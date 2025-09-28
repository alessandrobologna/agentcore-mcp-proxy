#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "mcp",
# ]
# ///
"""Run the MCP proxy via stdio and exercise basic MCP calls."""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Sequence

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def _run_smoketest(cmd: Sequence[str], env: dict[str, str]) -> None:
    server_params = StdioServerParameters(command=cmd[0], args=list(cmd[1:]), env=env)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            print("Tools:", tool_names)

            if "whoami" in tool_names:
                whoami_result = await session.call_tool("whoami", {})
                print("Sandbox:", whoami_result.content)

            if "get_weather" in tool_names:
                weather = await session.call_tool("get_weather", {"city": "New York"})
                print("Weather:", weather.content)

            if "tell_joke" in tool_names:
                joke = await session.call_tool("tell_joke", {"topic": "programmers"})
                print("Joke:", joke.content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise the MCP AgentCore proxy via stdio"
    )
    parser.add_argument(
        "agent_arn", help="AgentCore runtime ARN (exported to AGENTCORE_AGENT_ARN)"
    )
    parser.add_argument(
        "--proxy-cmd",
        nargs=argparse.REMAINDER,
        help="Command launching the proxy (default: uvx --from . mcp-agentcore-proxy)",
    )

    args = parser.parse_args()

    cmd = args.proxy_cmd or [
        "uvx",
        "--from",
        ".",
        "mcp-agentcore-proxy",
    ]

    env = os.environ.copy()
    env.setdefault("AGENTCORE_AGENT_ARN", args.agent_arn)

    asyncio.run(_run_smoketest(cmd, env))


if __name__ == "__main__":
    main()
