import hashlib
import os
from typing import Any

import mcp.types as types
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context
from pydantic import BaseModel


mcp = FastMCP(
    json_response=True,
    log_level=os.getenv("LOG_LEVEL", "WARNING").upper(),
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


class CharacterProfileSchema(BaseModel):
    traits: str
    motivation: str


@mcp.tool(description="Return the sandbox identifier for this stateful MCP server.")
def whoami() -> dict[str, Any]:
    sandbox_id = os.getenv("MCP_SESSION_ID")
    return {"sandbox_id": sandbox_id}


@mcp.tool(description="Return deterministic weather information for the given city.")
def get_weather(city: str) -> dict[str, Any]:
    return _deterministic_weather(city)


@mcp.tool(description="Request the client to generate a short story via sampling.")
async def generate_story_with_sampling(
    topic: str,
    style: str = "adventure",
    context: Context | None = None,
) -> dict[str, Any]:
    if context is None:
        return {"error": "Sampling requires request context"}

    capability = types.ClientCapabilities(sampling=types.SamplingCapability())
    if not context.session.check_client_capability(capability):
        return {"error": "Client does not advertise sampling capability"}

    messages = [
        types.SamplingMessage(
            role="user",
            content=types.TextContent(
                type="text",
                text=(
                    f"Write a short {style} story (2-3 paragraphs) about {topic}. "
                    "Include vivid descriptions and engaging dialogue."
                ),
            ),
        )
    ]

    result = await context.session.create_message(
        messages=messages,
        max_tokens=300,
        system_prompt="You are a concise storyteller who responds with plain text only.",
        related_request_id=context.request_id,
    )

    content = result.content
    if isinstance(content, types.TextContent):
        story = content.text
    else:
        story = str(content)

    return {
        "topic": topic,
        "style": style,
        "story": story,
        "model": result.model,
        "stop_reason": result.stopReason or "endTurn",
    }


@mcp.tool(description="Elicit a concise character profile via client-side elicitation.")
async def create_character_profile(
    character: str, context: Context | None = None
) -> dict[str, Any]:
    if context is None:
        return {"error": "Elicitation requires request context"}

    prompt = (
        f"Provide two short bullet points describing {character}: one for personality traits "
        "and one for core motivation."
    )

    elicitation = await context.elicit(prompt, CharacterProfileSchema)

    if elicitation.action != "accept" or elicitation.data is None:
        return {"status": elicitation.action, "character": character}

    profile = elicitation.data.model_dump()
    return {
        "status": "complete",
        "character": character,
        "profile": profile,
    }


if __name__ == "__main__":
    mcp.run()
