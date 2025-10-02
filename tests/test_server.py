"""Tests for mcp_agentcore_proxy.server module."""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from mcp_agentcore_proxy.server import (
    MCPServerError,
    MCPSubprocess,
    SubprocessConfig,
    _build_app,
    _resolve_subprocess_config,
)


@pytest.fixture
def subprocess_config():
    """Create a test SubprocessConfig."""
    return SubprocessConfig(
        command=["python", "-u", "test_server.py"],
        cwd="/app",
        env={"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "UTF-8"},
    )


class TestMCPSubprocess:
    """Test suite for MCPSubprocess class."""

    @pytest.mark.asyncio
    async def test_start_subprocess(self, subprocess_config, mock_subprocess):
        """Test successful subprocess startup."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()

            assert subprocess._process is mock_subprocess
            mock_create.assert_called_once_with(
                "python",
                "-u",
                "test_server.py",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/app",
                env=subprocess_config.env,
            )

    @pytest.mark.asyncio
    async def test_start_subprocess_not_found(self, subprocess_config):
        """Test subprocess start with missing executable."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError("not found")
        ):
            subprocess = MCPSubprocess(subprocess_config)

            with pytest.raises(MCPServerError, match="Unable to launch MCP server"):
                await subprocess.start()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, subprocess_config, mock_subprocess):
        """Test that calling start() multiple times doesn't spawn multiple processes."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()
            await subprocess.start()
            await subprocess.start()

            # Should only create subprocess once
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_clean(self, subprocess_config, mock_subprocess):
        """Test clean subprocess shutdown with SIGTERM."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()

            # Simulate process exiting cleanly on SIGTERM
            async def wait_side_effect():
                mock_subprocess.returncode = 0

            mock_subprocess.wait.side_effect = wait_side_effect

            await subprocess.shutdown()

            mock_subprocess.send_signal.assert_called_once()
            assert subprocess._process is None

    @pytest.mark.asyncio
    async def test_shutdown_force_kill(self, subprocess_config, mock_subprocess):
        """Test subprocess shutdown with forced kill after timeout."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()

            # Simulate process not responding to SIGTERM on first wait, then exiting on second wait
            wait_count = 0

            async def wait_side_effect():
                nonlocal wait_count
                wait_count += 1
                if wait_count == 1:
                    raise asyncio.TimeoutError()
                else:
                    mock_subprocess.returncode = -9
                    return

            mock_subprocess.wait.side_effect = wait_side_effect

            await subprocess.shutdown()

            mock_subprocess.send_signal.assert_called_once()
            mock_subprocess.kill.assert_called_once()
            assert subprocess._process is None

    @pytest.mark.asyncio
    async def test_invoke_request_response(
        self,
        subprocess_config,
        mock_subprocess,
        sample_json_rpc_request,
        sample_json_rpc_response,
    ):
        """Test invoke() sends request and reads response."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            # Mock stdout to return JSON response
            mock_subprocess.stdout.readline.return_value = (
                sample_json_rpc_response + "\n"
            ).encode("utf-8")

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()

            response = await subprocess.invoke(sample_json_rpc_request)

            assert response.strip() == sample_json_rpc_response
            mock_subprocess.stdin.write.assert_called_once()
            mock_subprocess.stdin.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_not_running(self, subprocess_config, sample_json_rpc_request):
        """Test invoke() raises error when subprocess not started."""
        subprocess = MCPSubprocess(subprocess_config)

        with pytest.raises(MCPServerError, match="not running"):
            await subprocess.invoke(sample_json_rpc_request)

    @pytest.mark.asyncio
    async def test_send_notification(
        self, subprocess_config, mock_subprocess, sample_json_rpc_notification
    ):
        """Test send() writes notification without waiting for response."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()

            await subprocess.send(sample_json_rpc_notification)

            mock_subprocess.stdin.write.assert_called_once()
            mock_subprocess.stdin.drain.assert_called_once()
            # Should NOT have called readline
            mock_subprocess.stdout.readline.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_json_multiline(
        self, subprocess_config, mock_subprocess, multiline_json_response
    ):
        """Test _read_json() handles multi-line JSON responses."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            # Split multi-line JSON into separate readline() calls
            lines = multiline_json_response.split("\n")
            mock_subprocess.stdout.readline.side_effect = [
                (line + "\n").encode("utf-8") for line in lines
            ]

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()

            result = await subprocess._read_json(mock_subprocess.stdout)

            # Should parse as valid JSON
            parsed = json.loads(result)
            assert parsed["id"] == 1
            assert parsed["result"]["sandbox_id"] == "test-123"

    @pytest.mark.asyncio
    async def test_read_json_skip_blank_lines(self, subprocess_config, mock_subprocess):
        """Test _read_json() skips blank lines before valid JSON."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            mock_subprocess.stdout.readline.side_effect = [
                b"\n",
                b"  \n",
                b'{"jsonrpc": "2.0", "result": "ok", "id": 1}\n',
            ]

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()

            result = await subprocess._read_json(mock_subprocess.stdout)

            parsed = json.loads(result)
            assert parsed["result"] == "ok"

    @pytest.mark.asyncio
    async def test_read_json_subprocess_terminated(
        self, subprocess_config, mock_subprocess
    ):
        """Test _read_json() raises error when subprocess exits unexpectedly."""
        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_subprocess

            # Simulate subprocess stdout closing
            mock_subprocess.stdout.readline.return_value = b""

            subprocess = MCPSubprocess(subprocess_config)
            await subprocess.start()

            with pytest.raises(MCPServerError, match="terminated while reading output"):
                await subprocess._read_json(mock_subprocess.stdout)


class TestSubprocessConfig:
    """Test suite for _resolve_subprocess_config function."""

    def test_resolve_config_basic(self):
        """Test resolving subprocess config without session ID."""
        with patch.dict(
            os.environ,
            {"MCP_SERVER_CMD": "python -u server.py", "PYTHONUNBUFFERED": "1"},
            clear=True,
        ):
            config = _resolve_subprocess_config()

            assert config.command == ["python", "-u", "server.py"]
            assert config.cwd is None
            assert config.env["PYTHONUNBUFFERED"] == "1"
            assert config.env["PYTHONIOENCODING"] == "UTF-8"

    def test_resolve_config_with_session(self):
        """Test session ID is added to environment."""
        with patch.dict(os.environ, {"MCP_SERVER_CMD": "python server.py"}, clear=True):
            config = _resolve_subprocess_config(session_id="sess-123")

            assert config.env["MCP_SESSION_ID"] == "sess-123"

    def test_resolve_config_with_cwd(self):
        """Test working directory is configured."""
        with patch.dict(
            os.environ,
            {"MCP_SERVER_CMD": "python server.py", "MCP_SERVER_CWD": "/custom/path"},
            clear=True,
        ):
            config = _resolve_subprocess_config()

            assert config.cwd == "/custom/path"

    def test_resolve_config_missing_cmd(self):
        """Test error when MCP_SERVER_CMD not set."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(MCPServerError, match="Set MCP_SERVER_CMD"):
                _resolve_subprocess_config()

    def test_resolve_config_empty_cmd(self):
        """Test error when MCP_SERVER_CMD is empty after parsing."""
        with patch.dict(os.environ, {"MCP_SERVER_CMD": "   "}, clear=True):
            with pytest.raises(MCPServerError, match="did not yield a command"):
                _resolve_subprocess_config()


