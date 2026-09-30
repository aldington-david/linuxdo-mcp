"""45-second end-to-end stdio check using a synthetic slow forum, never Linux.do."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def serve():
    from linuxdo_mcp import cookies, server
    cookies._write_cache("_t=offline-fixture", validated_at=time.time())
    def slow_get(url, **kwargs):
        page = int(server.urllib.parse.parse_qs(server.urllib.parse.urlsplit(url).query)["page"][0])
        time.sleep(min(20, kwargs["timeout"]))
        if kwargs["timeout"] < 20:
            raise server.creq.RequestsError("offline simulated timeout")
        return SimpleNamespace(status_code=200, cookies={}, headers={}, text=json.dumps({
            "topics": [{"id": page, "title": "offline fixture"}], "posts": [{"topic_id": page}],
            "grouped_search_result": {"term": "fixture", "more_full_page_results": True}}))
    server.creq.get = slow_get
    server.mcp.run()


async def check():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    with tempfile.TemporaryDirectory() as tmp:
        params = StdioServerParameters(command=sys.executable,
            args=[str(Path(__file__).resolve()), "--serve"],
            env={**os.environ, "LINUXDO_CACHE_DIR": tmp, "LINUXDO_READ_BROWSER": "0", "LINUXDO_COOKIE": ""})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=60) as session:
                await session.initialize()
                started = time.monotonic()
                result = await session.call_tool("search", {"query": "fixture", "pages": 5})
                elapsed = time.monotonic() - started
                data = result.structured_content
                assert not result.is_error, result
                assert data["partial"] and data["pages_returned"] == 2 and data["next_page"] == 3, data
                assert data["stop_reason"] == "time_budget_exceeded", data
                assert 44 <= elapsed < 50, elapsed
                print(json.dumps({"transport": "stdio", "client_timeout_seconds": 60,
                    "elapsed_seconds": round(elapsed, 3), "pages_returned": data["pages_returned"],
                    "next_page": data["next_page"], "partial": data["partial"]}))


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        asyncio.run(check())
