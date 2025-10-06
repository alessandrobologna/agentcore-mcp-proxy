# AgentCore MCP Demo Runtimes

This directory contains sample MCP server implementations that run on Amazon Bedrock AgentCore, demonstrating both stateless and stateful deployment models.

## Overview

The demo provides two runtime implementations:
- **Stateless Runtime** (`runtime_stateless/`): Direct FastMCP server for simple request/response tools
- **Stateful Runtime** (`runtime_stateful/`): HTTP-to-STDIO bridge maintaining a persistent MCP subprocess for bidirectional MCP (sampling/elicitation)

## Prerequisites

- Python 3.10+ with [uv](https://github.com/astral-sh/uv) installed
- AWS credentials with permissions for:
  - `sts:GetCallerIdentity`
  - `bedrock-agentcore:InvokeAgentRuntime`
  - ECR operations (push/pull images)
  - CloudFormation stack management
- Docker and AWS SAM CLI
- An AWS region configured

## Quick Start

Deploy both runtimes with a single command (run from `demo/` directory):

```bash
cd demo/
make deploy
```

This will:
1. Build both Docker images (stateless and stateful)
2. Push them to ECR
3. Deploy the CloudFormation stack via SAM
4. Output runtime ARNs for use with the proxy

Get the deployed runtime ARNs:
```bash
make outputs
```

## Stateless Runtime

The stateless runtime (`runtime_stateless/`) runs a FastMCP server directly inside AgentCore. Each `InvokeAgentRuntime` call creates a new execution context.

**Tools provided:**
- `whoami` - Returns the sandbox identifier
- `get_weather` - Deterministic weather lookup by city

**Best for:**
- Deterministic functions (calculations, lookups)
- Stateless API calls
- Simple data transformations

**Deploy only stateless:**
```bash
make build-stateless
```

## Stateful Runtime

The stateful runtime (`runtime_stateful/`) runs an HTTP-to-STDIO bridge that spawns and maintains a persistent MCP server subprocess. The subprocess persists across multiple invocations with the same `runtimeSessionId`.

**Tools provided:**
- `whoami` - Returns the sandbox identifier
- `get_weather` - Deterministic weather lookup
- `generate_story_with_sampling` - Demonstrates MCP sampling (server requests LLM inference from client)
- `create_character_profile` - Demonstrates MCP elicitation (schema-driven data collection)

**Best for:**
- MCP sampling (server-initiated LLM calls)
- MCP elicitation (structured data with Pydantic schemas)
- Multi-turn conversations requiring session state
- Workflows requiring persistent context

**Deploy only stateful:**
```bash
make build-stateful
```

## Bidirectional MCP Examples

The stateful runtime demonstrates bidirectional MCP flows where the server can request services from the client.

### Sampling

The `generate_story_with_sampling` tool requests LLM inference from the client:

```python
@mcp.tool()
async def generate_story_with_sampling(topic: str, context: Context) -> dict:
    result = await context.session.create_message(
        messages=[
            types.SamplingMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=f"Write a short story about {topic}."
                )
            )
        ],
        max_tokens=300,
    )
    return {"story": result.content.text}
```

The MCP protocol routes the sampling request back to the client. The client runs inference and returns the result to the server.

### Elicitation

The `create_character_profile` tool demonstrates schema-driven data collection:

```python
class CharacterProfileSchema(BaseModel):
    traits: str
    motivation: str

@mcp.tool()
async def create_character_profile(character: str, context: Context) -> dict:
    result = await context.elicit(
        f"Describe {character} in two bullet points",
        CharacterProfileSchema
    )
    return {"profile": result.data.model_dump()}
```

The client validates responses against the Pydantic schema before returning data to the server.

## Building Your Own Stateful Runtime

The HTTP-to-STDIO bridge (`mcp-agentcore-server`) can be installed in any container:

```dockerfile
RUN pip install mcp-agentcore-proxy
ENV MCP_SERVER_CMD="python -u your_mcp_server.py"
CMD ["mcp-agentcore-server"]
```

**Important:** The `-u` flag forces unbuffered output to prevent communication hangs.

### Bridge Environment Variables

- `MCP_SERVER_CMD` (required): Command to launch the child MCP server
  - Example: `python -u mcp_server.py`
  - Must speak MCP JSON-RPC over stdio

- `MCP_SERVER_CWD` (optional): Working directory for the child process

- `SERVER_HOST` (optional): Bridge HTTP listen address (default: `0.0.0.0`)

- `SERVER_PORT` (optional): Bridge HTTP listen port (default: `8080`)

- `LOG_LEVEL` (optional): Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)

