# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository provides an MCP (Model Context Protocol) proxy for Amazon Bedrock AgentCore, solving two key problems:
1. **IAM Authentication**: Local SigV4 signing proxy that bridges IAM credentials to AgentCore's OAuth/Cognito requirements
2. **Stateful Bidirectional MCP**: HTTP-to-STDIO bridge enabling MCP sampling and elicitation in serverless environments

The proxy runs locally via stdio and communicates with AgentCore runtimes deployed to AWS. Two runtime deployment models are supported: stateless (direct MCP) and stateful (HTTP bridge with persistent subprocess).

## Common Commands

### Development
```bash
# Install proxy in editable mode
uv pip install -e .

# Install with dev and server dependencies
uv pip install -e ".[dev,server]"

# Run proxy locally
uvx --from . mcp-agentcore-proxy

# Required environment variables
export AGENTCORE_AGENT_ARN="arn:aws:bedrock-agentcore:region:account:runtime/name"
export AWS_REGION="us-east-1"
```

### Testing
```bash
# Run all tests
make test
# or directly:
uvx --python 3.13 --with .[dev] --with .[server] pytest tests/

# Run smoketest against deployed runtime
uv run demo/scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN"

# Run stateful smoketest
RUNTIME_SESSION_MODE=session uv run demo/scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN" --mode stateful
```

### Code Quality
```bash
# Lint
uvx ruff check .
# or: make lint

# Format
uvx ruff format
# or: make format

# Combined quality checks
make quality
```

### Deployment (AWS SAM)
```bash
# Build both runtime containers
make build

# Push to ECR
make push

# Deploy SAM stack
make deploy

# All-in-one
make all

# View stack outputs (includes runtime ARNs)
make outputs

# Run both smoketests
make smoke-test
```

### Running Individual Smoketests
```bash
# Stateless runtime
make smoke-test-stateless

# Stateful runtime
make smoke-test-stateful
```

## Architecture

### Core Components

#### Local Proxy (`src/mcp_agentcore_proxy/`)
- **`client.py`**: Main CLI entry point (`mcp-agentcore-proxy`). Handles stdio ↔ AgentCore communication, SigV4 signing, SSE streaming, and automatic handshake replay on container restarts
- **`session_manager.py`**: Runtime session ID generation (modes: `session`, `identity`, `request`)
- **`aws_session.py`**: AWS session resolution with optional role assumption via `aws-assume-role-lib`
- **`server.py`**: HTTP-to-STDIO bridge (`mcp-agentcore-server`) for stateful runtimes. Spawns and manages persistent MCP subprocess
- **`version.py`**: Auto-generated during builds (do not edit or track)

#### Demo Infrastructure (`demo/`)
- **`runtime_stateless/`**: FastMCP server running directly in AgentCore (stateless HTTP). Tools: `whoami`, `get_weather`, plus completion-style story/profile flows
- **`runtime_stateful/`**: HTTP bridge container that spawns a persistent stdio MCP server subprocess. Enables bidirectional MCP (sampling/elicitation). Tools: `whoami`, `get_weather`, `generate_story_with_sampling`, `create_character_profile`
- **`scripts/`**: Integration tests and smoke tests
- **`template.yaml`**: SAM CloudFormation template defining both runtimes, IAM roles, and outputs
- **`samconfig.toml`**: SAM CLI configuration (default region, stack name, capabilities)

#### Session Management
The proxy supports three session modes via `RUNTIME_SESSION_MODE`:
- `session` (default): Random UUID per proxy process—maintains warm runtime for stateful flows
- `identity`: Hash of caller identity from `sts:GetCallerIdentity`—enables session reuse across proxy invocations for the same IAM principal
- `request`: New UUID per request—fully stateless

For stateful runtimes, use `session` mode. The HTTP bridge maintains a single subprocess for the microVM lifetime.

#### Handshake Replay (Resilience)
When a stateful container restarts, the child MCP subprocess loses initialization state. The proxy (`client.py:292-377`) detects `-32602` errors on non-initialize requests and automatically:
1. Re-sends cached `initialize` message
2. Sends `notifications/initialized`
3. Retries original request
4. Emits MCP log notification to IDE

This keeps sessions transparent across infrequent redeployments without switching to stateless mode.

### Data Flow

**Stateless**: MCP client → stdio proxy → SigV4 → AgentCore → FastMCP server → response

**Stateful**: MCP client → stdio proxy → SigV4 → AgentCore → HTTP bridge → stdio subprocess → response (subprocess persists across calls with same `runtimeSessionId`)

For bidirectional flows (sampling/elicitation), the subprocess initiates requests back to the client via the bridge.

## Key Implementation Details

### SigV4 Signing & Streaming
The proxy (`client.py:_invoke_raw`) signs `InvokeAgentRuntime` requests with boto3 and streams SSE responses from AgentCore back to stdout as JSON-RPC messages. It handles both streaming (`text/event-stream`) and JSON response bodies.

