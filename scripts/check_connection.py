"""默认自动启动 stdio MCP；--url 检查 HTTP；--live 实际登录、搜索、读帖。"""
import argparse
import asyncio
import os
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


async def check(url=None, live=False, query="Codex order:latest", plugin_dir=None):
    params = StdioServerParameters(command=sys.executable,
                                  args=["-X", "utf8", "-m", "linuxdo_mcp.server"], env=dict(os.environ))
    if plugin_dir:
        root = Path(plugin_dir).resolve()
        config = json.loads((root / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["linuxdo"]
        params = StdioServerParameters(command=config["command"], args=config.get("args", []),
                                      cwd=str(root / config.get("cwd", ".")), env=dict(os.environ))
    transport = streamable_http_client(url) if url else stdio_client(params)
    async with transport as streams:
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
    parser.add_argument("--url", help="可选 HTTP MCP 地址；不填时由脚本启动 stdio 服务")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--query", default="Codex order:latest")
    parser.add_argument("--plugin-dir", help="按实际插件清单启动，验证打包后的启动入口")
    args = parser.parse_args()
    if args.url and args.plugin_dir:
        parser.error("--url 和 --plugin-dir 不能同时使用")
    asyncio.run(check(args.url, args.live, args.query, args.plugin_dir))