class TestFastAPIApp:
    """Test suite for FastAPI application endpoints."""

    @pytest.fixture
    def client(self):
        """Create TestClient for FastAPI app."""
        app = _build_app()
        return TestClient(app)

    def test_health_check_no_subprocess(self, client):
        """Test /ping returns 200 when subprocess hasn't started yet."""
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_check_subprocess_running(self, client, mock_subprocess):
        """Test /ping returns 200 when subprocess is running."""
        with patch.dict(os.environ, {"MCP_SERVER_CMD": "python -u server.py"}):
            with patch(
                "asyncio.create_subprocess_exec", new_callable=AsyncMock
            ) as mock_create:
                mock_create.return_value = mock_subprocess

                # Trigger subprocess start by making invocation
                with patch.object(
                    MCPSubprocess, "invoke", new_callable=AsyncMock
                ) as mock_invoke:
                    mock_invoke.return_value = (
                        '{"jsonrpc": "2.0", "result": "ok", "id": 1}'
                    )
                    client.post(
                        "/invocations",
                        content='{"jsonrpc": "2.0", "method": "test", "id": 1}',
                    )

                # Health check should pass
                response = client.get("/ping")
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}

    def test_health_check_subprocess_exited(self, client, mock_subprocess):
        """Test /ping returns 503 when subprocess has exited."""
        with patch.dict(os.environ, {"MCP_SERVER_CMD": "python -u server.py"}):
            with patch(
                "asyncio.create_subprocess_exec", new_callable=AsyncMock
            ) as mock_create:
                # Start with process running
                mock_subprocess.returncode = None
                mock_create.return_value = mock_subprocess

                # Trigger subprocess start
                with patch.object(
                    MCPSubprocess, "invoke", new_callable=AsyncMock
                ) as mock_invoke:
                    mock_invoke.return_value = (
                        '{"jsonrpc": "2.0", "result": "ok", "id": 1}'
                    )
                    client.post(
                        "/invocations",
                        content='{"jsonrpc": "2.0", "method": "test", "id": 1}',
                    )

                # Now simulate subprocess exiting
                mock_subprocess.returncode = 1

                # Health check should fail
                response = client.get("/ping")
                assert response.status_code == 503
                assert "not running" in response.json()["detail"]

    def test_invocation_json_rpc_request(self, client, mock_subprocess):
        """Test /invocations handles JSON-RPC request with response."""
        with patch.dict(os.environ, {"MCP_SERVER_CMD": "python -u server.py"}):
            with patch(
                "asyncio.create_subprocess_exec", new_callable=AsyncMock
            ) as mock_create:
                mock_create.return_value = mock_subprocess

                with patch.object(
                    MCPSubprocess, "invoke", new_callable=AsyncMock
                ) as mock_invoke:
                    mock_invoke.return_value = (
                        '{"jsonrpc": "2.0", "result": {"test": "data"}, "id": 1}'
                    )

                    response = client.post(
                        "/invocations",
                        content='{"jsonrpc": "2.0", "method": "tools/call", "id": 1}',
                    )

                    assert response.status_code == 200
                    assert response.json() == {
                        "jsonrpc": "2.0",
                        "result": {"test": "data"},
                        "id": 1,
                    }

    def test_invocation_json_rpc_notification(self, client, mock_subprocess):
        """Test /invocations handles JSON-RPC notification (no response)."""
        with patch.dict(os.environ, {"MCP_SERVER_CMD": "python -u server.py"}):
            with patch(
                "asyncio.create_subprocess_exec", new_callable=AsyncMock
            ) as mock_create:
                mock_create.return_value = mock_subprocess

                with patch.object(
                    MCPSubprocess, "send", new_callable=AsyncMock
                ) as mock_send:
                    response = client.post(
                        "/invocations",
                        content='{"jsonrpc": "2.0", "method": "notifications/cancelled"}',
                    )

                    assert response.status_code == 204
                    mock_send.assert_called_once()

    def test_invocation_empty_body(self, client):
        """Test /invocations returns 400 for empty request body."""
        response = client.post("/invocations", content="")
        assert response.status_code == 400
        assert "empty" in response.json()["detail"]

    def test_invocation_invalid_utf8(self, client):
        """Test /invocations returns 400 for non-UTF-8 body."""
        response = client.post("/invocations", content=b"\xff\xfe")
        assert response.status_code == 400
        assert "UTF-8" in response.json()["detail"]

    def test_invocation_subprocess_error(self, client, mock_subprocess):
        """Test /invocations returns 500 when subprocess fails."""
        with patch.dict(os.environ, {"MCP_SERVER_CMD": "python -u server.py"}):
            with patch(
                "asyncio.create_subprocess_exec", new_callable=AsyncMock
            ) as mock_create:
                mock_create.return_value = mock_subprocess

                with patch.object(
                    MCPSubprocess, "invoke", new_callable=AsyncMock
                ) as mock_invoke:
                    mock_invoke.side_effect = MCPServerError("Subprocess crashed")

                    response = client.post(
                        "/invocations",
                        content='{"jsonrpc": "2.0", "method": "test", "id": 1}',
                    )

                    assert response.status_code == 500
                    assert "Subprocess crashed" in response.json()["detail"]

    def test_session_id_propagation(self, client, mock_subprocess):
        """Test session ID from AgentCore header is propagated to subprocess."""
        with patch.dict(os.environ, {"MCP_SERVER_CMD": "python -u server.py"}):
            with patch(
                "asyncio.create_subprocess_exec", new_callable=AsyncMock
            ) as mock_create:
                mock_create.return_value = mock_subprocess

                with patch.object(
                    MCPSubprocess, "invoke", new_callable=AsyncMock
                ) as mock_invoke:
                    mock_invoke.return_value = (
                        '{"jsonrpc": "2.0", "result": "ok", "id": 1}'
                    )

                    client.post(
                        "/invocations",
                        content='{"jsonrpc": "2.0", "method": "test", "id": 1}',
                        headers={
                            "x-amzn-bedrock-agentcore-runtime-session-id": "session-abc-123"
                        },
                    )

                    # Verify subprocess was started with session ID in environment
                    call_kwargs = mock_create.call_args.kwargs
                    assert "env" in call_kwargs
                    assert call_kwargs["env"].get("MCP_SESSION_ID") == "session-abc-123"
