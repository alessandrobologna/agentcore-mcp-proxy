# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "fast-agent-mcp",
# ]
# ///

# this demo uses FastAgent (https://fast-agent.ai/) to create an agent that interacts
# with the stateful mcp server to demonstrate sampling capabilities.
#
import asyncio

from fast_agent import FastAgent

# Create the application
fast = FastAgent("Sampling Demo", quiet=False)


@fast.agent(
    "sampling_demo",
    instruction="""
    You are an agent using the mcp-agentcore-proxy mcp server. Write a short poem about a given topic.
    """,
    servers=["mcp-agentcore-proxy"],
)
async def main() -> None:
    async with fast.run() as agent:
        await agent.sampling_demo.send("topic: a space adventure")


if __name__ == "__main__":
    asyncio.run(main())
