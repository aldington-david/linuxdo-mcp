"""Credential error and notification checks; never launch a real popup or read real secrets."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from linuxdo_mcp import credential_alerts as alerts, server


class CredentialTests(unittest.TestCase):
    def test_only_confirmed_auth_errors_notify(self):
        for status in (200, 403, 404, 407, 429, 500):
            self.assertFalse(alerts.invalid_key_event({"message": "poll failed; backing off", "attrs": {"status_code": status}}))
        self.assertFalse(alerts.invalid_key_event({"message": "unrelated log", "attrs": {"status_code": 401}}))
        self.assertTrue(alerts.invalid_key_event({"message": "poll failed; backing off", "attrs": {"status_code": 401}}))
        for code in ("expired", "blocked", "forbidden", "network_error", "rate_limited"):
            with patch.object(server, "_cookie_header", return_value="_t=fake"), \
                 patch.object(server.cookies, "recently_validated", return_value=True), \
                 patch.object(server.cookies, "clear_cache"), \
                 patch.object(server, "_request", side_effect=server.LoginCheckError(code, "fixture")), \
                 patch.object(alerts, "request") as notify:
                with self.assertRaises(server.LoginCheckError):
                    server._fetch_locked("/fixture.json")
                if code == "expired":
                    notify.assert_called_once_with("Cookie")
                else:
                    notify.assert_not_called()

    def test_one_popup_per_episode_and_rearm_after_valid_update(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(alerts, "_state", Path(tmp)), \
             patch.object(alerts.subprocess, "run") as run, \
             patch.object(alerts.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             patch.object(alerts.subprocess, "CREATE_NEW_CONSOLE", 0x10, create=True):
            root = Path(tmp)
            (root / "credential-notifications.json").write_text(json.dumps({"task": "LinuxDo-Codex-Tunnel-AABBCCDDEEFF"}))
            self.assertTrue(alerts.request("TunnelKey"))
            self.assertFalse(alerts.request("TunnelKey"))
            self.assertEqual(run.call_count, 1)
            alerts.show_pending(root, "pwsh.exe", root / "manager.ps1")
            self.assertEqual(run.call_count, 2)
            self.assertIn("RepairCredential", run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs["creationflags"], 0x10)
            alerts.show_pending(root, "pwsh.exe", root / "manager.ps1")
            self.assertFalse(alerts.request("TunnelKey"))
            self.assertEqual(run.call_count, 2)
            alerts.recovered("TunnelKey")
            self.assertTrue(alerts.request("TunnelKey"))
            self.assertEqual(run.call_count, 3)

    def test_sse_auth_event_uses_existing_local_stream(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(alerts.http.client, "HTTPConnection") as connect, \
             patch.object(alerts, "request") as notify, patch.object(alerts.time, "sleep", side_effect=StopIteration):
            root = Path(tmp)
            (root / "tunnel-key.xml").write_text("fake encrypted key; contents are not read")
            (root / "last-tunnel-status.json").write_text(json.dumps({"health_url": "http://127.0.0.1:12345/healthz"}))
            response = connect.return_value.getresponse.return_value
            response.status = 200
            response.readline.side_effect = [b': ping\n', b'data: {"message":"poll failed; backing off","attrs":{"status_code":401}}\n', b'']
            with self.assertRaises(StopIteration):
                alerts._watch_tunnel(root)
            connect.assert_called_once_with("127.0.0.1", 12345, timeout=30)
            connect.return_value.request.assert_called_once_with("GET", "/api/logs/stream", headers={"Accept": "text/event-stream"})
            notify.assert_called_once_with("TunnelKey")


if __name__ == "__main__":
    unittest.main()
