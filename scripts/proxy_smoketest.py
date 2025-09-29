#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "click",
#     "mcp",
# ]
# ///
"""Run the MCP proxy via stdio and exercise basic MCP calls."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Iterable, Sequence

import click

from mcp import ClientSession
from mcp.types import ContentBlock
from mcp.client.stdio import StdioServerParameters, stdio_client


def _format_content(blocks: Iterable[ContentBlock]) -> list[str]:
    """Convert MCP content blocks into human-friendly strings."""

    formatted: list[str] = []
    for block in blocks:
        text = getattr(block, "text", None)
        if text is None:
            continue

        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            pass

        formatted.append(text)

    return formatted


async def _run_smoketest(cmd: Sequence[str], env: dict[str, str]) -> None:
    server_params = StdioServerParameters(command=cmd[0], args=list(cmd[1:]), env=env)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            click.secho("Tools", fg="cyan", bold=True)
            for tool in tool_names:
                click.echo(f"  • {tool}")

            if "whoami" in tool_names:
                whoami_result = await session.call_tool("whoami", {})
                formatted = _format_content(whoami_result.content)
                click.secho("\nSandbox", fg="cyan", bold=True)
                for block in formatted:
                    click.echo(block)

            if "get_weather" in tool_names:
                weather = await session.call_tool("get_weather", {"city": "New York"})
                formatted = _format_content(weather.content)
                click.secho("\nWeather", fg="cyan", bold=True)
                for block in formatted:
                    click.echo(block)

            if "tell_joke" in tool_names:
                joke = await session.call_tool("tell_joke", {"topic": "programmers"})
                formatted = _format_content(joke.content)
                click.secho("\nJoke", fg="cyan", bold=True)
                for block in formatted:
                    click.echo(block)


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
        "--with-editable",
        ".",
        "--from",
        ".",
        "mcp-agentcore-proxy",
    ]

    env = os.environ.copy()
    env.setdefault("AGENTCORE_AGENT_ARN", args.agent_arn)

    asyncio.run(_run_smoketest(cmd, env))


if __name__ == "__main__":
    main()