### Credential Refresh
If boto3 raises expired token errors (`ExpiredToken`, `UnrecognizedClientException`, etc.), the proxy automatically refreshes the AWS session once per request (`client.py:161-209`).

### HTTP Bridge Subprocess Management
The bridge (`server.py:MCPSubprocess`) spawns the MCP server with `asyncio.create_subprocess_exec`, communicates via newline-delimited JSON over stdin/stdout, and drains stderr to logs. It uses a lock to serialize requests and gracefully terminates the subprocess on shutdown (SIGTERM with 5s timeout, then SIGKILL).

### Environment Variables
Critical bridge configuration (`server.py:_resolve_subprocess_config`):
- `MCP_SERVER_CMD`: Command to launch stdio MCP server (required)
- `MCP_SERVER_CWD`: Working directory for subprocess
- `PYTHONUNBUFFERED=1`: Ensures immediate output flushing (auto-set)
- `LOG_LEVEL`: Controls logging verbosity

Proxy configuration:
- `AGENTCORE_AGENT_ARN`: Runtime ARN (required)
- `RUNTIME_SESSION_MODE`: Session ID generation strategy
- `AGENTCORE_ASSUME_ROLE_ARN`: Optional role to assume
- `AGENTCORE_ASSUME_ROLE_SESSION_NAME`: STS session name (default: `mcpAgentCoreProxy`)

### Cross-Account Access
The proxy supports assuming IAM roles for cross-account scenarios. Set `AGENTCORE_ASSUME_ROLE_ARN` and ensure the role's trust policy permits your caller. The SAM stack provisions a test role (`ProxyInvokeRoleArn` output) for validation.

## Testing Strategy

### Unit Tests (`tests/`)
- `test_client.py`: MCP protocol handling, error cases
- `test_server.py`: HTTP bridge subprocess lifecycle
- `test_session_manager.py`: Session ID generation modes
- `test_aws_session.py`: Role assumption flows

Run via `pytest tests/` or `make test` (includes lint + format checks).

### Integration Tests
`demo/scripts/proxy_smoketest.py` exercises end-to-end flows:
1. Lists tools via `tools/list`
2. Calls `whoami` (verifies session ID propagation)
3. Calls `get_weather` (deterministic response validation)
4. For stateful mode: tests `generate_story_with_sampling` and `create_character_profile` (bidirectional MCP)

### CI/CD
`.github/workflows/ci.yml` runs Ruff lint, Ruff format check, and pytest on every PR. On pushes to `main`, it builds distributions, publishes to PyPI (if `PYPI_API_TOKEN` secret is set), and tags the release.

## Common Development Patterns

### Adding New Tools
For stateless runtimes, add FastMCP tools to `demo/runtime_stateless/mcp_server.py`. For stateful runtimes requiring sampling/elicitation, add to `demo/runtime_stateful/mcp_server.py`.

### Debugging Proxy Issues
1. Set `LOG_LEVEL=DEBUG` or `MCP_PROXY_DEBUG=1` for verbose stderr logs
2. Check STDERR for `[mcp-agentcore-proxy]` debug messages
3. Verify stdout contains valid JSON-RPC (no interleaved debug output)

### Debugging Bridge Issues
1. Set `LOG_LEVEL=DEBUG` in the container environment
2. Check CloudWatch Logs for subprocess stderr output (`[subprocess-stderr]` prefix)
3. Verify `MCP_SERVER_CMD` includes `-u` flag for unbuffered Python output

### Modifying Session Behavior
Edit `session_manager.py` to change session ID derivation. For identity-based sessions, the hash includes Account, UserId, and ARN from `sts:GetCallerIdentity`.

## Important Constraints

- **Stdout Purity**: The proxy must only write valid JSON-RPC to stdout. Use stderr for debug messages.
- **Unbuffered Output**: MCP subprocess commands must use unbuffered mode (`python -u`) to prevent communication hangs.
- **Notification Handling**: JSON-RPC notifications (no `id` field) must not expect responses. The bridge returns HTTP 204 for notifications.
- **Handshake State**: Stateful runtimes require `initialize` → `notifications/initialized` before tool calls. The proxy handles replay transparently.

## Dependencies

- **boto3**: AWS SDK for SigV4 signing and AgentCore invocation
- **aws-assume-role-lib**: Handles STS role assumption with automatic refresh
- **fastapi + uvicorn**: HTTP bridge server framework
- **fastmcp**: MCP server implementation for both runtimes
- **pytest + pytest-asyncio + pytest-mock**: Testing framework

Install with `uv pip install -e ".[dev,server]"` for full development setup.

## Release Process

1. Bump `version` in `pyproject.toml`
2. Merge PR to `main`
3. CI automatically builds, tests, publishes to PyPI, and creates git tag `v<version>`
4. Verify workflow success and PyPI package availability

## Security Notes

- Never hard-code AWS credentials or ARNs in source code
- Use default credential chain (environment, SSO, instance profile)
- Clear environment variables before sharing command transcripts
- The proxy signs requests with caller's IAM credentials—ensure minimal privilege (`bedrock-agentcore:InvokeAgentRuntime` only)
