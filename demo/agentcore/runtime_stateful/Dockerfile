FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

COPY demo/agentcore/runtime_stateful/requirements.txt ./requirements.txt

# Create an isolated environment for dependencies so we can copy it into the
# slim runtime image without bringing along build tooling.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir aws-opentelemetry-distro>=0.10.1

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src/mcp_agentcore_proxy ./mcp_agentcore_proxy
COPY demo/agentcore/runtime_stateful/mcp_server.py ./mcp_server.py

# set the command to run the MCP server
ENV MCP_SERVER_CMD="python -u mcp_server.py"

EXPOSE 8080

CMD ["python", "-m", "mcp_agentcore_proxy.server"]
