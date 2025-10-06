# Repository Guidelines

## Project Structure & Module Organization
This repo couples a local MCP STDIO proxy with a Bedrock AgentCore demo runtime.
- `src/mcp_agentcore_proxy/` packages the client (`client.py`) published as `mcp-agentcore-proxy`; it handles IAM auth and streams responses.
- `demo/runtime_stateless/` hosts the original FastMCP server (`mcp_server.py`, `utils.py`) plus `Dockerfile` and `requirements.txt` used by the SAM stack.
- `demo/runtime_stateful/` packages the HTTP↔STDIO bridge runtime and sampling/elicitation demos (`generate_story_with_sampling`, `create_character_profile`).
- `demo/scripts/proxy_smoketest.py` runs the proxy end-to-end; reuse it for quick checks.
- `demo/template.yaml` and `demo/samconfig.toml` define the SAM stack for deploying both runtimes.
- Root `Makefile` manages container builds and deployment automation.

## Build, Test, and Development Commands
- `uv pip install -e .` — install the CLI in editable mode while iterating.
- `uvx --from . mcp-agentcore-proxy` — run the proxy locally against any MCP client.
- Configure runtime affinity with `RUNTIME_SESSION_MODE` (defaults to `session`; `identity` is opt-in for stateless reuse).
- `uv run demo/scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN"` — smoke-test the proxy against a runtime; set `AWS_REGION`.
- `make build | push | deploy` — build both runtime images, push to ECR, and deploy the SAM stack.
- `make smoke-test` — run both smoketest scenarios (stateless then stateful).
- `make smoke-test-stateless` — retrieve the stateless runtime ARN, then invoke the smoketest via `uv run`.
- `make smoke-test-stateful` — retrieve the stateful runtime ARN, then invoke the smoketest with `--mode stateful` and `RUNTIME_SESSION_MODE=session`.

## Coding Style & Naming Conventions
Code is Python 3.10+ with four-space indentation and type hints. Keep modules, files, and functions snake_case; constants stay UPPER_CASE. Guard CLI output with `print(..., flush=True)` and prefer structured JSON responses as in `client.py`. Update `pyproject.toml` or `demo/runtime_stateless/requirements.txt` alongside any dependency changes and lock with `uv lock`.

## Testing Guidelines
`demo/scripts/proxy_smoketest.py` is the canonical verification path; run it after CLI or runtime changes. Provide the runtime ARN via `AGENTCORE_AGENT_ARN` (or rely on `make smoke-test` to resolve it). When adding logic-heavy modules, place `pytest` tests beneath `tests/` or `demo/runtime_stateless/tests/` and wire them into `uv run pytest`. Capture notable stdout/stderr snippets in PRs, but avoid committing AWS identifiers.

## Commit & Pull Request Guidelines
Existing history uses short, imperative subjects (“Add MIT License to the project”); continue that style and keep summaries under ~72 characters. Draft PRs with: purpose and impacted components; verification notes (`make smoke-test`, manual MCP runs); and any follow-up tasks (new IAM policies, documentation). Link GitHub issues when applicable and attach screenshots or transcripts only when they omit sensitive ARNs or credentials.

## Security & Configuration Tips
Do not hard-code AWS credentials or ARNs; rely on the default credential chain. Export `AGENTCORE_AGENT_ARN` and `AWS_REGION` only in your shell or CI secrets, and clear them before sharing command transcripts. Both demo runtimes rely on client-provided completions, so no additional model permissions are required beyond `bedrock-agentcore:InvokeAgentRuntime`.
