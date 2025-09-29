import hashlib
import logging
import os
import sys
from typing import Any

from strands import Agent
from strands.models import BedrockModel

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context
import mcp as mcp_pkg

from utils import SuppressClosedResourceErrors

# Suppress noisy disconnect traces until upstream fix
logging.getLogger("mcp.server.streamable_http").addFilter(
    SuppressClosedResourceErrors()
)


# Initialize FastMCP at module level (needed for decorators)
mcp = FastMCP(
    host="0.0.0.0",
    stateless_http=True,
    json_response=True,
    log_level=os.getenv("LOG_LEVEL", "WARNING"),
    streamable_http_path="/mcp/",
)

# Global instances
model = BedrockModel(model_id="amazon.nova-micro-v1:0")

agent = Agent(
    model=model,
    system_prompt=(
        "You are a witty comedian. Produce short, original, family-friendly jokes about"
        " the requested topic. Responses must stay under 40 words and avoid offensive content."
    ),
)


@mcp.tool()
def get_weather(city: str) -> dict[str, Any]:
    """Get deterministic weather information for a city.

    Returns fake but consistent weather data based on the city name.
    """
    h = int(hashlib.sha256(city.strip().lower().encode("utf-8")).hexdigest(), 16)
    temps = [18, 20, 22, 24, 26, 28]
    conds = ["sunny", "partly cloudy", "overcast", "light rain", "breezy", "clear"]
    wind = ["calm", "light breeze", "moderate breeze", "gusty"]
    return {
        "city": city,
        "temperature_c": temps[h % len(temps)],
        "conditions": conds[(h // 7) % len(conds)],
        "wind": wind[(h // 19) % len(wind)],
    }


@mcp.tool()
def tell_joke(topic: str) -> dict[str, Any]:
    """Return a short joke about a topic using a Bedrock Nova model via Strands."""
    # Use prompt engineering for structured output as recommended for Nova
    prompt = f"""Tell a brief, family-friendly joke about {topic}.
Your response should be only the joke text, nothing else.
Keep it under 40 words."""

    # Call the agent directly with temperature=0 for consistency
    result = agent(prompt)

    # Extract the joke text from the response
    joke_text = str(result).strip()

    # Handle case where result has content attribute
    if hasattr(result, "content"):
        if isinstance(result.content, str):
            joke_text = result.content.strip()

    return {"topic": topic, "message": joke_text}


@mcp.tool()
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


if __name__ == "__main__":
    print("[boot] Demo MCP server starting…", flush=True)
    print(f"[boot] Python: {sys.version}", flush=True)
    print("[boot] Calling FastMCP.run(streamable-http)", flush=True)
    mcp.run(transport="streamable-http")