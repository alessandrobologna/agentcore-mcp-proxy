"""Tests for credential refresh behaviour in mcp_agentcore_proxy.client."""

import io
import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, UnauthorizedSSOTokenError

from mcp_agentcore_proxy import client as client_module


@pytest.fixture(autouse=True)
def _clear_debug_env(monkeypatch):
    """Ensure debug environment variables do not pollute test output."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("MCP_PROXY_DEBUG", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


def _expired_token_error() -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "ExpiredTokenException",
                "Message": "The security token included in the request is expired",
            }
        },
        "InvokeAgentRuntime",
    )


def test_main_refreshes_expired_credentials(monkeypatch, capsys):
    """Expired assume-role credentials should trigger a refresh and retry."""

    monkeypatch.setenv(
        "AGENTCORE_AGENT_ARN", "arn:aws:bedrock:us-east-1:123456789012:agent/test"
    )

    session_manager = MagicMock()
    session_manager.next_session_id.return_value = "session-1"
    monkeypatch.setattr(
        client_module, "RuntimeSessionManager", MagicMock(return_value=session_manager)
    )

    session_1 = MagicMock()
    client_1 = MagicMock()
    session_1.client.return_value = client_1

    session_2 = MagicMock()
    client_2 = MagicMock()
    session_2.client.return_value = client_2

    client_1.invoke_agent_runtime.side_effect = _expired_token_error()
    client_2.invoke_agent_runtime.return_value = {
        "response": io.BytesIO(b'{"jsonrpc":"2.0","id":1,"result":"ok"}'),
        "contentType": "application/json",
    }

    resolve_session = MagicMock(side_effect=[session_1, session_2])
    monkeypatch.setattr(client_module, "resolve_aws_session", resolve_session)

    request_payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "foo"})
    monkeypatch.setattr(client_module.sys, "stdin", io.StringIO(request_payload + "\n"))

    client_module.main()

    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line]
    # First line should be the MCP log notification, final line the AgentCore payload
    assert stdout_lines[-1] == '{"jsonrpc":"2.0","id":1,"result":"ok"}'
    assert any('"notifications/message"' in line for line in stdout_lines[:-1])

    assert resolve_session.call_count == 2
    assert client_1.invoke_agent_runtime.call_count == 1
    assert client_2.invoke_agent_runtime.call_count == 1
    assert session_manager.next_session_id.call_count == 1


def test_main_prompts_for_sso_login_on_start(monkeypatch, capsys):
    """If SSO session is invalid during startup, surface a helpful message."""

    monkeypatch.setenv(
        "AGENTCORE_AGENT_ARN", "arn:aws:bedrock:us-east-1:123456789012:agent/test"
    )
    monkeypatch.setenv("AWS_PROFILE", "dev-profile")

    session = MagicMock()
    session.client.side_effect = UnauthorizedSSOTokenError()
    monkeypatch.setattr(
        client_module, "resolve_aws_session", MagicMock(return_value=session)
    )

    with pytest.raises(SystemExit) as excinfo:
        client_module.main()

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "aws sso login --profile dev-profile" in captured.err


def test_main_prompts_for_sso_login_during_request(monkeypatch, capsys):
    """When SSO expires mid-run, emit JSON-RPC error instructing re-login."""

    monkeypatch.setenv(
        "AGENTCORE_AGENT_ARN", "arn:aws:bedrock:us-east-1:123456789012:agent/test"
    )
    monkeypatch.setenv("AWS_PROFILE", "dev-profile")

    session_manager = MagicMock()
    session_manager.next_session_id.return_value = "session-1"
    monkeypatch.setattr(
        client_module, "RuntimeSessionManager", MagicMock(return_value=session_manager)
    )

    session = MagicMock()
    client = MagicMock()
    session.client.return_value = client
    client.invoke_agent_runtime.side_effect = UnauthorizedSSOTokenError()
    monkeypatch.setattr(
        client_module, "resolve_aws_session", MagicMock(return_value=session)
    )

    request_payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "foo"})
    monkeypatch.setattr(client_module.sys, "stdin", io.StringIO(request_payload + "\n"))

    client_module.main()

    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line]
    assert any("aws sso login --profile dev-profile" in line for line in stdout_lines)
