# Repository Guidelines

## Project Structure & Module Organization
- Proxy client: `src/mcp_agentcore_proxy/` (entry: `client.py`, package: `mcp-agentcore-proxy`).
- Demos: `demo/runtime_stateless/` (FastMCP server, `Dockerfile`, `requirements.txt`), `demo/runtime_stateful/` (HTTP↔STDIO bridge, sampling demos).
- Smoke test: `demo/scripts/proxy_smoketest.py`.
- SAM and orchestration: `demo/template.yaml`, `demo/samconfig.toml`, root `Makefile`.

## Build, Test, and Development Commands
- Install editable CLI: `uv pip install -e .` (installs `mcp-agentcore-proxy` locally).
- Run proxy locally: `uvx --from . mcp-agentcore-proxy`.
- Smoke test (requires `AWS_REGION`, `AGENTCORE_AGENT_ARN`):
  `uv run demo/scripts/proxy_smoketest.py "$AGENTCORE_AGENT_ARN"`.
- Package/deploy (SAM + images): `make build`, `make push`, `make deploy`.
- Convenience smoke tests: `make smoke-test`, `make smoke-test-stateless`, `make smoke-test-stateful`.

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, type hints required for public APIs.
- Naming: snake_case (files/modules/functions), UPPERCASE constants.
- CLI output: use `print(..., flush=True)` and prefer structured JSON payloads (see `src/mcp_agentcore_proxy/client.py`).
- Dependencies: manage in `pyproject.toml` or runtime `requirements.txt`; after changes run `uv lock`.

## Testing Guidelines
- Primary harness: `demo/scripts/proxy_smoketest.py` (accepts explicit `AGENTCORE_AGENT_ARN`; `make smoke-test` can resolve it).
- Add logic-heavy tests under `tests/` or `demo/runtime_stateless/tests/`.
- Run tests: `uv run pytest`.
- Logs: capture meaningful stdout/stderr; do not include ARNs, credentials, or regions in shared artifacts.

## Commit & Pull Request Guidelines
- Commits: short, imperative subjects under ~72 chars; focused diffs.
- PRs: include purpose, components touched, verification (`make smoke-test`, local proxy runs), and follow-ups (e.g., IAM). Link issues and scrub identifiers from logs/screenshots.

## Security & Configuration Tips
- Never hard-code AWS credentials or agent ARNs; rely on the default credential chain.
- Env vars: `AGENTCORE_AGENT_ARN`, `AWS_REGION`, `RUNTIME_SESSION_MODE` as needed; unset before sharing logs.
- Ensure invoking identity is limited to `bedrock-agentcore:InvokeAgentRuntime` for completions.

