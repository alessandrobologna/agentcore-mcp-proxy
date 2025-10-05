"""Tests for mcp_agentcore_proxy.aws_session module."""

import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError, UnauthorizedSSOTokenError

from mcp_agentcore_proxy.aws_session import (
    AssumeRoleError,
    format_sso_login_message,
    resolve_aws_session,
)


class TestResolveAwsSession:
    """Test suite for resolve_aws_session function."""

    def test_default_session_no_assume_role(self):
        """Return default session when AGENTCORE_ASSUME_ROLE_ARN is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session"
            ) as mock_session_class:
                session = resolve_aws_session()

                mock_session_class.assert_called_once_with()
                assert session is mock_session_class.return_value

    def test_default_session_empty_assume_role(self):
        """Return default session when AGENTCORE_ASSUME_ROLE_ARN is empty."""
        with patch.dict(os.environ, {"AGENTCORE_ASSUME_ROLE_ARN": "   "}, clear=True):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session"
            ) as mock_session_class:
                session = resolve_aws_session()

                mock_session_class.assert_called_once_with()
                assert session is mock_session_class.return_value

    def test_assume_role_success_default_session_name(self):
        """Assume role uses default session name when none provided."""
        base_session = MagicMock()
        assumed_session = MagicMock()

        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session",
                return_value=base_session,
            ) as mock_session_class:
                with patch(
                    "mcp_agentcore_proxy.aws_session.assume_role_with_refresh",
                    return_value=assumed_session,
                ) as mock_assume_role:
                    session = resolve_aws_session()

                    assert session is assumed_session
                    mock_session_class.assert_called_once_with()
                    mock_assume_role.assert_called_once_with(
                        base_session,
                        "arn:aws:iam::111122223333:role/TestRole",
                        RoleSessionName="mcpAgentCoreProxy",
                    )

    def test_assume_role_success_custom_session_name(self):
        """Assume role honors custom session name if provided."""
        base_session = MagicMock()
        assumed_session = MagicMock()

        with patch.dict(
            os.environ,
            {
                "AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole",
                "AGENTCORE_ASSUME_ROLE_SESSION_NAME": "CustomSessionName",
            },
            clear=True,
        ):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session",
                return_value=base_session,
            ):
                with patch(
                    "mcp_agentcore_proxy.aws_session.assume_role_with_refresh",
                    return_value=assumed_session,
                ) as mock_assume_role:
                    session = resolve_aws_session()

                    assert session is assumed_session
                    mock_assume_role.assert_called_once_with(
                        base_session,
                        "arn:aws:iam::111122223333:role/TestRole",
                        RoleSessionName="CustomSessionName",
                    )

    def test_assume_role_empty_session_name(self):
        """Empty session name falls back to default value."""
        base_session = MagicMock()
        assumed_session = MagicMock()

        with patch.dict(
            os.environ,
            {
                "AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole",
                "AGENTCORE_ASSUME_ROLE_SESSION_NAME": "   ",
            },
            clear=True,
        ):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session",
                return_value=base_session,
            ):
                with patch(
                    "mcp_agentcore_proxy.aws_session.assume_role_with_refresh",
                    return_value=assumed_session,
                ) as mock_assume_role:
                    session = resolve_aws_session()

                    assert session is assumed_session
                    mock_assume_role.assert_called_once_with(
                        base_session,
                        "arn:aws:iam::111122223333:role/TestRole",
                        RoleSessionName="mcpAgentCoreProxy",
                    )

    @pytest.mark.parametrize("exc_type", [ClientError, BotoCoreError, ValueError])
    def test_assume_role_wrapped_errors(self, exc_type):
        """Errors from aws-assume-role-lib are wrapped in AssumeRoleError."""
        if exc_type is ClientError:
            error_instance = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}},
                "AssumeRole",
            )
        elif exc_type is BotoCoreError:
            error_instance = BotoCoreError(error_message="boom")
        else:
            error_instance = ValueError("boom")

        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session",
                return_value=MagicMock(),
            ):
                with patch(
                    "mcp_agentcore_proxy.aws_session.assume_role_with_refresh",
                    side_effect=error_instance,
                ):
                    with pytest.raises(AssumeRoleError, match="Unable to assume role"):
                        resolve_aws_session()

    def test_assume_role_unknown_error_wrapped(self):
        """Unexpected exceptions are wrapped with descriptive message."""
        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session",
                return_value=MagicMock(),
            ):
                with patch(
                    "mcp_agentcore_proxy.aws_session.assume_role_with_refresh",
                    side_effect=RuntimeError("boom"),
                ):
                    with pytest.raises(AssumeRoleError, match="Unexpected error"):
                        resolve_aws_session()

    def test_multiple_calls_no_caching(self):
        """Each call to resolve_aws_session re-invokes aws-assume-role-lib."""
        base_session = MagicMock()

        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session",
                return_value=base_session,
            ):
                with patch(
                    "mcp_agentcore_proxy.aws_session.assume_role_with_refresh",
                    side_effect=[MagicMock(), MagicMock()],
                ) as mock_assume_role:
                    _ = resolve_aws_session()
                    _ = resolve_aws_session()

                    assert mock_assume_role.call_count == 2

    def test_assume_role_sso_token_expired_message(self):
        """SSO expiration surfaces helpful login guidance."""

        base_session = MagicMock()

        with patch.dict(
            os.environ,
            {
                "AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole",
                "AWS_PROFILE": "dev-profile",
            },
            clear=True,
        ):
            with patch(
                "mcp_agentcore_proxy.aws_session.boto3.session.Session",
                return_value=base_session,
            ):
                with patch(
                    "mcp_agentcore_proxy.aws_session.assume_role_with_refresh",
                    side_effect=UnauthorizedSSOTokenError(),
                ):
                    with pytest.raises(AssumeRoleError) as excinfo:
                        resolve_aws_session()

        assert "aws sso login --profile dev-profile" in str(excinfo.value)


def test_format_sso_login_message_variants(monkeypatch):
    """format_sso_login_message reflects AWS_PROFILE when provided."""
    monkeypatch.setenv("AWS_PROFILE", "dev-profile")
    assert "--profile dev-profile" in format_sso_login_message()
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    assert "--profile" not in format_sso_login_message()
