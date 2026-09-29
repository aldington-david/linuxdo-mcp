"""检查运行中的 HTTP MCP；--live 会读取当前账号并实际搜索、读帖。"""
import argparse
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def check(url, live=False, query="Codex order:latest"):
    async with streamable_http_client(url) as streams:
        async with ClientSession(streams[0], streams[1], read_timeout_seconds=120) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            print(f"MCP: {init.server_info.name}; tools: {len(tools.tools)}")
            if not live:
                return

            async def call(name, arguments):
                result = await session.call_tool(name, arguments)
                if result.is_error:
                    raise RuntimeError(f"{name}: " + " ".join(getattr(c, "text", "") for c in result.content))
                if result.structured_content is None:
                    raise RuntimeError(f"{name}: missing structuredContent")
                return result.structured_content

            user = await call("whoami", {})
            print(f"Login OK; trust level: {user.get('trust_level')}")
            found = await call("search", {"query": query, "pages": 1})
            print(f"Search OK; results: {found['count']}")
            if found["results"]:
                topic = await call("get_topic", {"topic_id": found["results"][0]["topic_id"], "posts": 3})
                print(f"Topic OK; returned: {topic['returned']}; next_start: {topic['next_start']}")
            else:
                print("No matching topics; topic read was not tested.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8787/mcp")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--query", default="Codex order:latest")
    args = parser.parse_args()
    asyncio.run(check(args.url, args.live, args.query))
