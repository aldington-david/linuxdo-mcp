"""Integration probe for the isolated Docker fixtures, using stdin for its synthetic token."""
import argparse
import json
import socket
import ssl
import sys
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

parser = argparse.ArgumentParser()
parser.add_argument("--http-port", type=int, required=True)
parser.add_argument("--https-port", type=int, required=True)
parser.add_argument("--ca", required=True)
args = parser.parse_args()
token = sys.stdin.read().strip()
assert len(token) >= 43
ssl_context = ssl.create_default_context(cafile=args.ca)
opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl_context))
original_dns = socket.getaddrinfo

def dns(host, *values, **kwargs):
    return original_dns("127.0.0.1" if host == "linuxdo.test" else host, *values, **kwargs)

def request(base, data=b"{}", auth=True, headers=None):
    supplied = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}
    if auth:
        supplied["Authorization"] = "Bearer " + token
    supplied.update(headers or {})
    req = Request(base + "/mcp", data=data, headers=supplied)
    try:
        with opener.open(req, timeout=15) as response:
            return response.status, response.read(), response.headers
    except HTTPError as exc:
        with exc:
            return exc.code, exc.read(), exc.headers

def rpc(base, method, params, identifier=1):
    body = json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}).encode()
    status, payload, headers = request(base, body)
    assert status == 200, (method, status)
    assert "no-store" in headers.get("Cache-Control", "")
    result = json.loads(payload)
    assert "error" not in result, method
    return result["result"]

with patch.object(socket, "getaddrinfo", side_effect=dns):
    for base in (f"http://127.0.0.1:{args.http_port}", f"https://linuxdo.test:{args.https_port}"):
        assert request(base, auth=False)[0] == 401
        assert request(base, headers={"Authorization": "Bearer wrong"})[0] == 401
        assert request(base, headers={"Origin": "https://evil.test"})[0] == 403
        assert request(base, b" " * 65537)[0] == 413
        result = rpc(base, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "vps-probe", "version": "1"}})
        assert result["serverInfo"]["name"] == "linuxdo"
        tools = rpc(base, "tools/list", {})["tools"]
        assert len(tools) == 13
        identity = rpc(base, "tools/call", {"name": "whoami", "arguments": {}})
        assert not identity.get("isError")
        assert identity["structuredContent"]["username"] == "reader"
        found = rpc(base, "tools/call", {"name": "search", "arguments": {"query": "test"}})
        assert found["structuredContent"]["results"][0]["topic_id"] == 42
    assert request(f"http://127.0.0.1:{args.http_port}", headers={"Host": "evil.test"})[0] == 421
print("PASS: real HTTP and verified HTTPS, auth, Host/Origin, 64 KiB limit, MCP discovery and fixture calls.")
