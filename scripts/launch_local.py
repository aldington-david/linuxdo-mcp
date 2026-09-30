"""Plugin-contained stdio bootstrap; stdout belongs exclusively to MCP."""
import argparse
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


def tunnel_ready(state):
    """One bounded loopback probe on startup; no timer, forum request, or proxy."""
    connection = None
    try:
        status = json.loads((Path(state) / "last-tunnel-status.json").read_text(encoding="utf-8-sig"))
        url = urlsplit(status["health_url"])
        if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
                or url.username or url.password):
            return False
        connection = http.client.HTTPConnection("127.0.0.1", url.port, timeout=0.5)
        connection.request("GET", "/readyz")
        response = connection.getresponse()
        return response.status == 200 and response.read(64).strip() == b"ready"
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        return False
    finally:
        if connection:
            connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-tunnel", type=Path)
    parser.add_argument("--powershell", default="pwsh.exe")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    if args.start_tunnel:
        if tunnel_ready(args.start_tunnel):
            return 0
        # Invoked by pythonw.exe: neither this process nor its child allocates a console.
        try:
            return subprocess.run(
                [args.powershell, "-NoProfile", "-NonInteractive", "-File",
                 str(root / "Manage-LinuxDo.ps1"), "-Action", "Start", "-Unattended",
                 "-StateDir", str(args.start_tunnel)], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW).returncode
        except OSError:
            (args.start_tunnel / "last-error.json").write_text(json.dumps({
                "action": "Start", "error": "后台管理程序无法启动，请打开 LinuxDo.cmd 检查安装。"
            }, ensure_ascii=False), encoding="utf-8")
            return 1
    runtime = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
    python = runtime["python"]
    if not Path(python).is_file():
        raise SystemExit("Linux.do Python environment is missing; run LinuxDo.cmd to reinstall.")
    state = runtime.get("manager_state")
    if os.name == "nt" and state and (Path(state) / "tunnel-key.xml").is_file() and not tunnel_ready(state):
        try:
            # Task Scheduler owns the Tunnel; closing an MCP job must not kill it.
            subprocess.run(["schtasks.exe", "/Run", "/TN", runtime["tunnel_task"]],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=5)
        except (OSError, subprocess.SubprocessError, KeyError):
            print("Linux.do Tunnel auto-start failed; open LinuxDo.cmd and check its status.", file=sys.stderr)
    command = [python, "-X", "utf8", "-m", "linuxdo_mcp.server"]
    if os.name == "nt":
        # Windows execv starts another PID; keeping the bootstrap alive preserves Codex's process ownership.
        return subprocess.call(command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    os.execv(python, command)


if __name__ == "__main__":
    raise SystemExit(main())
