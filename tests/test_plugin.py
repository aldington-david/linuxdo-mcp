"""离线回归：不读取真实 Cookie，不向 Linux.do 发请求。"""
import asyncio
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from linuxdo_mcp import cookies, server
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver.exceptions import ToolError

TOOLS = {
    "whoami", "search", "get_topic", "format_search", "format_topic",
    "list_categories", "category_topics", "list_tags", "tag_topics",
    "user_info", "latest_topics", "top_topics", "user_actions",
}


def post(i):
    return {"id": i, "post_number": i * 2 - 1, "username": "reader",
            "cooked": '<p>text</p><pre><code class="lang-python">print(1)</code></pre>'}


def fixture(path):
    topic = {"id": 42, "title": "Example", "slug": "example", "category_id": 1,
             "tags": ["ai", {"name": "code"}], "posts_count": 45}
    if path == "/session/current.json":
        return {"current_user": {"username": "reader", "trust_level": 1}}
    if path.startswith("/search.json"):
        return {"topics": [topic], "posts": [{"topic_id": 42, "blurb": "<p>summary</p>"}],
                "grouped_search_result": {"term": "test", "more_full_page_results": False}}
    if path == "/t/42.json":
        return {**topic, "post_stream": {"stream": list(range(1, 46)), "posts": [post(1)]}}
    if path.startswith("/t/42/posts.json?"):
        ids = server.urllib.parse.parse_qs(server.urllib.parse.urlsplit(path).query)["post_ids[]"]
        return {"post_stream": {"posts": [post(int(i)) for i in ids]}}
    cats = [{"id": 1, "slug": "dev", "name": "开发调优, Lv1"}]
    if path == "/site.json":
        return {"categories": cats}
    if path == "/categories.json":
        return {"category_list": {"categories": cats}}
    if path == "/tags.json":
        return {"tags": [{"name": "ai", "count": 1}]}
    if path == "/u/reader.json":
        return {"user": {"username": "reader"}}
    if path == "/u/reader/summary.json":
        return {"user_summary": {"topic_count": 1}}
    if path.startswith("/user_actions.json"):
        return {"user_actions": [{"topic_id": 42, "slug": "example", "post_number": 1}]}
    if path.startswith(("/latest.json", "/top.json", "/c/", "/tag/")):
        return {"topic_list": {"topics": [topic]}}
    raise AssertionError(f"Unexpected fixture request: {path}")


def concurrent_request(cache_dir, start, results):
    cookies.CACHE = Path(cache_dir) / "cookie.json"
    counter = Path(cache_dir) / "website-token.txt"

    def get(url, **kwargs):
        token = counter.read_text()
        if kwargs["headers"]["Cookie"] != "_t=" + token:
            return SimpleNamespace(status_code=401, text="{}", cookies={})
        # 模拟网站已轮换而响应仍在路上；无跨进程锁会导致另一进程带旧凭证请求。
        newer = str(int(token) + 1)
        counter.write_text(newer)
        time.sleep(0.2)
        return SimpleNamespace(status_code=200, text='{"ok":true}', cookies={"_t": newer})

    start.wait(timeout=20)
    try:
        with patch.object(server.creq, "get", side_effect=get):
            results.put(server._fetch("/test.json"))
    except Exception as error:
        results.put({"error": str(error)})


def hold_cookie_lock(cache_dir, ready):
    cookies.CACHE = Path(cache_dir) / "cookie.json"
    with cookies.locked():
        ready.set()
        time.sleep(60)


