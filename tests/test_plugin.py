"""离线回归：不读取真实 Cookie，不向 Linux.do 发请求。"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
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


class CoreTests(unittest.TestCase):
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
        for value in ("_t=abc; other=secret", "_t=abc\r\nInjected: true", "session=wrong"):
            with self.assertRaises(ValueError):
                cookies._normalize(value)

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
                        self.assertEqual(json.loads(zipped.read(".app.json"))["apps"]["linuxdo"]["id"], app_id)
                    else:
                        self.assertNotIn(".app.json", names)
            with self.assertRaises(ValueError):
                packager.package(Path(tmp) / "bad.zip", "https://evil.test/")


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
