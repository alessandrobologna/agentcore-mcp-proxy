"""Tests for mcp_agentcore_proxy.aws_session module."""

import os
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from mcp_agentcore_proxy.aws_session import AssumeRoleError, resolve_aws_session


class TestResolveAwsSession:
    """Test suite for resolve_aws_session function."""

    def test_default_session_no_assume_role(self):
        """Test returns default session when AGENTCORE_ASSUME_ROLE_ARN is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("boto3.session.Session") as mock_session_class:
                session = resolve_aws_session()

                mock_session_class.assert_called_once_with()
                assert session is mock_session_class.return_value

    def test_default_session_empty_assume_role(self):
        """Test returns default session when AGENTCORE_ASSUME_ROLE_ARN is empty."""
        with patch.dict(os.environ, {"AGENTCORE_ASSUME_ROLE_ARN": "   "}, clear=True):
            with patch("boto3.session.Session") as mock_session_class:
                session = resolve_aws_session()

                mock_session_class.assert_called_once_with()
                assert session is mock_session_class.return_value

    def test_assume_role_success_default_session_name(self, mock_sts_client):
        """Test assume role with default session name."""
        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch("boto3.client", return_value=mock_sts_client):
                with patch("boto3.session.Session") as mock_session_class:
                    _ = resolve_aws_session()

                    # Verify assume_role was called with default session name
                    mock_sts_client.assume_role.assert_called_once_with(
                        RoleArn="arn:aws:iam::111122223333:role/TestRole",
                        RoleSessionName="mcpAgentCoreProxy",
                    )

                    # Verify session was created with temporary credentials
                    mock_session_class.assert_called_once_with(
                        aws_access_key_id="ASIAIOSFODNN7EXAMPLE",
                        aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                        aws_session_token="FwoGZXIvYXdzEBYaDJ...",
                    )

    def test_assume_role_success_custom_session_name(self, mock_sts_client):
        """Test assume role with custom session name."""
        with patch.dict(
            os.environ,
            {
                "AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole",
                "AGENTCORE_ASSUME_ROLE_SESSION_NAME": "CustomSessionName",
            },
            clear=True,
        ):
            with patch("boto3.client", return_value=mock_sts_client):
                with patch("boto3.session.Session"):
                    _ = resolve_aws_session()

                    # Verify assume_role was called with custom session name
                    mock_sts_client.assume_role.assert_called_once_with(
                        RoleArn="arn:aws:iam::111122223333:role/TestRole",
                        RoleSessionName="CustomSessionName",
                    )

    def test_assume_role_empty_session_name(self, mock_sts_client):
        """Test assume role with empty custom session name falls back to default."""
        with patch.dict(
            os.environ,
            {
                "AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole",
                "AGENTCORE_ASSUME_ROLE_SESSION_NAME": "   ",
            },
            clear=True,
        ):
            with patch("boto3.client", return_value=mock_sts_client):
                with patch("boto3.session.Session"):
                    _ = resolve_aws_session()

                    # Should use default session name
                    mock_sts_client.assume_role.assert_called_once_with(
                        RoleArn="arn:aws:iam::111122223333:role/TestRole",
                        RoleSessionName="mcpAgentCoreProxy",
                    )

    def test_assume_role_client_error(self):
        """Test assume role raises AssumeRoleError on ClientError."""
        mock_sts = MagicMock()
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}},
            "AssumeRole",
        )

        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch("boto3.client", return_value=mock_sts):
                with pytest.raises(AssumeRoleError, match="Unable to assume role"):
                    resolve_aws_session()

    def test_assume_role_missing_credentials(self):
        """Test assume role raises AssumeRoleError when credentials are missing."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "AssumedRoleUser": {
                "AssumedRoleId": "AROA3XFRBF535PLBIFPI4:session-name",
                "Arn": "arn:aws:sts::123456789012:assumed-role/RoleName/session-name",
            }
            # Missing Credentials key
        }

        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch("boto3.client", return_value=mock_sts):
                with pytest.raises(AssumeRoleError, match="missing credentials"):
                    resolve_aws_session()

    def test_assume_role_incomplete_credentials(self, mock_sts_client):
        """Test session creation with complete credentials."""
        # Modify mock to return incomplete credentials
        mock_sts_client.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIAIOSFODNN7EXAMPLE",
                # Missing SecretAccessKey and SessionToken
            }
        }

        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch("boto3.client", return_value=mock_sts_client):
                with patch("boto3.session.Session") as mock_session_class:
                    _ = resolve_aws_session()

                    # Session should be created even with incomplete credentials
                    # (boto3 will handle validation)
                    mock_session_class.assert_called_once()
                    call_kwargs = mock_session_class.call_args.kwargs
                    assert call_kwargs["aws_access_key_id"] == "ASIAIOSFODNN7EXAMPLE"
                    assert call_kwargs["aws_secret_access_key"] is None
                    assert call_kwargs["aws_session_token"] is None

    def test_multiple_calls_no_caching(self, mock_sts_client):
        """Test each call to resolve_aws_session assumes role again (no caching)."""
        with patch.dict(
            os.environ,
            {"AGENTCORE_ASSUME_ROLE_ARN": "arn:aws:iam::111122223333:role/TestRole"},
            clear=True,
        ):
            with patch("boto3.client", return_value=mock_sts_client):
                with patch("boto3.session.Session"):
                    _ = resolve_aws_session()
                    _ = resolve_aws_session()

                    # Should call assume_role twice (no caching)
                    assert mock_sts_client.assume_role.call_count == 2
