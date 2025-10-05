"""HTTP↔STDIO bridge for running MCP servers inside AgentCore runtimes."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shlex
import signal
import sys
from dataclasses import dataclass

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
import uvicorn


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mcp_agentcore_proxy.server")


class _SuppressPingFilter(logging.Filter):
    """Filter out access logs for the /ping endpoint."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        try:
            path = record.args[2]
        except (IndexError, TypeError, AttributeError):
            return True
        return path != "/ping"


logging.getLogger("uvicorn.access").addFilter(_SuppressPingFilter())


class MCPServerError(Exception):
    """Raised when the MCP subprocess cannot be used."""


@dataclass
class SubprocessConfig:
    command: list[str]
    cwd: str | None
    env: dict[str, str]


class MCPSubprocess:
    """Manage a long-lived MCP server subprocess over stdio."""

    def __init__(self, config: SubprocessConfig):
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._stderr_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._process is not None:
            return

        logger.info("Starting MCP subprocess: %s", " ".join(self._config.command))
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._config.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.cwd,
                env=self._config.env,
            )
        except FileNotFoundError as exc:
            raise MCPServerError(f"Unable to launch MCP server: {exc}") from exc

        assert self._process.stderr is not None
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def shutdown(self) -> None:
        process = self._process
        if process is None:
            return

        logger.info("Stopping MCP subprocess")
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Subprocess did not exit on SIGTERM; killing")
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

        if self._stderr_task:
            self._stderr_task.cancel()
        self._process = None

    async def invoke(self, payload: str) -> str:
        process = self._process
        if process is None:
            raise MCPServerError("MCP subprocess is not running")

        if process.stdin is None or process.stdout is None:
            raise MCPServerError("Subprocess stdio is unavailable")

        async with self._lock:
            await self._write(payload, process)
            response = await self._read_json(stream=process.stdout)
            logger.debug("← subprocess response: %s", response[:200])
            return response

    async def send(self, payload: str) -> None:
        """Send a JSON-RPC notification to the subprocess without waiting for a reply."""
        process = self._process
        if process is None:
            raise MCPServerError("MCP subprocess is not running")

        if process.stdin is None:
            raise MCPServerError("Subprocess stdio is unavailable")

        async with self._lock:
            await self._write(payload, process)

    async def _write(self, payload: str, process: asyncio.subprocess.Process) -> None:
        if not payload.endswith("\n"):
            payload = payload + "\n"

        preview = payload.strip().replace("\n", " ")[:200]
        logger.debug("→ subprocess payload: %s", preview)
        assert process.stdin is not None
        process.stdin.write(payload.encode("utf-8"))
        await process.stdin.drain()

    async def _read_json(self, stream: asyncio.StreamReader) -> str:
        """Read newline-delimited JSON from the subprocess, tolerating blank lines."""

        chunks: list[str] = []
        while True:
            line = await stream.readline()
            if not line:
                raise MCPServerError("MCP subprocess terminated while reading output")

            text = line.decode("utf-8", errors="replace")
            if not text.strip():
                continue

            chunks.append(text)
            candidate = "".join(chunks).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

    async def _drain_stderr(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        reader = self._process.stderr
        while True:
            line = await reader.readline()
            if not line:
                return
            logger.debug(
                "[subprocess-stderr] %s",
                line.decode("utf-8", errors="replace").rstrip(),
            )


def _resolve_subprocess_config(session_id: str | None = None) -> SubprocessConfig:
    cmd_env = os.getenv("MCP_SERVER_CMD")
    if not cmd_env:
        raise MCPServerError("Set MCP_SERVER_CMD to launch the stdio MCP server")

    command = shlex.split(cmd_env)
    if not command:
        raise MCPServerError("MCP_SERVER_CMD did not yield a command")

    cwd = os.getenv("MCP_SERVER_CWD") or None

    env = os.environ.copy()
    if session_id:
        env["MCP_SESSION_ID"] = session_id

    # Ensure the MCP subprocess writes immediately to stdout/stderr
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONIOENCODING", "UTF-8")
    return SubprocessConfig(command=command, cwd=cwd, env=env)


def _build_app() -> FastAPI:
    runner: MCPSubprocess | None = None
    runner_lock = asyncio.Lock()

    session_id: str | None = None

    async def _ensure_runner() -> MCPSubprocess:
        nonlocal runner
        if runner is not None:
            return runner

        async with runner_lock:
            if runner is None:
                config = _resolve_subprocess_config(session_id)
                new_runner = MCPSubprocess(config)
                await new_runner.start()
                runner = new_runner
        assert runner is not None
        return runner

    @contextlib.asynccontextmanager
    async def _lifespan(app: FastAPI):  # pragma: no cover - FastAPI hook
        try:
            yield
        finally:
            async with runner_lock:
                if runner is not None:
                    await runner.shutdown()

    app = FastAPI(lifespan=_lifespan)

    @app.get("/ping")
    async def health() -> dict[str, str]:
        nonlocal runner

        # If subprocess has been started, verify it's still running
        if runner is not None:
            process = runner._process
            if process is None or process.returncode is not None:
                logger.warning(
                    "Health check failed: subprocess exit code %s",
                    process.returncode if process else "N/A",
                )
                raise HTTPException(
                    status_code=503, detail="MCP subprocess not running"
                )

        # If runner is None, we haven't started yet (lazy init) - that's OK
        return {"status": "ok"}

    async def _read_payload(request: Request) -> str:
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="Request body is empty")
        # Log a minimal set of headers for debugging (avoid sensitive ones)
        hdr = request.headers
        interesting = {
            "host": hdr.get("host"),
            "content-length": hdr.get("content-length"),
            "content-type": hdr.get("content-type"),
            "x-amzn-bedrock-agentcore-runtime-session-id": hdr.get(
                "x-amzn-bedrock-agentcore-runtime-session-id"
            ),
        }
        logger.debug(
            "HTTP %s %s headers: %s", request.method, request.url.path, interesting
        )
        try:
            payload = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Body must be UTF-8") from exc
        nonlocal session_id
        if session_id is None:
            session_id = interesting.get("x-amzn-bedrock-agentcore-runtime-session-id")
        payload = payload.strip()

        if payload:
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None
            if (
                isinstance(parsed, dict)
                and parsed.get("method") == "initialize"
                and isinstance(parsed.get("params"), dict)
            ):
                params = parsed["params"]
                client_info = params.get("clientInfo")
                client_capabilities = params.get("capabilities")
                logger.info(
                    "Initialize request received: client_info=%s capabilities=%s",
                    client_info,
                    client_capabilities,
                )

        return payload

    @app.post("/invocations")
    async def handle_invocation(payload: str = Depends(_read_payload)) -> JSONResponse:
        # Determine if this is a JSON-RPC notification (no id -> no response)
        expect_response = True
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict) and parsed.get("id") is None:
                expect_response = False
        except json.JSONDecodeError:
            # If not JSON, treat as expecting a response to avoid losing errors silently
            expect_response = True

        try:
            bridge_runner = await _ensure_runner()
            if expect_response:
                response = await bridge_runner.invoke(payload)
                return JSONResponse(content=json.loads(response))
            else:
                await bridge_runner.send(payload)
                return Response(status_code=204)
        except MCPServerError as exc:
            logger.error("Invocation failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    return app


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    app = _build_app()

    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8080"))

    uvicorn.run(app, host=host, port=port, log_level=LOG_LEVEL.lower())


if __name__ == "__main__":
    main()
