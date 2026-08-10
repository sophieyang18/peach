from __future__ import annotations

import argparse
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


REQUIRED_TOOLS = {
    "peach_chat",
    "peach_start_interview",
    "peach_answer_interview",
    "peach_finish_interview",
    "peach_generate_resume",
    "peach_profile_snapshot",
}


async def verify(url: str, call_tool: bool) -> None:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            missing = sorted(REQUIRED_TOOLS - set(tool_names))

            print("MCP initialize: ok")
            print("MCP tools:", ", ".join(tool_names))
            if missing:
                raise SystemExit(f"Missing required tools: {', '.join(missing)}")

            if call_tool:
                result = await session.call_tool("peach_profile_snapshot", {"username": "Apple01"})
                content = result.content[0].text if result.content else "{}"
                print("peach_profile_snapshot:", content[:800])
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError as exc:
                    raise SystemExit(f"Tool returned non-JSON content: {exc}") from exc
                if not payload.get("ok"):
                    raise SystemExit(f"Tool returned ok=false: {payload}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Peach Streamable HTTP MCP endpoint.")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/mcp/",
        help="Public or local MCP URL. Use the trailing slash for CloudBaseRun.",
    )
    parser.add_argument("--call-tool", action="store_true", help="Also call peach_profile_snapshot.")
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.call_tool))


if __name__ == "__main__":
    main()
