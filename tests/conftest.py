"""Shared pytest fixtures for agentcore-mcp-proxy tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_subprocess():
    """Mock asyncio.subprocess.Process for testing subprocess interactions."""
    process = MagicMock()
    process.returncode = None

    # Create async mock for stdin
    stdin = AsyncMock()
    stdin.write = MagicMock()  # write is synchronous
    stdin.drain = AsyncMock()
    process.stdin = stdin

    # Create async mock for stdout
    stdout = AsyncMock()
    stdout.readline = AsyncMock()
    process.stdout = stdout

    # Create async mock for stderr that returns empty bytes to terminate _drain_stderr
    stderr = AsyncMock()
    stderr.readline = AsyncMock(return_value=b"")
    process.stderr = stderr

    process.wait = AsyncMock()
    process.send_signal = MagicMock()
    process.kill = MagicMock()
    return process


@pytest.fixture
def mock_sts_client():
    """Mock boto3 STS client for testing AWS session resolution."""
    client = MagicMock()
    client.get_caller_identity.return_value = {
        "UserId": "AIDACKCEVSQ6C2EXAMPLE",
        "Account": "123456789012",
        "Arn": "arn:aws:iam::123456789012:user/DevUser",
    }
    client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIAIOSFODNN7EXAMPLE",
            "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "SessionToken": "FwoGZXIvYXdzEBYaDJ...",
            "Expiration": "2025-10-02T12:00:00Z",
        },
        "AssumedRoleUser": {
            "AssumedRoleId": "AROA3XFRBF535PLBIFPI4:session-name",
            "Arn": "arn:aws:sts::123456789012:assumed-role/RoleName/session-name",
        },
    }
    return client


@pytest.fixture
def mock_session(mock_sts_client):
    """Mock boto3 Session for testing AWS integration."""
    session = MagicMock()
    session.client.return_value = mock_sts_client
    session.region_name = "us-east-1"
    return session


@pytest.fixture
def sample_json_rpc_request():
    """Sample JSON-RPC request payload."""
    return '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "whoami"}, "id": 1}'


@pytest.fixture
def sample_json_rpc_notification():
    """Sample JSON-RPC notification (no id field)."""
    return '{"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": "req-123"}}'


@pytest.fixture
def sample_json_rpc_response():
    """Sample JSON-RPC response payload."""
    return '{"jsonrpc": "2.0", "result": {"sandbox_id": "test-123"}, "id": 1}'


@pytest.fixture
def multiline_json_response():
    """Sample multi-line JSON response."""
    return """{
  "jsonrpc": "2.0",
  "result": {
    "sandbox_id": "test-123"
  },
  "id": 1
}"""