The bridge automatically sets `PYTHONUNBUFFERED=1` and `PYTHONIOENCODING=UTF-8` in the child process environment.

## Makefile Targets

All `make` commands should be run from the `demo/` directory:

- `make build` - Build both runtime images locally (default: `linux/arm64`)
- `make build-stateless` - Build only the stateless runtime
- `make build-stateful` - Build only the stateful runtime
- `make push` - Push both images to ECR with versioned and digest tags
- `make deploy` - Build, push, and deploy the SAM stack
- `make outputs` - Print CloudFormation stack outputs (includes runtime ARNs)
- `make smoke-test` - Run both smoketest scenarios sequentially
- `make smoke-test-stateless` - Run smoketest against stateless runtime only
- `make smoke-test-stateful` - Run smoketest against stateful runtime only
- `make clean` - Remove local Docker images

**Environment requirements:**
- `AWS_REGION` must be set or configured via AWS CLI
- Docker must be running
- AWS credentials must be valid

## Smoke Testing

The smoke test script exercises the proxy end-to-end:

```bash
# Test stateless runtime
export AGENTCORE_AGENT_ARN="<stateless-runtime-arn>"
uv run ../scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN"

# Test stateful runtime
export AGENTCORE_AGENT_ARN="<stateful-runtime-arn>"
RUNTIME_SESSION_MODE=session uv run ../scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN" --mode stateful
```

The script:
1. Lists available tools via `tools/list`
2. Calls `whoami` to verify session ID propagation
3. Calls `get_weather` with deterministic validation
4. For stateful mode: tests `generate_story_with_sampling` and `create_character_profile`

## Cross-Account Testing

When deploying the demo stack, a test role is provisioned for cross-account scenarios (run from `demo/` directory):

```bash
make deploy
export AGENTCORE_ASSUME_ROLE_ARN="$(make -s outputs | jq -r '.[] | select(.OutputKey=="ProxyInvokeRoleArn") | .OutputValue')"
uv run scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN"
```

The role:
- Trusts the deploying account's root principal
- Allows `bedrock-agentcore:InvokeAgentRuntime` on both deployed runtimes
- Can be used to test role assumption flows

**Note:** Requires the `jq` CLI to filter CloudFormation outputs.

## Development

### Adding Dependencies

- **Stateless runtime**: Update `runtime_stateless/requirements.txt`
- **Stateful runtime**: Update `runtime_stateful/requirements.txt`
- **Bridge/proxy**: Update `pyproject.toml`

### Local Testing

Build and run locally (from repository root):
```bash
docker build -f demo/agentcore/runtime_stateful/Dockerfile -t agentcore-stateful .
```

### Custom Tools

Add new tools to the appropriate `mcp_server.py`:
- Simple request/response tools → `runtime_stateless/mcp_server.py`
- Tools requiring sampling/elicitation → `runtime_stateful/mcp_server.py`

## Cost Considerations

Deploying these runtimes incurs AWS costs:
- AgentCore runtime execution (per invocation)
- ECR storage (for Docker images)
- CloudFormation stack resources

Delete the stack when done:
```bash
sam delete --stack-name agentcore-proxy-demo-servers --region <your-region>
```

## Additional Demos

- **FastAgent Demo** (`../fast-agent/`): AI agent using FastAgent framework to interact with the stateful runtime via MCP sampling. See [`../fast-agent/README.md`](../fast-agent/README.md) for details.

## Troubleshooting

- **Build failures**: Ensure Docker is running and you have sufficient disk space
- **Push failures**: Verify AWS credentials and ECR permissions
- **Deploy failures**: Check CloudFormation events for specific errors
- **Runtime errors**: Review CloudWatch Logs for the deployed runtimes
- **Empty responses**: Confirm the runtime accepts MCP requests and is properly configured

## References

- [AgentCore Runtime Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html)
- [InvokeAgentRuntime API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
