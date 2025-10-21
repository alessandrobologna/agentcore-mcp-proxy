# Amazon Bedrock AgentCore MCP Proxy

## Overview

This repository addresses two limitations in Amazon Bedrock AgentCore when running MCP servers:

1. **IAM Authentication**: AgentCore requires OAuth 2.0 or Cognito for authentication through the gateway.[^gateway-inbound][^cognito-auth] Developer workstations typically use IAM credentials via Identity Center instead. This repository packages a local stdio proxy that signs requests with SigV4, allowing direct invocation of the AgentCore runtime API[^runtime-how] without configuring OIDC providers or VPC access.

2. **Stateful Bidirectional MCP**: AgentCore's native MCP protocol support is stateless. MCP sampling (server-to-client LLM requests) and elicitation (schema-driven data collection) require persistent sessions. This repository provides an HTTP-to-STDIO bridge that maintains a subprocess across invocations, enabling bidirectional MCP flows within AgentCore's serverless infrastructure.

The local proxy handles IAM authentication and presents a standard MCP stdio interface to clients. Two deployment models are provided for the AgentCore runtime:
- **Stateless**: Direct MCP server for simple request/response tools
- **Stateful**: HTTP bridge maintaining a persistent MCP subprocess for sampling and elicitation workflows


[![PyPI version](https://img.shields.io/pypi/v/mcp-agentcore-proxy.svg?style=flat-square)](https://pypi.org/project/mcp-agentcore-proxy/)
[![Python versions](https://img.shields.io/pypi/pyversions/mcp-agentcore-proxy.svg?style=flat-square)](https://pypi.org/project/mcp-agentcore-proxy/)
[![CI](https://img.shields.io/github/actions/workflow/status/alessandrobologna/agentcore-mcp-proxy/ci.yml?branch=main&style=flat-square)](https://github.com/alessandrobologna/agentcore-mcp-proxy/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

## Quick Start

If you already have an MCP server deployed on Amazon AgentCore Runtime, you can install the MCP proxy in VS Code with one click:

[![Install on VS Code](https://img.shields.io/badge/VS_Code-Install%20on%20VS%20Code-007ACC?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=agentcoreMcpProxy&inputs=%5B%7B%22type%22%3A%22promptString%22%2C%22id%22%3A%22agentArn%22%2C%22description%22%3A%22Enter%20the%20required%20AGENTCORE_AGENT_ARN%22%2C%22password%22%3Afalse%7D%2C%7B%22type%22%3A%22promptString%22%2C%22id%22%3A%22assumeRoleArn%22%2C%22description%22%3A%22Optional%20AGENTCORE_ASSUME_ROLE_ARN%20%28press%20Enter%20to%20skip%29%22%2C%22password%22%3Afalse%7D%5D&config=%7B%22name%22%3A%22agentcoreMcpProxy%22%2C%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22mcp-agentcore-proxy%22%5D%2C%22env%22%3A%7B%22AGENTCORE_AGENT_ARN%22%3A%22%24%7Binput%3AagentArn%7D%22%2C%22AGENTCORE_ASSUME_ROLE_ARN%22%3A%22%24%7Binput%3AassumeRoleArn%7D%22%7D%7D) [![Install on VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Install%20on%20VS%20Code%20Insiders-00B56A?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=agentcoreMcpProxy&inputs=%5B%7B%22type%22%3A%22promptString%22%2C%22id%22%3A%22agentArn%22%2C%22description%22%3A%22Enter%20the%20required%20AGENTCORE_AGENT_ARN%22%2C%22password%22%3Afalse%7D%2C%7B%22type%22%3A%22promptString%22%2C%22id%22%3A%22assumeRoleArn%22%2C%22description%22%3A%22Optional%20AGENTCORE_ASSUME_ROLE_ARN%20%28press%20Enter%20to%20skip%29%22%2C%22password%22%3Afalse%7D%5D&config=%7B%22name%22%3A%22agentcoreMcpProxy%22%2C%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22mcp-agentcore-proxy%22%5D%2C%22env%22%3A%7B%22AGENTCORE_AGENT_ARN%22%3A%22%24%7Binput%3AagentArn%7D%22%2C%22AGENTCORE_ASSUME_ROLE_ARN%22%3A%22%24%7Binput%3AassumeRoleArn%7D%22%7D%7D&quality=insiders)

You'll be prompted to enter your AgentCore Agent ARN during installation. Leave the assume role ARN empty if not using cross-account access. The server name in the VSCode `.mcp.json` will be `agentcoreProxy`. Rename it to something that reflect the actual MCP server that you are proxying. 

>[!TIP] 
> **Need a runtime ARN?** Deploy sample runtimes from the [`demo/` directory](demo/README.md), or see the [Installation](#installation) section for detailed setup instructions.

## Architecture

### Stateless Model

The stateless model runs an MCP server directly inside the AgentCore runtime. Each `InvokeAgentRuntime` call[^invoke-api] creates a new execution context.

```mermaid
sequenceDiagram
    participant Client as MCP Client
    participant Proxy as IAM Proxy (STDIO)
    participant AgentCore as AgentCore Runtime
    participant Server as MCP Server

    Client->>Proxy: tools/call request
    Proxy->>AgentCore: InvokeAgentRuntime (SigV4)
    AgentCore->>Server: MCP over HTTPS
    Server-->>AgentCore: Tool result
    AgentCore-->>Proxy: SSE stream
    Proxy-->>Client: JSON-RPC response
```

The proxy translates MCP JSON-RPC requests into `InvokeAgentRuntime` API calls. Responses stream back as server-sent events and are forwarded to the client as JSON-RPC messages.

**Appropriate for:**
- Deterministic functions (weather lookup, calculations)
- Stateless API calls
- Simple data transformations

### Stateful Model

The stateful model runs an HTTP-to-STDIO bridge inside the AgentCore runtime. The bridge spawns and maintains a persistent MCP server subprocess. This subprocess persists across multiple `InvokeAgentRuntime` calls with the same `runtimeSessionId`, enabling stateful conversations and bidirectional MCP flows.

```mermaid
sequenceDiagram
    participant Client as MCP Client
    participant Proxy as IAM Proxy (STDIO)
    participant AgentCore as AgentCore Runtime
    participant Bridge as HTTP Bridge
    participant Child as MCP Server (subprocess)

    Client->>Proxy: tools/call (generate_story)
    Proxy->>AgentCore: InvokeAgentRuntime (session-123)
    AgentCore->>Bridge: POST /invocations
    Bridge->>Child: MCP over stdio

    Note over Child: Server initiates sampling

    Child-->>Bridge: sampling/createMessage
    Bridge-->>AgentCore: Sampling request
    AgentCore-->>Proxy: SSE stream
    Proxy-->>Client: Sampling request

    Client->>Proxy: LLM result
    Proxy->>AgentCore: InvokeAgentRuntime (session-123)
    AgentCore->>Bridge: POST /invocations
    Bridge->>Child: Result (same subprocess)
    Child-->>Bridge: Final response
    Bridge-->>AgentCore: Tool result
    AgentCore-->>Proxy: SSE stream
    Proxy-->>Client: JSON-RPC response
```

The bridge maintains the subprocess for the lifetime of the AgentCore microVM. Session affinity is achieved by passing the same `runtimeSessionId` in subsequent `InvokeAgentRuntime` calls.

**Appropriate for:**
- MCP sampling (server-initiated LLM calls)
- MCP elicitation (structured data collection with Pydantic schemas)
- Multi-turn conversations requiring session state
- Workflows requiring persistent context

## Deployment Model Comparison

| Feature | Stateless | Stateful |
|---------|-----------|----------|
| AgentCore Protocol | MCP | HTTP |
| Session State | No | Yes |
| Sampling Support | No | Yes |
| Elicitation Support | No | Yes |
| Subprocess Lifecycle | Per-request | Per-session |
| Memory Overhead | Lower | Higher |

Choose the deployment model based on whether tools require bidirectional MCP features or session state.

## Repository Layout
- `src/mcp_agentcore_proxy/` - MCP STDIO proxy (published as `mcp-agentcore-proxy` on PyPI)
- `demo/` - Demo implementations and testing utilities ([see demo README](demo/README.md))
  - `agentcore/` - Sample AgentCore runtime deployments (stateless and stateful)
  - `scripts/` - Smoke test utilities
  - `fast-agent/` - FastAgent AI agent demo
- `tests/` - Unit tests for the proxy

## Prerequisites
- Python 3.11 or newer with [uv](https://github.com/astral-sh/uv)
- AWS credentials with permission to call `sts:GetCallerIdentity` and `bedrock-agentcore:InvokeAgentRuntime`
- An AgentCore runtime ARN (deploy your own from `demo/` or use an existing one)

## Installation

**From PyPI (recommended):**
```bash
pip install mcp-agentcore-proxy
```

**From source (for development):**
```bash
git clone https://github.com/alessandrobologna/agentcore-mcp-proxy
cd agentcore-mcp-proxy
uv pip install -e .
```

## Configuration

Set the runtime ARN and region:
```bash
export AGENTCORE_AGENT_ARN="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/example"
export AWS_REGION="us-east-1"
```

> **Need a runtime?** Deploy the sample runtimes from the [`demo/` directory](demo/README.md).

## Running the Proxy with an MCP Client

The proxy can be invoked directly with `uvx`.

**From PyPI (recommended for production use):**
```bash
# Latest version
uvx mcp-agentcore-proxy

# Pinned version
uvx mcp-agentcore-proxy@0.1.0
```

**From GitHub (for latest unreleased changes):**
```bash
uvx --from git+https://github.com/alessandrobologna/agentcore-mcp-proxy mcp-agentcore-proxy
```

**From local clone (for development):**
```bash
uvx --from . mcp-agentcore-proxy
```

The proxy validates IAM credentials with `sts:GetCallerIdentity`, derives an AgentCore `runtimeSessionId`, and relays MCP messages to the remote runtime. Standard output carries the JSON-RPC responses. Errors surface as structured MCP error payloads.

### Session modes
Control how session identifiers are generated with `RUNTIME_SESSION_MODE` (default: `session`):
- `session` creates a random session ID once when the proxy starts (recommended for stateful runtimes).
- `identity` hashes the caller identity returned by `sts:GetCallerIdentity` so multiple proxy invocations under the same IAM principal can reuse a warm runtime.
- `request` generates a new session ID for every MCP request (fully stateless, mainly for testing).

### VS Code MCP Client Example
Configure VS Code MCP to launch the proxy with `uvx` and a pre-set runtime ARN. Replace the ARN value with the runtime you deploy.

**Option 1: Install from PyPI (recommended)**

Install the latest published version:
```json
{
  "servers": {
    "mcp-proxy": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-agentcore-proxy"
      ],
      "env": {
        "AGENTCORE_AGENT_ARN": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/example"
      }
    }
  }
}
```

To pin to a specific version:
```json
{
  "servers": {
    "mcp-proxy": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "mcp-agentcore-proxy@0.1.0"
      ],
      "env": {
        "AGENTCORE_AGENT_ARN": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/example"
      }
    }
  }
}
```

**Option 2: Install from GitHub (development/latest)**

For the latest unreleased changes:
```json
{
  "servers": {
    "mcp-proxy": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/alessandrobologna/agentcore-mcp-proxy",
        "mcp-agentcore-proxy"
      ],
      "env": {
        "AGENTCORE_AGENT_ARN": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/example"
      }
    }
  },
  "inputs": []
}
```

## Cross-Account Use (Assume Role)

The proxy can assume an IAM role before invoking AgentCore:

```bash
export AGENTCORE_ASSUME_ROLE_ARN="arn:aws:iam::111122223333:role/AgentCoreProxyInvokeRole"
export AGENTCORE_ASSUME_ROLE_SESSION_NAME="mySession"  # Optional, defaults to "mcpAgentCoreProxy"
```

The assumed role must:
- Trust the calling principal via its trust policy
- Allow `bedrock-agentcore:InvokeAgentRuntime` on the target runtime(s)

See the [demo README](demo/README.md#cross-account-testing) for a complete cross-account testing example.

## Deploying Sample Runtimes

This repository includes sample stateless and stateful AgentCore runtimes for testing. See the **[demo/ directory](demo/README.md)** for:
- Deployment instructions
- Bidirectional MCP examples (sampling/elicitation)
- Building custom stateful runtimes
- Smoke testing

## Development

### Running Tests

Install dev dependencies:
```bash
uv pip install -e ".[dev,server]"
```

Run tests and quality checks:
```bash
make test          # Run all tests, linting, and formatting checks
make lint          # Ruff linting only
make format        # Apply Ruff formatting
make quality       # Lint + formatting check
```

Or directly:
```bash
uv run pytest tests/ -v
uvx ruff check .
uvx ruff format
```

### Contributing

- Keep CLI output flushed to STDOUT to avoid blocking MCP clients
- Add tests for new features in `tests/`
- Use `uvx --from . mcp-agentcore-proxy` for fast iteration
- `src/mcp_agentcore_proxy/version.py` is auto-generated—don't edit or track it

### Release Process

1. Bump `version` in `pyproject.toml`
2. Create PR and merge to `main`
3. CI automatically:
   - Runs tests on Python 3.11, 3.12, 3.13
   - Publishes to PyPI (if `PYPI_API_TOKEN` secret is configured)
   - Tags the release as `v<version>`

## Advanced Features

### Handshake Replay (Resilience)

When connecting to stateful runtimes, the proxy automatically handles container restarts transparently:

- Caches the last `initialize` payload from the client
- On `-32602` errors (uninitialized server), re-sends `initialize` and `notifications/initialized`
- Retries the original request
- Emits MCP log notifications describing the replay

This keeps sessions working across infrequent container restarts without manual intervention.

**Debug logging:**
Set `LOG_LEVEL=DEBUG` or `MCP_PROXY_DEBUG=1` for detailed replay information on STDERR.

## Troubleshooting
- `Set AGENTCORE_AGENT_ARN (or AGENT_ARN)` indicates the environment variable is missing
- `Unable to call sts:GetCallerIdentity` points to missing IAM credentials or wrong region
- `InvokeAgentRuntime error` payloads mirror the AWS API response; inspect the JSON for permission or runtime issues
- Empty responses usually mean the remote AgentCore runtime closed the stream without data; confirm the deployed server accepts MCP requests
 - `-32602 Invalid request parameters` on `tools/call` after a redeploy means the child server has not been initialized yet. The CLI proxy will auto-replay `initialize` and `notifications/initialized` once and retry; otherwise, restart your MCP session.
 - Assume role errors: verify `AGENTCORE_ASSUME_ROLE_ARN` is correct, your caller has `sts:AssumeRole`, the role trust policy includes your account, and the role allows `bedrock-agentcore:InvokeAgentRuntime` on the target runtime.

## Security Considerations
The proxy relies on the default AWS credential chain. Use dedicated IAM principals with the minimum scope required by Bedrock AgentCore. 

## License
This repository is licensed under the MIT License. See `LICENSE` for details.

## References
[^gateway-inbound]: Configure inbound authentication for Amazon Bedrock AgentCore Gateway. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html
[^cognito-auth]: Set up Amazon Cognito as an identity provider for AgentCore Gateway. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity-idp-cognito.html
[^runtime-how]: Overview of AgentCore runtime flow and IAM SigV4 support. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html
[^invoke-api]: API reference for InvokeAgentRuntime. https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html
