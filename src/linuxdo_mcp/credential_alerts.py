"""Windows credential alerts: existing demand task, one alert per failed credential episode."""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

KINDS = ("Cookie", "TunnelKey")
_state = None


def configure(state, *, watch=False):
    global _state
    _state = None
    if os.name != "nt" or not state:
        return
    state = Path(state).resolve()
    if not (state / "credential-notifications.json").is_file():
        return
    _state = state
    if watch:
        threading.Thread(target=_watch_tunnel, args=(state,), daemon=True,
                         name="linuxdo-tunnel-auth-events").start()


def request(kind):
    if _state is None or kind not in KINDS:
        return False
    marker = _state / f"credential-{kind}.alert"
    if marker.exists():
        return False
    temporary = None
    try:
        settings = json.loads((_state / "credential-notifications.json").read_text(encoding="utf-8-sig"))
        task = settings["task"]
        if not re.fullmatch(r"LinuxDo-Codex-Tunnel-[A-F0-9]{12}", task):
            return False
        # Publish a complete marker exclusively; parallel processes cannot duplicate it.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=_state, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"shown": False, "time": time.time()}, stream)
        os.link(temporary, marker)
    except (OSError, ValueError, KeyError, TypeError):
        return False
    finally:
        if temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    try:
        subprocess.run(["schtasks.exe", "/Run", "/TN", task], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        # Let the next real failure retry dispatch; no timer or popup retry loop.
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


def recovered(kind):
    if _state is not None and kind in KINDS:
        try:
            (_state / f"credential-{kind}.alert").unlink(missing_ok=True)
        except OSError:
            pass


def show_pending(state, powershell, manager):
    """Called inside the existing single-instance Windows task, outside MCP process jobs."""
    for kind in KINDS:
        marker = Path(state) / f"credential-{kind}.alert"
        try:
            notice = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(notice, dict) or notice.get("shown"):
                continue
            marker.write_text(json.dumps({"shown": True, "time": notice.get("time")}), encoding="utf-8")
        except (OSError, ValueError, TypeError):
            continue
        try:
            # Visible only for a confirmed credential failure explicitly requested by the user.
            subprocess.run([powershell, "-NoLogo", "-NoProfile", "-File", str(manager),
                            "-Action", "RepairCredential", "-Credential", kind, "-StateDir", str(state)],
                           creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
        except OSError:
            marker.write_text(json.dumps({"shown": False}), encoding="utf-8")


def invalid_key_event(event):
    return (isinstance(event, dict) and event.get("message") == "poll failed; backing off"
            and isinstance(event.get("attrs"), dict) and event["attrs"].get("status_code") == 401)


def _watch_tunnel(state):
    # This thread lives only in the already-running Tunnel MCP process. SSE pings keep it idle.
    key_path = state / "tunnel-key.xml"
    try:
        key_generation = key_path.stat().st_mtime_ns
    except OSError:
        return
    while True:
        connection = None
        try:
            status = json.loads((state / "last-tunnel-status.json").read_text(encoding="utf-8-sig"))
            url = urlsplit(status["health_url"])
            if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
                    or url.username or url.password):
                return
            connection = http.client.HTTPConnection("127.0.0.1", url.port, timeout=30)
            connection.request("GET", "/api/logs/stream", headers={"Accept": "text/event-stream"})
            response = connection.getresponse()
            if response.status != 200:
                raise OSError("Local event stream unavailable")
            while True:
                line = response.readline(65537)
                if not line or len(line) > 65536:
                    break
                if line.startswith(b"data:"):
                    event = json.loads(line[5:])
                    # Ignore old runtime errors after the user has already replaced its key.
                    if invalid_key_event(event) and key_path.stat().st_mtime_ns == key_generation:
                        request("TunnelKey")
        except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
            pass  # Network/parse failures are not proof that credentials expired.
        finally:
            if connection:
                connection.close()
        time.sleep(5)  # Local stream reconnection only; never probes an external service.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manager-dir", required=True)
    parser.add_argument("--request", choices=KINDS)
    parser.add_argument("--clear", choices=KINDS)
    args = parser.parse_args()
    configure(args.manager_dir)
    if args.request:
        request(args.request)
    if args.clear:
        recovered(args.clear)
