# Repository Guidelines

## Project Structure & Module Organization
This repo couples a local MCP STDIO proxy with a Bedrock AgentCore demo runtime.
- `src/mcp_agentcore_proxy/` packages the CLI (`cli.py`) published as `mcp-agentcore-proxy`; it handles IAM auth and streams responses.
- `server/` hosts the FastMCP server (`mcp_server.py`, `utils.py`) plus `Dockerfile` and `requirements.txt` used by the SAM stack.
- `scripts/proxy_smoketest.py` runs the proxy end-to-end; reuse it for quick checks.
- Root tooling (`Makefile`, `template.yaml`, `samconfig.toml`) manages container builds and deployment; reference `docs/plan.md` for context.

## Build, Test, and Development Commands
- `uv pip install -e .` — install the CLI in editable mode while iterating.
- `uvx --from . mcp-agentcore-proxy` — run the proxy locally against any MCP client.
- `uv run scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN" --city "Seattle"` — smoke-test the proxy against a runtime; set `AWS_REGION`.
- `make build | push | deploy` — build the server image, push to ECR, and deploy the SAM stack.
- `make smoke-test` — retrieve the deployed ARN, then invoke the smoketest via `uv run`.

## Coding Style & Naming Conventions
Code is Python 3.10+ with four-space indentation and type hints. Keep modules, files, and functions snake_case; constants stay UPPER_CASE. Guard CLI output with `print(..., flush=True)` and prefer structured JSON responses as in `cli.py`. Update `pyproject.toml` or `server/requirements.txt` alongside any dependency changes and lock with `uv lock`.

## Testing Guidelines
`proxy_smoketest.py` is the canonical verification path; run it after CLI or runtime changes. Provide the runtime ARN via `AGENTCORE_AGENT_ARN` (or rely on `make smoke-test` to resolve it). When adding logic-heavy modules, place `pytest` tests beneath `tests/` or `server/tests/` and wire them into `uv run pytest`. Capture notable stdout/stderr snippets in PRs, but avoid committing AWS identifiers.

## Commit & Pull Request Guidelines
Existing history uses short, imperative subjects (“Add MIT License to the project”); continue that style and keep summaries under ~72 characters. Draft PRs with: purpose and impacted components; verification notes (`make smoke-test`, manual MCP runs); and any follow-up tasks (new IAM policies, documentation). Link GitHub issues when applicable and attach screenshots or transcripts only when they omit sensitive ARNs or credentials.

## Security & Configuration Tips
Do not hard-code AWS credentials or ARNs; rely on the default credential chain. Export `AGENTCORE_AGENT_ARN` and `AWS_REGION` only in your shell or CI secrets, and clear them before sharing command transcripts. The demo server calls the `amazon.nova-micro-v1:0` model—update IAM permissions accordingly if you swap models or regions.
