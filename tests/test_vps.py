"""VPS boundary checks; no real credentials or Linux.do requests."""
import asyncio
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from linuxdo_mcp.http_server import PrivateGateway, make_app
from linuxdo_mcp.vps_admin import save_private
from linuxdo_mcp import server


async def request(app, headers=(), path="/mcp", method="POST"):
    messages = []
    async def receive():
        raise AssertionError("The authentication boundary must not read request bodies")
    async def send(message):
        messages.append(message)
    await app({"type": "http", "path": path, "method": method, "headers": list(headers)}, receive, send)
    return messages[0]["status"]


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_noninteractive_cookie_input_never_echoes(self):
        sample = 'opaque-cookie-stdin-fixture'
        output = io.StringIO()
        with patch.object(sys, 'argv', ['server', '--configure-cookie', '--cookie-stdin']), \
             patch.object(sys, 'stdin', io.StringIO(sample)), \
             patch.object(server, 'configure_cookie', return_value={'id': 1}) as configure, redirect_stdout(output):
            server.main()
        configure.assert_called_once_with(sample)
        self.assertNotIn(sample, output.getvalue())
        self.assertIn('登录验证成功', output.getvalue())

    async def test_auth_rotation_rate_and_fail_closed(self):
        calls = []
        async def endpoint(scope, receive, send):
            calls.append(scope)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "token"
            with self.assertRaises(FileNotFoundError):
                PrivateGateway(endpoint, path)
            save_private(path, "A" * 64)
            app = PrivateGateway(endpoint, path, requests_per_minute=2)
            auth = [(b"authorization", b"Bearer " + b"A" * 64)]
            for _ in range(3):
                self.assertEqual(await request(app), 401)
            self.assertEqual(await request(app, auth * 2), 401)
            self.assertEqual(await request(app, auth, path="/cookie"), 404)
            self.assertEqual(await request(app, auth, method="GET"), 405)
            self.assertEqual(len(calls), 0)
            self.assertEqual(await request(app, auth), 200)
            save_private(path, "B" * 64)
            self.assertEqual(await request(app, auth), 401)
            auth = [(b"authorization", b"Bearer " + b"B" * 64)]
            self.assertEqual(await request(app, auth), 200)
            self.assertEqual(await request(app, auth), 429)
            self.assertEqual(len(calls), 2)
            path.unlink()
            self.assertEqual(await request(app, auth), 503)

    async def test_bounded_concurrency_and_public_url(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def endpoint(scope, receive, send):
            entered.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token"
            save_private(token, "A" * 64)
            for url in ("http://example.com", "https://user:password@example.com", "https://example.com/mcp", "https://example.com?key=secret"):
                with self.assertRaises(ValueError):
                    make_app(url, token)
            app = PrivateGateway(endpoint, token, max_inflight=1)
            auth = [(b"authorization", b"Bearer " + b"A" * 64)]
            first = asyncio.create_task(request(app, auth))
            await entered.wait()
            self.assertEqual(await request(app, auth), 429)
            release.set()
            self.assertEqual(await first, 200)
            self.assertEqual(await request(app, auth), 200)


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "Linux Bash guard test")
class ScriptGuardTests(unittest.TestCase):
    def test_stop_refuses_a_project_owned_by_another_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copyfile(Path(__file__).resolve().parents[1] / "linuxdo.sh", root / "linuxdo.sh")
            state = root / ".local/vps"
            state.mkdir(parents=True)
            (state / "deploy.env").write_text("LINUXDO_MODE=https\nLINUXDO_TUNNEL=0\nLINUXDO_PUBLIC_URL=https://example.test\n")
            command_log = root / "calls.txt"
            fake = root / "docker"
            fake.write_text(f'''#!{sys.executable}
import json, sys
from pathlib import Path
with Path({str(command_log)!r}).open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
if sys.argv[1] == 'ps': print('foreign-container')
elif sys.argv[1] == 'inspect': print('/unrelated/business')
''')
            fake.chmod(0o755)
            wrapper = 'docker() { "$TEST_PYTHON" "$TEST_DOCKER" "$@"; }; export -f docker; exec bash "$TEST_SCRIPT" stop'
            result = subprocess.run(["bash", "-c", wrapper],
                                    env={**os.environ, "TEST_PYTHON": sys.executable,
                                         "TEST_DOCKER": str(fake), "TEST_SCRIPT": str(root / "linuxdo.sh")},
                                    text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("同名 Docker 项目", result.stderr)
            calls = [json.loads(line) for line in command_log.read_text().splitlines()]
            self.assertFalse(any("down" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
