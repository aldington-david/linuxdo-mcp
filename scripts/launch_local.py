"""Plugin-contained stdio bootstrap; stdout belongs exclusively to MCP."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    runtime = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
    python = runtime["python"]
    if not Path(python).is_file():
        raise SystemExit("Linux.do Python environment is missing; run LinuxDo.cmd to reinstall.")
    state = runtime.get("manager_state")
    if os.name == "nt" and state and (Path(state) / "tunnel-key.xml").is_file():
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
