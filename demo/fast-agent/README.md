# FastAgent Demo

This demo uses [FastAgent](https://fast-agent.ai/) to create an AI agent that interacts with the stateful AgentCore MCP server, demonstrating MCP sampling capabilities.

## What is FastAgent?

FastAgent is an open-source Python framework for building AI agents and workflows with native support for the Model Context Protocol (MCP). It provides a simple decorator-based API for defining agents and supports multiple LLM providers (Anthropic, OpenAI, Google, Groq, DeepSeek, and more).

## Prerequisites

- Python 3.13 or newer with [uv](https://docs.astral.sh/uv/) installed
- A deployed stateful AgentCore runtime (see main README for deployment instructions)
- AWS credentials configured (via environment variables, `~/.aws/credentials`, or SSO)
- API key for your chosen LLM provider (OpenAI, Anthropic, etc.)

## Setup

1. **Copy the example configuration:**
   ```bash
   cp fastagent.config.example.yaml fastagent.config.yaml
   ```

2. **Edit `fastagent.config.yaml`:**
   - Replace the `AGENTCORE_AGENT_ARN` with your deployed stateful runtime ARN (from `make outputs` in `demo/` directory)
   - Configure your LLM provider:
     ```yaml
     default_model: "openai.gpt-4o"  # or anthropic.claude-3-5-sonnet-20241022, etc.
     ```
   - Set your API key for the chosen provider
   - See [FastAgent Model Configuration](https://fast-agent.ai/models/) for all supported providers

3. **Set your LLM provider API key:**
   ```bash
   export OPENAI_API_KEY="your-api-key"
   # or for Anthropic:
   export ANTHROPIC_API_KEY="your-api-key"
   ```

## Running the Demo

```bash
cd demo/fast-agent
uv run demo.py
```

The script will automatically:
- Install the `fast-agent-mcp` dependency (declared in the script's PEP 723 metadata)
- Launch the agent with your configured LLM model
- Connect to your stateful AgentCore MCP server via the proxy
- Use MCP sampling to generate a short poem about a space adventure
- Display the generated result with full conversation flow

**Note:** `uv run` handles dependency installation automatically thanks to the inline script metadata in `demo.py`.

## How It Works

The demo showcases:
- **MCP Sampling**: The stateful MCP server requests LLM inference from the client (FastAgent)
- **Bidirectional Communication**: The server initiates requests back to the client through the AgentCore HTTP bridge
- **Session Persistence**: The `RUNTIME_SESSION_MODE=session` maintains state across invocations

## Configuration Reference

The `fastagent.config.yaml` file supports:

**Model Configuration:**
```yaml
default_model: "provider.model"
# Examples:
# - "openai.gpt-4o"
# - "anthropic.claude-3-5-sonnet-20241022"
# - "google.gemini-1.5-pro"
# Aliases: sonnet, sonnet35, opus, gpt-4o, gpt-4o-mini, etc.
```

**MCP Server Configuration:**
```yaml
mcp:
  servers:
    mcp-agentcore-proxy:
      command: "uvx"           # Command to launch the proxy
      args:
        - "mcp-agentcore-proxy"
      env:
        AGENTCORE_AGENT_ARN: "arn:aws:bedrock-agentcore:..."
        RUNTIME_SESSION_MODE: "session"
```

**Logger Configuration:**
```yaml
logger:
  progress_display: true    # Show progress bars
  show_chat: true          # Display conversation
  show_tools: true         # Show tool calls
  truncate_tools: true     # Truncate long responses
```

For all configuration options, see the [FastAgent documentation](https://fast-agent.ai/).

## Troubleshooting

- **Connection errors**: Verify your `AGENTCORE_AGENT_ARN` is correct and the runtime is deployed
- **Authentication errors**: Ensure AWS credentials are properly configured
- **Model errors**: Check that your configured LLM provider and API keys are set up correctly
