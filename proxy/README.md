# MCP AgentCore Proxy

Local STDIO proxy that forwards MCP frames to an Amazon Bedrock AgentCore Runtime using IAM credentials. 

## Smoketest

`scripts/proxy_smoketest.py` exercises the proxy end-to-end using the official MCP stdio client. Example:

```
export AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/agentcore_proxy_demo_server-abc123
export AWS_REGION=us-east-1

uv run scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN" --city "Seattle" --proxy-cmd uvx --from proxy/ mcp-agentcore-proxy
```

The script launches the proxy via stdio, runs `initialize`, lists tools, and (optionally) calls `get_weather`. Pass `--proxy-cmd` if you need a different launch command, and set `UV_NO_CACHE=1` to force `uvx` to rebuild from source.