class CoreTests(unittest.TestCase):
    def test_cross_process_rotation_and_abandoned_lock(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"):
            cookies._write_cache("_t=0", validated_at=time.time())
            (Path(tmp) / "website-token.txt").write_text("0")
            start, results = context.Barrier(3), context.Queue()
            workers = [context.Process(target=concurrent_request, args=(tmp, start, results)) for _ in range(2)]
            try:
                for worker in workers:
                    worker.start()
                start.wait(timeout=20)
                self.assertEqual([results.get(timeout=20) for _ in workers], [{"ok": True}] * 2)
                for worker in workers:
                    worker.join(timeout=10)
                    self.assertEqual(worker.exitcode, 0)
                self.assertEqual(cookies.get_cookie(), "_t=2")
            finally:
                for worker in workers:
                    if worker.is_alive():
                        worker.terminate()
                        worker.join(timeout=10)
                results.close()
            ready = context.Event()
            holder = context.Process(target=hold_cookie_lock, args=(tmp, ready))
            holder.start()
            try:
                self.assertTrue(ready.wait(timeout=20))
                with self.assertRaises(RuntimeError):
                    with cookies.locked(timeout=0.1):
                        self.fail("lock was not exclusive")
            finally:
                holder.terminate()
                holder.join(timeout=10)
            with cookies.locked(timeout=1):
                self.assertEqual(cookies.get_cookie(), "_t=2")

    def test_topic_identifiers_and_pagination(self):
        for value in (42, "42", "https://linux.do/t/42/5", "https://linux.do/t/example/42/5"):
            self.assertEqual(server._as_topic_id(value), 42)
        for value in (0, -1, True, "bad42", "https://evil.test/t/x/42", "https://linux.do.evil/t/x/42"):
            with self.assertRaises(ValueError):
                server._as_topic_id(value)
        with patch.object(server, "_fetch", side_effect=fixture) as fetch:
            first = server._topic(42, 21, 1)
            last = server._topic(42, 100, first["next_start"])
            self.assertEqual(first["next_start"], 22)
            self.assertEqual(first["posts"][1]["floor"], 3)
            self.assertEqual(first["posts"][1]["url"], "https://linux.do/t/example/42/3")
            self.assertEqual(last["returned"], 24)
            self.assertIsNone(last["next_start"])
            self.assertEqual(server._topic(42, 20, 99)["returned"], 0)
            for call in fetch.call_args_list:
                if "posts.json" in call.args[0]:
                    self.assertLessEqual(call.args[0].count("post_ids[]="), 20)
        self.assertIn("```python\nprint(1)\n```", first["posts"][0]["content"])

    def test_cookie_rotation_and_request_boundary(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"), \
             patch.dict(os.environ, {"LINUXDO_COOKIE": "_t=bootstrap", "LINUXDO_READ_BROWSER": "0"}), \
             patch.object(server.creq, "get") as get:
            cookies._write_cache("_t=bootstrap", validated_at=time.time())
            get.return_value = SimpleNamespace(status_code=200, text='{"ok": true}', cookies={"_t": "rotated"})
            self.assertEqual(server._fetch("/test.json"), {"ok": True})
            self.assertEqual(get.call_args.kwargs["headers"]["Cookie"], "_t=bootstrap")
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
            self.assertEqual(cookies.get_cookie(), "_t=rotated")
            for path in ("https://evil.test/", "//evil.test/"):
                with self.assertRaises(ToolError):
                    server._fetch(path)
            for status in (403, 429, 302):
                get.return_value = SimpleNamespace(status_code=status, text="private-secret", cookies={})
                with self.assertRaises(ToolError) as error:
                    server._fetch("/test.json")
                self.assertNotIn("private-secret", str(error.exception))
                self.assertTrue(cookies.CACHE.exists())
            get.return_value.status_code = 404
            with self.assertRaisesRegex(ToolError, "未识别登录 Cookie"):
                server._fetch("/session/current.json")
            self.assertFalse(cookies.CACHE.exists())
            get.return_value.status_code = 401
            with self.assertRaises(ToolError):
                server._fetch("/test.json")
            self.assertFalse(cookies.CACHE.exists())
            cookies.CACHE.write_text('{"ts": "invalid"}', encoding="utf-8")
            self.assertEqual(cookies.get_cookie(), "_t=bootstrap")
            with patch.object(cookies.os, "replace", side_effect=OSError):
                with self.assertRaises(RuntimeError):
                    cookies._write_cache("_t=next")
            self.assertEqual(cookies.get_cookie(), "_t=bootstrap")
            self.assertEqual(list(Path(tmp).glob(".cookie-*")), [])
        for value in ("padded-token==", "_t=padded-token==", "opaque=value"):
            expected = "_t=" + server.urllib.parse.quote(value.removeprefix("_t="), safe="%")
            self.assertEqual(cookies._normalize(value), expected)
        self.assertEqual(cookies._normalize("a+b/c=="), "_t=a%2Bb%2Fc%3D%3D")
        self.assertEqual(cookies._normalize("_t=a%2Bb%2Fc%3D%3D"), "_t=a%2Bb%2Fc%3D%3D")
        for value in ("_t=abc; other=secret", "_t=abc\r\nInjected: true", "_t="):
            with self.assertRaises(ValueError):
                cookies._normalize(value)

    def test_validated_cookie_update_and_automatic_login_check(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"), \
             patch.dict(os.environ, {"LINUXDO_COOKIE": "", "LINUXDO_READ_BROWSER": "0"}), \
             patch.object(server.creq, "get") as get:
            cookies._write_cache("_t=old")
            before = cookies.CACHE.read_bytes()
            for status, body, code in ((200, '{}', 'expired'), (401, '{}', 'expired'),
                                       (403, 'Just a moment', 'blocked'), (429, '{}', 'rate_limited')):
                get.return_value = SimpleNamespace(status_code=status, text=body, cookies={})
                with self.assertRaises(server.LoginCheckError) as error:
                    server.configure_cookie('candidate')
                self.assertEqual(error.exception.code, code)
                self.assertEqual(cookies.CACHE.read_bytes(), before)
            get.return_value = SimpleNamespace(status_code=200, text='{"current_user":{"id":1,"username":"reader"}}', cookies={"_t":"rotated"})
            server.configure_cookie('candidate')
            self.assertEqual(cookies.get_cookie(), '_t=rotated')
            self.assertTrue(cookies.recently_validated())
            cookies._write_cache('_t=old')
            get.reset_mock()
            get.side_effect = [get.return_value, SimpleNamespace(status_code=200, text='{"ok":true}', cookies={})]
            self.assertEqual(server._fetch('/search.json?q=test'), {'ok': True})
            self.assertTrue(get.call_args_list[0].args[0].endswith('/session/current.json'))
            self.assertEqual(get.call_args_list[1].kwargs['headers']['Cookie'], '_t=rotated')
            get.side_effect = None
            get.return_value = SimpleNamespace(status_code=200, text='{}', cookies={})
            result = server.check_cookie()
            self.assertEqual(result['status'], 'expired')
            self.assertFalse(cookies.CACHE.exists())
            self.assertEqual(server.check_cookie()['status'], 'missing')

    def test_package_excludes_secrets_and_binds_registered_app(self):
        spec = importlib.util.spec_from_file_location("packager", ROOT / "scripts/package_plugin.py")
        packager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packager)
        with tempfile.TemporaryDirectory() as tmp:
            for app_id in (None, "plugin_asdk_app_testonly"):
                archive = packager.package(Path(tmp) / "plugin.zip", app_id)
                with ZipFile(archive) as zipped:
                    names = zipped.namelist()
                    self.assertIn("skills/linuxdo-research/SKILL.md", names)
                    self.assertNotIn("cookie.json", names)
                    self.assertNotIn(".env", names)
                    self.assertEqual("mcp.json" in names, app_id is None)
                    manifest = json.loads(zipped.read(".codex-plugin/plugin.json"))
                    if app_id:
                        self.assertNotIn("mcpServers", manifest)
                        self.assertEqual(json.loads(zipped.read(".app.json"))["apps"]["linuxdo"]["id"], app_id.removeprefix("plugin_"))
                    else:
                        self.assertNotIn(".app.json", names)
                        config = json.loads(zipped.read("mcp.json"))["mcpServers"]["linuxdo"]
                        self.assertEqual(config["type"], "stdio")
                        self.assertEqual(config["args"][-1], "linuxdo_mcp.server")
            archive = packager.package(Path(tmp) / "local.zip", python_command=sys.executable)
            with ZipFile(archive) as zipped:
                for name in ("mcp.json", ".mcp.json"):
                    entry = json.loads(zipped.read(name))["mcpServers"]["linuxdo"]
                    self.assertEqual(entry["command"], "python")
                    self.assertEqual(entry["cwd"], "./")
                    self.assertEqual(entry["args"][-1], "./scripts/launch_local.py")
                self.assertEqual(json.loads(zipped.read("scripts/runtime.json"))["python"], sys.executable)
                self.assertNotIn("scripts/Manage-LinuxDo.ps1", zipped.namelist())
            archive = packager.package(Path(tmp) / "managed.zip", python_command=sys.executable,
                                       manager_state=str(Path(tmp) / "manager"), tunnel_task="LinuxDo-test-only")
            with ZipFile(archive) as zipped:
                self.assertEqual(json.loads(zipped.read("scripts/runtime.json"))["tunnel_task"], "LinuxDo-test-only")
                self.assertNotIn("tunnel-key.xml", " ".join(zipped.namelist()))
            with self.assertRaises(ValueError):
                packager.package(Path(tmp) / "bad.zip", "https://evil.test/")
            with self.assertRaises(ValueError):
                packager.package(Path(tmp) / "bad-manager.zip", manager_state=tmp)
            archive = packager.package(Path(tmp) / "cloud-update.zip", "plugin_asdk_app_testonly",
                                       plugin_name="dev-testonly")
            with ZipFile(archive) as zipped:
                for name in ("plugin.json", ".codex-plugin/plugin.json"):
                    self.assertEqual(json.loads(zipped.read(name))["name"], "dev-testonly")

    def test_plugin_bootstrap_keeps_tunnel_output_off_mcp_stdio(self):
        spec = importlib.util.spec_from_file_location("launcher", ROOT / "scripts/launch_local.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runtime.json").write_text(json.dumps({"python": sys.executable, "manager_state": tmp,
                                                          "tunnel_task": "LinuxDo-test-only"}))
            (root / "tunnel-key.xml").write_text("not-a-real-credential")
            launcher.__file__ = str(root / "launch_local.py")
            fake_os = SimpleNamespace(name="nt", execv=lambda *args: None)
            fake_process = SimpleNamespace(run=lambda *args, **kwargs: None, call=lambda *args, **kwargs: 0, DEVNULL=-3,
                                           CREATE_NO_WINDOW=0x08000000, SubprocessError=subprocess.SubprocessError)
            with patch.object(launcher, "os", fake_os), patch.object(launcher, "subprocess", fake_process), \
                 patch.object(fake_process, "run") as spawn, patch.object(fake_os, "execv") as execute, \
                 patch.object(fake_process, "call", return_value=0) as serve:
                self.assertEqual(launcher.main([]), 0)
                self.assertEqual(spawn.call_args.kwargs["stdin"], fake_process.DEVNULL)
                self.assertEqual(spawn.call_args.kwargs["creationflags"], fake_process.CREATE_NO_WINDOW)
                self.assertEqual(spawn.call_args.kwargs["stdout"], fake_process.DEVNULL)
                self.assertEqual(spawn.call_args.kwargs["stderr"], fake_process.DEVNULL)
                self.assertEqual(spawn.call_args.args[0], ["schtasks.exe", "/Run", "/TN", "LinuxDo-test-only"])
                self.assertNotIn("not-a-real-credential", str(spawn.call_args))
                execute.assert_not_called()
                serve.assert_called_once_with([sys.executable, "-X", "utf8", "-m", "linuxdo_mcp.server"],
                                              stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
                                              creationflags=fake_process.CREATE_NO_WINDOW)
                spawn.reset_mock()
                with patch.object(launcher, "tunnel_ready", return_value=True):
                    self.assertEqual(launcher.main([]), 0)
                    spawn.assert_not_called()
                    self.assertEqual(launcher.main(["--start-tunnel", tmp]), 0)
                    spawn.assert_not_called()
                with patch.object(launcher, "tunnel_ready", return_value=False):
                    spawn.return_value.returncode = 0
                    self.assertEqual(launcher.main(["--start-tunnel", tmp]), 0)
                    self.assertEqual(spawn.call_args.args[0][0], "pwsh.exe")
                    self.assertEqual(spawn.call_args.kwargs["creationflags"], fake_process.CREATE_NO_WINDOW)
                    self.assertEqual(spawn.call_args.kwargs["stdout"], fake_process.DEVNULL)
                    self.assertEqual(spawn.call_args.kwargs["stderr"], fake_process.DEVNULL)

    def test_tunnel_health_probe_is_local_bounded_and_does_not_follow_redirects(self):
        spec = importlib.util.spec_from_file_location("launcher", ROOT / "scripts/launch_local.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as tmp, patch.object(launcher.http.client, "HTTPConnection") as connect:
            state = Path(tmp) / "last-tunnel-status.json"
            self.assertFalse(launcher.tunnel_ready(tmp))
            for url in ("https://example.com", "http://127.0.0.1.evil.test:8080", "http://user:secret@127.0.0.1:8080"):
                state.write_text(json.dumps({"health_url": url}))
                self.assertFalse(launcher.tunnel_ready(tmp))
            connect.assert_not_called()
            state.write_text(json.dumps({"health_url": "http://127.0.0.1:12345/healthz"}))
            response = connect.return_value.getresponse.return_value
            response.status, response.read.return_value = 200, b"ready\n"
            self.assertTrue(launcher.tunnel_ready(tmp))
            connect.assert_called_with("127.0.0.1", 12345, timeout=0.5)
            connect.return_value.request.assert_called_with("GET", "/readyz")
            connect.return_value.close.assert_called_once()
            response.status = 302
            self.assertFalse(launcher.tunnel_ready(tmp))

    @unittest.skipUnless(os.name == "nt", "Windows console creation check")
    def test_windowless_entry_creates_no_powershell_console(self):
        pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "launch_local.py").write_bytes((ROOT / "scripts/launch_local.py").read_bytes())
            (root / "Manage-LinuxDo.ps1").write_text('''param($Action,[switch]$Unattended,$StateDir)
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class ConsoleProbe { [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow(); }'
Write-Host 'This test message must not open a console window.'
@{console_window=[ConsoleProbe]::GetConsoleWindow().ToInt64()} | ConvertTo-Json | Set-Content (Join-Path $StateDir 'probe.json')
''', encoding="utf-8")
            subprocess.run([pythonw, "-X", "utf8", str(root / "launch_local.py"), "--start-tunnel", tmp],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True, timeout=20)
            self.assertEqual(json.loads((root / "probe.json").read_text(encoding="utf-8-sig"))["console_window"], 0)


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_tools_and_input_validation(self):
        definitions = await server.mcp.list_tools()
        self.assertEqual({t.name for t in definitions}, TOOLS)
        for tool in definitions:
            self.assertTrue(tool.annotations.read_only_hint)
            self.assertFalse(tool.annotations.destructive_hint)
            self.assertTrue(tool.annotations.open_world_hint)
            self.assertTrue(tool.title)
            if not tool.name.startswith("format_"):
                self.assertIsNotNone(tool.output_schema)
        arguments = {
            "search": {"query": "test"}, "get_topic": {"topic_id": 42},
            "format_search": {"query": "test"}, "format_topic": {"topic_id": 42},
            "category_topics": {"category_id": 1}, "tag_topics": {"tag": "ai"},
            "user_info": {"username": "reader"}, "user_actions": {"username": "reader"},
        }
        with patch.object(server, "_fetch", side_effect=fixture):
            for name in TOOLS:
                result = await server.mcp.call_tool(name, arguments.get(name, {}))
                self.assertFalse(result.is_error, name)
                self.assertTrue(result.content, name)
                if not name.startswith("format_"):
                    self.assertIsNotNone(result.structured_content, name)
        with patch.object(server, "_fetch", side_effect=AssertionError("must not fetch")):
            for name, args in (
                ("search", {"query": "test", "pages": 6}), ("search", {"query": ""}),
                ("search", {"query": "test", "page": 0}), ("latest_topics", {"page": -1}),
                ("get_topic", {"topic_id": 42, "posts": 101}),
                ("get_topic", {"topic_id": 42, "start": 0}),
                ("user_info", {"username": "../../secret"}),
            ):
                with self.assertRaises(ToolError):
                    await server.mcp.call_tool(name, args)

    async def check_session(self, read, write, fixture_data=False):
        async with ClientSession(read, write, read_timeout_seconds=15) as session:
            init = await session.initialize()
            self.assertEqual(init.server_info.name, "linuxdo")
            self.assertTrue(init.instructions)
            tools = await session.list_tools()
            self.assertEqual({t.name for t in tools.tools}, TOOLS)
            bad = await session.call_tool("get_topic", {"topic_id": 42, "posts": 101})
            self.assertTrue(bad.is_error)
            identity = await session.call_tool("whoami", {})
            if fixture_data:
                self.assertFalse(identity.is_error)
                self.assertEqual(identity.structured_content["username"], "reader")
                found = await session.call_tool("search", {"query": "test"})
                self.assertFalse(found.is_error)
                self.assertEqual(found.structured_content["results"][0]["tags"], ["ai", "code"])
                topic = await session.call_tool("get_topic", {"topic_id": 42, "posts": 21})
                self.assertFalse(topic.is_error)
                self.assertEqual(topic.structured_content["next_start"], 22)
            else:
                self.assertTrue(identity.is_error)
                self.assertIn("LINUXDO_COOKIE", str(identity.content))

    async def test_real_stdio_and_http_transports(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1",
                   "LINUXDO_COOKIE": "", "LINUXDO_READ_BROWSER": "0", "LINUXDO_CACHE_DIR": tmp}
            params = StdioServerParameters(command=sys.executable,
                                            args=["-m", "linuxdo_mcp.server"], env=env)
            with open(os.devnull, "w") as quiet:
                async with stdio_client(params, errlog=quiet) as (read, write):
                    await self.check_session(read, write)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            with open(Path(tmp) / "server.log", "w", encoding="utf-8") as log:
                env["PYTHONPATH"] += os.pathsep + str(ROOT / "tests")
                bootstrap = "from linuxdo_mcp import server; from test_plugin import fixture; server._fetch = fixture; server.main()"
                child = subprocess.Popen(
                    [sys.executable, "-c", bootstrap, "--transport", "streamable-http", "--port", str(port)],
                    env=env, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    for _ in range(100):
                        if child.poll() is not None:
                            self.fail("HTTP server exited: " + (Path(tmp) / "server.log").read_text(encoding="utf-8"))
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=.1):
                                break
                        except OSError:
                            await asyncio.sleep(.1)
                    else:
                        self.fail("HTTP server did not start")
                    url = f"http://127.0.0.1:{port}/mcp"
                    async with streamable_http_client(url) as streams:
                        await self.check_session(streams[0], streams[1], fixture_data=True)
                    for headers in ({"Host": "evil.test"}, {"Origin": "https://evil.test"}):
                        request = Request(url, data=b"{}", headers={"Content-Type": "application/json", **headers})
                        with self.assertRaises(HTTPError) as error:
                            urlopen(request, timeout=5)
                        self.assertIn(error.exception.code, (403, 421))
                        error.exception.close()
                finally:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    else:
                        child.terminate()
                    child.wait(timeout=15)


if __name__ == "__main__":
    unittest.main()
