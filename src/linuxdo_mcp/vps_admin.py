"""Local Docker operator commands. These operations are never MCP tools or HTTP routes."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile

from . import cookies
from .http_server import read_token


def save_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            temporary.chmod(0o600)
            stream.write(value)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "rotate-token", "show-token", "tunnel-key", "check-tunnel"))
    parser.add_argument("--tunnel-id")
    args = parser.parse_args()
    path = Path(os.environ.get("LINUXDO_MCP_TOKEN_FILE", "/data/mcp-token"))
    if args.action in ("tunnel-key", "check-tunnel"):
        profile_path = cookies.CACHE.parent / "tunnel.json"
        key_path = cookies.CACHE.parent / "tunnel-api-key"
        if args.action == "tunnel-key":
            if not re.fullmatch(r"tunnel_[a-f0-9]{32}", args.tunnel_id or ""):
                parser.error("请提供真实的 tunnel_ 开头的 Tunnel ID。")
            token = sys.stdin.read(4097).strip()
            if not 20 <= len(token) <= 4096 or any(c.isspace() for c in token):
                parser.error("运行密钥为空、过长或含空白，未保存。")
            tunnel_id = args.tunnel_id
        else:
            try:
                tunnel_id = json.loads(profile_path.read_text())["control_plane"]["tunnel_id"]
                token = key_path.read_text().strip()
            except (OSError, ValueError, KeyError):
                raise SystemExit(2)
        checked = subprocess.run(["tunnel-client", "admin", "--json", "tunnels", "get", tunnel_id],
                                 env={**os.environ, "CONTROL_PLANE_API_KEY": token},
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
        if checked.returncode:
            print("Tunnel 验证未通过：检查网络、密钥有效期和 Tunnels Read + Use 权限；旧配置未替换。")
            raise SystemExit(3)
        if args.action == "tunnel-key":
            profile = {"config_version": 1,
                       "control_plane": {"base_url": "https://api.openai.com", "tunnel_id": tunnel_id,
                                         "api_key": "file:" + str(key_path)},
                       "health": {"listen_addr": "127.0.0.1:8788"},
                       "admin_ui": {"open_browser": False}, "log": {"level": "warn", "format": "json"},
                       "mcp": {"commands": [{"channel": "main", "command": "/usr/local/bin/python -m linuxdo_mcp.server"}]}}
            save_private(key_path, token + "\n")
            save_private(profile_path, json.dumps(profile, ensure_ascii=False))
        print("Tunnel 元数据读取成功；启动后仍需从 ChatGPT 实际验证工具调用。")
        return
    with cookies.locked():
        if args.action == "init" and path.exists():
            read_token(path)
            print("已有 MCP 访问密钥，已保留。")
        elif args.action in ("init", "rotate-token"):
            save_private(path, secrets.token_urlsafe(48) + "\n")
            print("MCP 访问密钥已保存；不会写入服务日志。")
        else:
            print(read_token(path).decode("ascii"))


if __name__ == "__main__":
    main()
