"""Offline deadline, cancellation and resumable-pagination checks; no forum traffic."""
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from linuxdo_mcp import budget, cookies, pacing, server
from mcp.server.mcpserver.exceptions import ToolError
from test_pacing import Clock
from test_plugin import fixture, post


def response(data):
    return SimpleNamespace(status_code=200, text=json.dumps(data), cookies={}, headers={})


@contextmanager
def isolated(clock=None):
    with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"):
        cookies._write_cache("_t=fixture", validated_at=time.time())
        if clock is None:
            yield
        else:
            with patch.object(budget, "time", clock), patch.object(pacing, "time", clock), \
                 patch.object(pacing.random, "uniform", side_effect=lambda low, high: (low + high) / 2):
                yield


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_deadline_covers_queue_preflight_network_and_retries(self):
        clock, timeouts = Clock(), []
        @contextmanager
        def queued_lock(**kwargs):
            clock.sleep(4)
            yield
        def get(url, **kwargs):
            timeouts.append(kwargs["timeout"])
            if url.endswith("/session/current.json"):
                clock.sleep(8)
                return response({"current_user": {"id": 1}})
            clock.sleep(kwargs["timeout"])
            raise server.creq.RequestsError("simulated network timeout")
        with isolated(clock), patch.object(cookies, "recently_validated", return_value=False), \
             patch.object(cookies, "locked", queued_lock), patch.object(server.creq, "get", side_effect=get):
            with self.assertRaisesRegex(ToolError, "时间预算"):
                await server.mcp.call_tool("search", {"query": "fixture"})
            self.assertEqual(len(timeouts), 3)
            self.assertAlmostEqual(timeouts[-1], 2.2)
            self.assertAlmostEqual(clock.now, 145)
            self.assertEqual(cookies.get_cookie(), "_t=fixture")
            self.assertIsNone(budget._current.get())

    async def test_search_returns_completed_pages_and_resumes_first_unread_page(self):
        clock, starts = Clock(), []
        def get(url, **kwargs):
            page = int(server.urllib.parse.parse_qs(server.urllib.parse.urlsplit(url).query)["page"][0])
            starts.append(page)
            clock.sleep(min(20, kwargs["timeout"]))
            if kwargs["timeout"] < 20:
                raise server.creq.RequestsError("simulated network timeout")
            return response({"topics": [{"id": page, "title": str(page)}],
                             "posts": [{"topic_id": page}],
                             "grouped_search_result": {"term": "fixture", "more_full_page_results": page < 4}})
        with isolated(clock), patch.object(server.creq, "get", side_effect=get):
            first = (await server.mcp.call_tool("search", {"query": "fixture", "pages": 5})).structured_content
            self.assertEqual((first["partial"], first["pages_returned"], first["next_page"]), (True, 2, 3))
            self.assertEqual(first["stop_reason"], "time_budget_exceeded")
            self.assertEqual([r["topic_id"] for r in first["results"]], [1, 2])
            self.assertAlmostEqual(clock.now, 145)
            last = (await server.mcp.call_tool("search", {"query": "fixture", "page": first["next_page"], "pages": 5})).structured_content
            self.assertFalse(last["partial"])
            self.assertIsNone(last["next_page"])
            self.assertEqual([r["topic_id"] for r in last["results"]], [3, 4])
            self.assertEqual(starts, [1, 2, 3, 3, 4])

    async def test_topic_resume_tracks_checked_positions_not_returned_count(self):
        clock, calls, slow = Clock(), [], [True]
        def get(url, **kwargs):
            path = url.removeprefix(server.BASE)
            calls.append(path)
            if path == "/t/42.json":
                clock.sleep(.2)
                return response({"id": 42, "title": "fixture", "post_stream": {
                    "stream": list(range(1, 62)), "posts": [post(1), post(40)]}})
            duration = (20 if len(calls) == 2 else 30) if slow[0] else .2
            clock.sleep(min(duration, kwargs["timeout"]))
            if duration > kwargs["timeout"]:
                raise server.creq.RequestsError("simulated network timeout")
            ids = server.urllib.parse.parse_qs(server.urllib.parse.urlsplit(url).query)["post_ids[]"]
            return response({"post_stream": {"posts": [post(int(i)) for i in ids if int(i) != 5]}})
        with isolated(clock), patch.object(server.creq, "get", side_effect=get):
            first = (await server.mcp.call_tool("get_topic", {"topic_id": 42, "posts": 100})).structured_content
            self.assertTrue(first["partial"])
            self.assertEqual((first["returned"], first["next_start"]), (20, 22))
            self.assertNotIn(79, [p["floor"] for p in first["posts"]])  # Cached post 40 is beyond the unread gap.
            slow[0] = False
            last = (await server.mcp.call_tool("get_topic", {"topic_id": 42, "posts": 100, "start": first["next_start"]})).structured_content
            self.assertFalse(last["partial"])
            self.assertIsNone(last["next_start"])
            self.assertEqual([p["floor"] for p in first["posts"] + last["posts"]],
                             [i * 2 - 1 for i in range(1, 62) if i != 5])

    async def test_spacing_does_not_overrun_and_markdown_explains_partial_results(self):
        clock = Clock()
        with isolated(clock), patch.object(server.creq, "get") as get:
            with budget.operation():
                pacing.before_request("/search.json")
                clock.now += 44
                pacing._write({"next_request_at": clock.now + 2})
                with self.assertRaises(budget.Exhausted):
                    server._fetch("/search.json?q=fixture")
                get.assert_not_called()
                self.assertEqual(clock.now, 144)
        search = {"term": "fixture", "count": 1, "results": [], "more_results": True,
                  "pages_returned": 1, "next_page": 2, "partial": True}
        topic = {"title": "fixture", "url": "https://linux.do/t/42", "posts": [],
                 "partial": True, "next_start": 22}
        with patch.object(server, "_search", return_value=search), patch.object(server, "_topic", return_value=topic):
            result = await server.mcp.call_tool("format_search", {"query": "fixture", "pages": 5})
            self.assertIn("page=2", result.content[0].text)
            result = await server.mcp.call_tool("format_topic", {"topic_id": 42})
            self.assertIn("start=22", result.content[0].text)

    async def test_worker_queue_and_guard_return_before_client_deadline(self):
        limiter = anyio.to_thread.current_default_thread_limiter()
        previous = limiter.total_tokens
        entered, release = threading.Event(), threading.Event()
        def occupy():
            entered.set()
            release.wait(3)
        limiter.total_tokens = 1
        holder = asyncio.create_task(anyio.to_thread.run_sync(occupy))
        try:
            while not entered.is_set():
                await asyncio.sleep(.005)
            with patch.object(budget, "WORK_SECONDS", .1), patch.object(budget, "RESPONSE_SECONDS", .2), \
                 patch.object(server, "_whoami") as call:
                started = time.monotonic()
                with self.assertRaisesRegex(ToolError, "时间预算"):
                    await server.mcp.call_tool("whoami", {})
                self.assertLess(time.monotonic() - started, .8)
                release.set()
                await holder
                await asyncio.sleep(.05)
                call.assert_not_called()
        finally:
            release.set()
            await holder
            limiter.total_tokens = previous

    async def test_cancel_or_response_guard_stops_worker_before_another_request(self):
        for cancel in (True, False):
            entered, release, done = threading.Event(), threading.Event(), threading.Event()
            calls = []
            def get(url, **kwargs):
                calls.append(url)
                entered.set()
                release.wait(2)
                return response({"topics": [], "posts": [], "grouped_search_result": {"more_full_page_results": True}})
            original = server._search
            def search(*args):
                try:
                    return original(*args)
                finally:
                    done.set()
            with isolated(), patch.object(server.creq, "get", side_effect=get), patch.object(server, "_search", search), \
                 patch.object(budget, "RESPONSE_SECONDS", .15):
                task = asyncio.create_task(server.mcp.call_tool("search", {"query": "fixture", "pages": 5}))
                try:
                    while not entered.is_set():
                        await asyncio.sleep(.005)
                    if cancel:
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                    else:
                        with self.assertRaisesRegex(ToolError, "时间预算"):
                            await task
                    release.set()
                    for _ in range(200):
                        if done.is_set():
                            break
                        await asyncio.sleep(.005)
                    self.assertTrue(done.is_set())
                    self.assertEqual(len(calls), 1)
                    with cookies.locked(timeout=.1):
                        pass
                finally:
                    release.set()

    async def test_real_socket_timeout_and_lock_contention_respect_budget(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        release = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                release.wait(2)
            def log_message(self, *args):
                pass
        http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            with isolated(), patch.object(server, "BASE", f"http://127.0.0.1:{http.server_port}"), \
                 patch.object(budget, "WORK_SECONDS", .25), patch.object(budget, "RESPONSE_SECONDS", .8):
                started = time.monotonic()
                with self.assertRaisesRegex(ToolError, "时间预算"):
                    await server.mcp.call_tool("whoami", {})
                self.assertLess(time.monotonic() - started, .8)
                with cookies.locked(), patch.object(server.creq, "get") as get:
                    started = time.monotonic()
                    with self.assertRaisesRegex(ToolError, "时间预算"):
                        await server.mcp.call_tool("whoami", {})
                    self.assertLess(time.monotonic() - started, .8)
                    get.assert_not_called()
        finally:
            release.set()
            http.shutdown()
            http.server_close()
            worker.join(2)


if __name__ == "__main__":
    unittest.main()
