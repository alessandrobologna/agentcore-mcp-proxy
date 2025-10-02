"""Runtime session management for AgentCore."""

import hashlib
import json
import uuid
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class RuntimeSessionError(Exception):
    """Raised when a runtime session ID cannot be established."""


@dataclass(frozen=True)
class RuntimeSessionConfig:
    mode: str


class RuntimeSessionManager:
    """Resolve AgentCore runtime session IDs based on configuration."""

    def __init__(self, config: RuntimeSessionConfig):
        self._mode = config.mode
        self._session_id: str | None = None

        if self._mode == "identity":
            self._session_id = self._derive_identity_session_id()
        elif self._mode == "session":
            self._session_id = f"session-{uuid.uuid4()}"
        elif self._mode == "request":
            self._session_id = None
        else:
            raise RuntimeSessionError(f"Unsupported runtime session mode: {self._mode}")

    @staticmethod
    def _derive_identity_session_id() -> str:
        sts = boto3.client("sts")
        try:
            ident = sts.get_caller_identity()
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeSessionError("Unable to call sts:GetCallerIdentity") from exc

        account = ident.get("Account")
        user_id = ident.get("UserId")
        arn = ident.get("Arn")
        if not all([account, user_id, arn]):
            raise RuntimeSessionError(
                "sts:GetCallerIdentity returned incomplete identity"
            )

        uid = json.dumps([account, user_id, arn], separators=(",", ":"))
        hash_bytes = hashlib.sha256(uid.encode("utf-8")).digest()
        # Convert first 16 bytes to UUID format
        uuid_from_hash = uuid.UUID(bytes=hash_bytes[:16])
        return f"identity-{uuid_from_hash}"

    def next_session_id(self) -> str:
        if self._mode == "request":
            return f"request-{uuid.uuid4()}"

        if not self._session_id:
            raise RuntimeSessionError("Runtime session ID was not initialized")

        return self._session_id
