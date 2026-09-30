"""Shared request spacing and server cooldown checks, without real forum traffic."""
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from linuxdo_mcp import cookies, pacing, server
from mcp.server.mcpserver.exceptions import ToolError


class Clock:
    def __init__(self):
        self.now, self.waits = 100.0, []
    def time(self):
        return self.now
    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def worker(directory, gate, results):
    cookies.CACHE = Path(directory) / "cookie.json"
    gate.wait(20)
    try:
        with cookies.locked():
            pacing.before_request("/search.json?q=fixture")
            results.put(time.time())
    except pacing.Deferred as error:
        results.put(error.code)


class PacingTests(unittest.TestCase):
    def test_jitter_idle_time_network_time_and_search_budget(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"), \
             patch.object(pacing, "time", clock), patch.object(pacing.random, "uniform", side_effect=lambda low, high: (low + high) / 2):
            pacing.before_request("/search.json?q=sensitive-fixture")
            self.assertEqual(clock.waits, [])
            clock.now += 0.4  # Existing network time reduces, rather than adds to, the next wait.
            pacing.before_request("/t/42.json")
            self.assertAlmostEqual(clock.waits[-1], 1.0)
            pacing.before_request("/search.json?q=second")
            self.assertAlmostEqual(clock.now, 102.8)
            clock.now += 10
            before = len(clock.waits)
            pacing.before_request("/search.json?q=after-idle")
            self.assertEqual(len(clock.waits), before)
            state = (Path(tmp) / "request-state.json").read_text()
            self.assertNotIn("sensitive", state)
            self.assertNotIn("cookie", state)

    def test_identity_and_network_retries_also_take_slots(self):
        clock, starts = Clock(), []
        def get(url, **kwargs):
            starts.append(clock.now)
            if len(starts) == 2:
                raise server.creq.RequestsError("fixture network error")
            body = '{"current_user":{"id":1}}' if url.endswith('/session/current.json') else '{"ok":true}'
            return SimpleNamespace(status_code=200, text=body, cookies={}, headers={})
        with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"), \
             patch.object(pacing, "time", clock), patch.object(server, "time", clock), \
             patch.object(pacing.random, "uniform", side_effect=lambda low, high: (low + high) / 2), \
             patch.object(server.creq, "get", side_effect=get):
            cookies._write_cache("_t=fixture")
            self.assertEqual(server._fetch("/search.json?q=fixture"), {"ok": True})
            self.assertEqual(len(starts), 3)
            self.assertAlmostEqual(starts[1] - starts[0], 1.4)
            self.assertAlmostEqual(starts[2] - starts[1], 2.7)

    def test_server_cooldown_blocks_next_request_without_waiting_or_losing_cookie(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"), \
             patch.object(pacing, "time", clock), patch.object(server.creq, "get") as get:
            cookies._write_cache("_t=fixture", validated_at=time.time())
            get.return_value = SimpleNamespace(status_code=429, text="{}", cookies={}, headers={"Retry-After": "7"})
            def config_changed_during_response(*args, **kwargs):
                (Path(tmp) / "request-policy.json").write_text('{incomplete-edit')
                return get.return_value
            get.side_effect = config_changed_during_response
            with self.assertRaisesRegex(ToolError, "429"):
                server._fetch("/fixture.json")
            (Path(tmp) / "request-policy.json").write_text('{}')
            get.side_effect = None
            with self.assertRaisesRegex(ToolError, "冷却中"):
                server._fetch("/different.json")
            self.assertEqual(get.call_count, 1)
            self.assertEqual(clock.waits, [])
            self.assertEqual(cookies.get_cookie(), "_t=fixture")
            clock.now += 7
            get.return_value = SimpleNamespace(status_code=200, text='{"text":"Just a moment challenge-platform"}', cookies={}, headers={})
            self.assertIn("text", server._fetch("/different.json"))  # Forum text is not a challenge page.
            get.return_value = SimpleNamespace(status_code=403, text="<html>Just a moment</html>", cookies={}, headers={})
            with self.assertRaisesRegex(ToolError, "Cloudflare"):
                server._fetch("/fixture.json")
            count = get.call_count
            with self.assertRaisesRegex(ToolError, "防护冷却"):
                server._fetch("/fixture.json")
            self.assertEqual(get.call_count, count)

    def test_retry_after_dates_and_invalid_configuration(self):
        self.assertEqual(pacing._retry_after({"retry-after": "Thu, 01 Oct 2026 00:00:35 GMT", "date": "Thu, 01 Oct 2026 00:00:00 GMT"}, 100), 35)
        self.assertIsNone(pacing._retry_after({"retry-after": "not-a-date"}, 100))
        with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"):
            for bad in ({"min_seconds": -1}, {"max_seconds": 0.1}, {"min_seconds": True}, {"max_seconds": float('nan')}, {"unknown": 1}):
                (Path(tmp) / "request-policy.json").write_text(json.dumps(bad))
                with self.assertRaises(RuntimeError):
                    pacing.before_request("/fixture.json")
            (Path(tmp) / "request-policy.json").write_text('{}')
            self.assertEqual(pacing.cool_down({}, "rate_limited"), 60)
            (Path(tmp) / "request-state.json").write_text('{broken')
            with self.assertRaises(RuntimeError):
                pacing.before_request("/fixture.json")

    def test_processes_share_spacing_and_persisted_cooldown(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as tmp, patch.object(cookies, "CACHE", Path(tmp) / "cookie.json"):
            (Path(tmp) / "request-policy.json").write_text(json.dumps({"min_seconds": .3, "max_seconds": .3, "search_min_seconds": .5, "search_max_seconds": .5}))
            gate, results = context.Event(), context.Queue()
            children = []
            try:
                children = [context.Process(target=worker, args=(tmp, gate, results)) for _ in range(2)]
                for child in children: child.start()
                gate.set()
                starts = sorted(results.get(timeout=25) for _ in children)
                self.assertGreaterEqual(starts[1] - starts[0], .48)
                for child in children: child.join(10)
                with cookies.locked():
                    pacing.cool_down({"Retry-After": "60"}, "rate_limited")
                child = context.Process(target=worker, args=(tmp, gate, results))
                children.append(child)
                child.start()
                self.assertEqual(results.get(timeout=25), "rate_limited")
                child.join(10)
                self.assertTrue(all(c.exitcode == 0 for c in children))
            finally:
                for child in children:
                    if child.is_alive(): child.terminate(); child.join(10)
                results.close()


if __name__ == "__main__":
    unittest.main()
