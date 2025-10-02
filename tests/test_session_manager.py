"""Tests for mcp_agentcore_proxy.session_manager module."""

import uuid
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from mcp_agentcore_proxy.session_manager import (
    RuntimeSessionConfig,
    RuntimeSessionError,
    RuntimeSessionManager,
)


class TestRuntimeSessionManager:
    """Test suite for RuntimeSessionManager."""

    def test_session_mode(self):
        """Test session mode generates a stable session ID."""
        config = RuntimeSessionConfig(mode="session")
        manager = RuntimeSessionManager(config)

        session_id = manager.next_session_id()

        # Should start with "session-"
        assert session_id.startswith("session-")

        # Should be stable across calls
        assert manager.next_session_id() == session_id
        assert manager.next_session_id() == session_id

        # Should be a valid UUID format
        uuid_part = session_id.replace("session-", "")
        assert uuid.UUID(uuid_part)

    def test_request_mode(self):
        """Test request mode generates a new ID for each request."""
        config = RuntimeSessionConfig(mode="request")
        manager = RuntimeSessionManager(config)

        session_id_1 = manager.next_session_id()
        session_id_2 = manager.next_session_id()
        session_id_3 = manager.next_session_id()

        # All should start with "request-"
        assert session_id_1.startswith("request-")
        assert session_id_2.startswith("request-")
        assert session_id_3.startswith("request-")

        # All should be different
        assert session_id_1 != session_id_2
        assert session_id_2 != session_id_3
        assert session_id_1 != session_id_3

        # All should be valid UUID format
        for sid in [session_id_1, session_id_2, session_id_3]:
            uuid_part = sid.replace("request-", "")
            assert uuid.UUID(uuid_part)

    def test_identity_mode_success(self, mock_sts_client):
        """Test identity mode derives session ID from caller identity."""
        with patch("boto3.client", return_value=mock_sts_client):
            config = RuntimeSessionConfig(mode="identity")
            manager = RuntimeSessionManager(config)

            session_id = manager.next_session_id()

            # Should start with "identity-"
            assert session_id.startswith("identity-")

            # Should be stable across calls
            assert manager.next_session_id() == session_id

            # Should be deterministic for same identity
            manager2 = RuntimeSessionManager(config)
            assert manager2.next_session_id() == session_id

    def test_identity_mode_sts_error(self):
        """Test identity mode raises error when STS call fails."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "GetCallerIdentity",
        )

        with patch("boto3.client", return_value=mock_sts):
            config = RuntimeSessionConfig(mode="identity")

            with pytest.raises(
                RuntimeSessionError, match="Unable to call sts:GetCallerIdentity"
            ):
                RuntimeSessionManager(config)

    def test_identity_mode_incomplete_response(self):
        """Test identity mode raises error when STS returns incomplete data."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Account": "123456789012",
            # Missing UserId and Arn
        }

        with patch("boto3.client", return_value=mock_sts):
            config = RuntimeSessionConfig(mode="identity")

            with pytest.raises(RuntimeSessionError, match="incomplete identity"):
                RuntimeSessionManager(config)

    def test_invalid_mode(self):
        """Test invalid mode raises error."""
        config = RuntimeSessionConfig(mode="invalid")

        with pytest.raises(
            RuntimeSessionError, match="Unsupported runtime session mode"
        ):
            RuntimeSessionManager(config)

    def test_identity_determinism(self, mock_sts_client):
        """Test identity mode produces same ID for same AWS identity."""
        with patch("boto3.client", return_value=mock_sts_client):
            config = RuntimeSessionConfig(mode="identity")

            # Create multiple managers with same identity
            manager1 = RuntimeSessionManager(config)
            manager2 = RuntimeSessionManager(config)
            manager3 = RuntimeSessionManager(config)

            id1 = manager1.next_session_id()
            id2 = manager2.next_session_id()
            id3 = manager3.next_session_id()

            # All should be identical
            assert id1 == id2 == id3

    def test_identity_uniqueness(self):
        """Test identity mode produces different IDs for different AWS identities."""
        identity1 = {
            "UserId": "AIDACKCEVSQ6C2EXAMPLE",
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/Alice",
        }
        identity2 = {
            "UserId": "AIDAI23HXX2LO6EXAMPLE",
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/Bob",
        }

        mock_sts1 = MagicMock()
        mock_sts1.get_caller_identity.return_value = identity1

        mock_sts2 = MagicMock()
        mock_sts2.get_caller_identity.return_value = identity2

        with patch("boto3.client", return_value=mock_sts1):
            config = RuntimeSessionConfig(mode="identity")
            manager1 = RuntimeSessionManager(config)
            id1 = manager1.next_session_id()

        with patch("boto3.client", return_value=mock_sts2):
            config = RuntimeSessionConfig(mode="identity")
            manager2 = RuntimeSessionManager(config)
            id2 = manager2.next_session_id()

        # Different identities should produce different session IDs
        assert id1 != id2

    def test_session_mode_uniqueness(self):
        """Test session mode produces different IDs for different manager instances."""
        config = RuntimeSessionConfig(mode="session")

        manager1 = RuntimeSessionManager(config)
        manager2 = RuntimeSessionManager(config)
        manager3 = RuntimeSessionManager(config)

        id1 = manager1.next_session_id()
        id2 = manager2.next_session_id()
        id3 = manager3.next_session_id()

        # Different manager instances should have different session IDs
        assert id1 != id2
        assert id2 != id3
        assert id1 != id3
