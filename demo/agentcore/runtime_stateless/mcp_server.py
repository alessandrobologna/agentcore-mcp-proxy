import hashlib
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from utils import SuppressClosedResourceErrors

# Suppress noisy disconnect traces until upstream fix
logging.getLogger("mcp.server.streamable_http").addFilter(
    SuppressClosedResourceErrors()
)

mcp = FastMCP(
    host="0.0.0.0",
    stateless_http=True,
    json_response=True,
    log_level=os.getenv("LOG_LEVEL", "WARNING").upper(),
    streamable_http_path="/mcp",
)


def _deterministic_weather(city: str) -> dict[str, Any]:
    seed = hashlib.sha256(city.strip().lower().encode("utf-8")).hexdigest()
    h = int(seed, 16)
    temps = [18, 20, 22, 24, 26, 28]
    conds = ["sunny", "partly cloudy", "overcast", "light rain", "breezy", "clear"]
    wind = ["calm", "light breeze", "moderate breeze", "gusty"]
    return {
        "city": city,
        "temperature_c": temps[h % len(temps)],
        "conditions": conds[(h // 7) % len(conds)],
        "wind": wind[(h // 19) % len(wind)],
    }


@mcp.tool(description="Return the sandbox identifier for this MCP server.")
def whoami(context: Context | None = None) -> dict[str, Any]:
    """Return the sandbox identifier for this MCP demo server."""

    sandbox_id: str | None = None
    if context is not None:
        try:
            request = context.request_context.request
        except ValueError:
            request = None
        if request is not None:
            sandbox_id = request.headers.get("mcp-session-id")

    return {"sandbox_id": sandbox_id}


@mcp.tool(description="Return deterministic weather information for the given city.")
def get_weather(city: str) -> dict[str, Any]:
    """Return deterministic weather information for a city."""

    return _deterministic_weather(city)


@mcp.tool(description="Issue a completion request asking the client to draft a story.")
def request_story(topic: str, style: str = "adventure") -> dict[str, Any]:
    """Request the client to draft a story about the given topic."""

    prompt = (
        f"Write a short {style} story (2-3 paragraphs) about {topic}. "
        "Include vivid descriptions and engaging dialogue."
    )

    return {
        "status": "completion_required",
        "prompt": prompt,
        "task": "story_generation",
        "parameters": {"topic": topic, "style": style},
        "instructions": "Return the full story text in plain text format.",
    }


@mcp.tool(description="Receive the client-generated story and summarize it.")
def submit_story(topic: str, style: str, story: str) -> dict[str, Any]:
    """Receive the client-generated story and summarize it."""

    word_count = len(story.split())
    preview = story[:120] + "..." if len(story) > 120 else story
    return {
        "status": "complete",
        "result": "Story generation complete",
        "topic": topic,
        "style": style,
        "word_count": word_count,
        "preview": preview,
    }


@mcp.tool(description="Ask the client to provide character details via completion.")
def request_character_profile(character: str) -> dict[str, Any]:
    """Ask the client to provide character details via elicitation."""

    prompt = (
        f"Ask the user to describe the character {character}. "
        f"Request the following information from the user:"
        "\n1. Personality traits"
        "\n2. Core motivation"
        "\n\nCollect this information from the user and then call submit_character_profile with their responses."
    )

    return {
        "status": "elicitation_required",
        "prompt": prompt,
        "character": character,
        "fields": [
            {
                "name": "traits",
                "description": "Key personality traits",
                "type": "string",
            },
            {
                "name": "motivation",
                "description": "Primary goal or motivation",
                "type": "string",
            },
        ],
    }


@mcp.tool(description="Receive character details supplied by the client.")
def submit_character_profile(
    character: str, traits: str, motivation: str
) -> dict[str, Any]:
    """Receive elicited character details from the client."""

    return {
        "status": "complete",
        "character": character,
        "profile": {"traits": traits, "motivation": motivation},
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
