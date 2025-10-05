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
from typing import Any, Iterable, Sequence

import click

from mcp import ClientSession
from mcp.types import (
    ContentBlock,
    CreateMessageRequestParams,
    CreateMessageResult,
    ElicitRequestParams,
    ElicitResult,
    TextContent,
)
from mcp.client.session import RequestContext
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import McpError


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


def _first_json(blocks: Iterable[ContentBlock]) -> dict | list | None:
    """Return the first block that parses as JSON, if any."""

    for block in blocks:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


async def _sampling_callback(
    ctx: "RequestContext[ClientSession, Any]", params: CreateMessageRequestParams
) -> CreateMessageResult:
    """Return a deterministic summary for sampling requests."""

    del ctx  # unused but part of callback signature

    pieces: list[str] = []
    for message in params.messages:
        content = getattr(message, "content", None)
        if isinstance(content, TextContent):
            pieces.append(content.text)

    joined = " ".join(pieces) if pieces else "(no content)"
    lower_joined = joined.lower()
    if "write a short" in lower_joined and "story" in lower_joined:
        text = "A guide followed the river at dusk, helping travelers cross safely before resting beside the water."
    else:
        text = f"Smoketest summary: {joined[:160]}"

    return CreateMessageResult(
        role="assistant",
        content=TextContent(type="text", text=text),
        model="smoketest-client",
        stopReason="endTurn",
    )


async def _elicitation_callback(
    ctx: "RequestContext[ClientSession, Any]", params: ElicitRequestParams
) -> ElicitResult:
    del ctx
    schema = params.requestedSchema or {}
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}

    content: dict[str, str] = {}
    if "traits" in properties:
        content["traits"] = "Curious and courageous"
    if "motivation" in properties:
        content["motivation"] = "Protect her community"

    if not content:
        content = {k: "sample" for k in properties.keys()}

    return ElicitResult(action="accept", content=content)


async def _exercise_stateless(session: ClientSession, tool_names: list[str]) -> None:
    click.secho("\nWhoami", fg="cyan", bold=True)
    if "whoami" in tool_names:
        whoami_result = await session.call_tool("whoami", {})
        for block in _format_content(whoami_result.content):
            click.echo(block)
    else:
        click.secho("  ↳ whoami not available on runtime", fg="yellow")

    click.secho("\nWeather", fg="cyan", bold=True)
    if "get_weather" in tool_names:
        weather = await session.call_tool("get_weather", {"city": "Seattle"})
        for block in _format_content(weather.content):
            click.echo(block)
    else:
        click.secho("  ↳ get_weather not available on runtime", fg="yellow")

    click.secho("\nStory", fg="cyan", bold=True)
    if {"request_story", "submit_story"}.issubset(set(tool_names)):
        story_request = await session.call_tool(
            "request_story", {"topic": "rivers", "style": "adventure"}
        )
        for block in _format_content(story_request.content):
            click.echo(block)

        story_text = "Once upon a time, a curious guide followed a river through the forest, helping every traveler she met."
        story_submit = await session.call_tool(
            "submit_story",
            {"topic": "rivers", "style": "adventure", "story": story_text},
        )
        for block in _format_content(story_submit.content):
            click.echo(block)
    else:
        click.secho(
            "  ↳ request_story/submit_story not available on runtime", fg="yellow"
        )

    click.secho("\nElicitation", fg="cyan", bold=True)
    if {"request_character_profile", "submit_character_profile"}.issubset(
        set(tool_names)
    ):
        character = "Aria"
        elicitation_request = await session.call_tool(
            "request_character_profile", {"character": character}
        )
        for block in _format_content(elicitation_request.content):
            click.echo(block)

        elicitation_submit = await session.call_tool(
            "submit_character_profile",
            {
                "character": character,
                "traits": "Curious and courageous",
                "motivation": "Protect her community",
            },
        )
        for block in _format_content(elicitation_submit.content):
            click.echo(block)
    else:
        click.secho(
            "  ↳ request_character_profile/submit_character_profile not available",
            fg="yellow",
        )


async def _exercise_stateful(session: ClientSession, tool_names: list[str]) -> None:
    click.secho("\nWhoami", fg="cyan", bold=True)
    if "whoami" in tool_names:
        whoami_result = await session.call_tool("whoami", {})
        for block in _format_content(whoami_result.content):
            click.echo(block)
    else:
        click.secho("  ↳ whoami not available on runtime", fg="yellow")

    click.secho("\nWeather", fg="cyan", bold=True)
    if "get_weather" in tool_names:
        weather = await session.call_tool("get_weather", {"city": "Seattle"})
        for block in _format_content(weather.content):
            click.echo(block)
    else:
        click.secho("  ↳ get_weather not available on runtime", fg="yellow")

    click.secho("\nSampling", fg="cyan", bold=True)
    if "generate_story_with_sampling" in tool_names:
        story = await session.call_tool(
            "generate_story_with_sampling",
            {"topic": "rivers", "style": "adventure"},
        )
        for block in _format_content(story.content):
            click.echo(block)
    else:
        click.secho(
            "  ↳ generate_story_with_sampling not available on runtime", fg="yellow"
        )

    click.secho("\nElicitation", fg="cyan", bold=True)
    if "create_character_profile" in tool_names:
        profile = await session.call_tool(
            "create_character_profile", {"character": "Aria"}
        )
        for block in _format_content(profile.content):
            click.echo(block)
    else:
        click.secho(
            "  ↳ create_character_profile not available on runtime", fg="yellow"
        )


async def _run_smoketest(cmd: Sequence[str], env: dict[str, str], mode: str) -> None:
    server_params = StdioServerParameters(command=cmd[0], args=list(cmd[1:]), env=env)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read,
            write,
            sampling_callback=_sampling_callback,
            elicitation_callback=_elicitation_callback,
        ) as session:
            try:
                await session.initialize()
            except McpError as exc:
                click.secho("Initialization failed", fg="red", bold=True)
                click.secho(str(exc), fg="yellow")
                return

            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            click.secho("Tools", fg="cyan", bold=True)
            for tool in tool_names:
                click.echo(f"  • {tool}")

            if mode == "stateful":
                await _exercise_stateful(session, tool_names)
            else:
                await _exercise_stateless(session, tool_names)


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
    parser.add_argument(
        "--mode",
        choices=["stateless", "stateful"],
        default="stateless",
        help="Which runtime scenario to exercise (default: stateless)",
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
    if args.mode == "stateful":
        env.setdefault("RUNTIME_SESSION_MODE", "session")

    asyncio.run(_run_smoketest(cmd, env, args.mode))


if __name__ == "__main__":
    main()
