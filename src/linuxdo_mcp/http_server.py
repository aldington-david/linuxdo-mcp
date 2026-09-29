"""Authenticated single-account HTTP entry point for a VPS, separate from local stdio."""
import asyncio
from collections import deque
import hmac
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
import uvicorn

from .server import mcp


def read_token(path):
    token = Path(path).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token):
        raise ValueError("MCP 访问密钥缺失或格式不正确，请运行 ./linuxdo.sh setup 或 rotate-token。")
    return token.encode("ascii")


class PrivateGateway:
    """One bounded limiter for one personal account; no IP or forwarded-header trust."""
    def __init__(self, app, token_file, *, requests_per_minute=60, max_inflight=4):
        read_token(token_file)  # Missing credentials must prevent startup.
        if not 1 <= requests_per_minute <= 600 or not 1 <= max_inflight <= 16:
            raise ValueError("请求限制须为 1–600 次/分钟，并发须为 1–16。")
        self.app = app
        self.token_file = token_file
        self.limit = requests_per_minute
        self.recent = deque()
        self.slots = asyncio.Semaphore(max_inflight)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def reject(status, message, **headers):
            await JSONResponse({"error": message}, status_code=status,
                               headers={"Cache-Control": "no-store", **headers})(scope, receive, send)

        if scope["path"] == "/healthz" and scope["method"] == "GET":
            # Process health only; never poll Linux.do from a Docker healthcheck.
            return await JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})(scope, receive, send)
        if scope["path"] != "/mcp":
            return await reject(404, "not_found")
        authorization = [value for name, value in scope["headers"] if name.lower() == b"authorization"]
        try:
            expected = b"Bearer " + read_token(self.token_file)
        except (OSError, ValueError):
            return await reject(503, "authentication_unavailable")
        if len(authorization) != 1 or not hmac.compare_digest(authorization[0], expected):
            return await reject(401, "unauthorized", **{"WWW-Authenticate": 'Bearer realm="linuxdo"'})
        # No persistent SSE channel is needed by this stateless read-only server.
        if scope["method"] != "POST":
            return await reject(405, "method_not_allowed", Allow="POST")
        now = time.monotonic()
        while self.recent and now - self.recent[0] >= 60:
            self.recent.popleft()
        if len(self.recent) >= self.limit:
            return await reject(429, "rate_limited", **{"Retry-After": str(max(1, int(60 - now + self.recent[0]) + 1))})
        if self.slots.locked():
            return await reject(429, "busy", **{"Retry-After": "2"})
        self.recent.append(now)
        async def private_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), (b"cache-control", b"no-store")]}
            await send(message)
        # ponytail: one process/one account; a shared limiter is required before scaling out.
        async with self.slots:
            return await self.app(scope, receive, private_send)


def make_app(public_url, token_file, *, requests_per_minute=60, max_inflight=4):
    parsed = urlsplit(public_url)
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("公网 URL 端口不正确。")
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("LINUXDO_PUBLIC_URL 必须是纯 HTTPS 站点地址，例如 https://linuxdo.example.com。")
    security = TransportSecuritySettings(
        allowed_hosts=[parsed.netloc, "127.0.0.1:*", "localhost:*", "mcp:8787"],
        allowed_origins=[public_url.rstrip("/")],
    )
    app = mcp.streamable_http_app(host="0.0.0.0", stateless_http=True, json_response=True,
                                 max_request_body_size=65536, transport_security=security)
    return PrivateGateway(app, token_file, requests_per_minute=requests_per_minute, max_inflight=max_inflight)


def main():
    app = make_app(os.environ.get("LINUXDO_PUBLIC_URL", ""),
                   os.environ.get("LINUXDO_MCP_TOKEN_FILE", "/data/mcp-token"),
                   requests_per_minute=int(os.environ.get("LINUXDO_REQUESTS_PER_MINUTE", "60")),
                   max_inflight=int(os.environ.get("LINUXDO_MAX_INFLIGHT", "4")))
    uvicorn.run(app, host="0.0.0.0", port=8787, workers=1, proxy_headers=False,
                access_log=False, timeout_keep_alive=5, limit_concurrency=32, backlog=64)


if __name__ == "__main__":
    main()
