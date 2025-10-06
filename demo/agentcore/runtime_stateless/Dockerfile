FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

COPY demo/agentcore/runtime_stateless/requirements.txt ./requirements.txt

# Create an isolated environment for dependencies so we can copy it into the
# slim runtime image without bringing along build tooling.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir aws-opentelemetry-distro>=0.10.1

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY demo/agentcore/runtime_stateless/mcp_server.py demo/agentcore/runtime_stateless/utils.py ./

EXPOSE 8000
CMD ["python","-m", "mcp_server"]
