# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "boto3",
# ]
# ///
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_CONTENT_TYPE = "application/json"
DEFAULT_ACCEPT = "application/json, text/event-stream"


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
            self._session_id = str(uuid.uuid4())
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
        return hashlib.sha256(uid.encode("utf-8")).hexdigest()

    def next_session_id(self) -> str:
        if self._mode == "request":
            return str(uuid.uuid4())

        if not self._session_id:
            raise RuntimeSessionError("Runtime session ID was not initialized")

        return self._session_id


def _resolve_runtime_session_config() -> RuntimeSessionConfig:
    mode_env = (os.getenv("RUNTIME_SESSION_MODE") or "").strip().lower()
    if mode_env:
        return RuntimeSessionConfig(mode=mode_env)
    return RuntimeSessionConfig(mode="identity")


def _error_response(request_id: Any, code: int, message: str) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


def _emit_event_stream(body_stream: Any) -> None:
    """Stream Server-Sent Events from AgentCore back to STDOUT."""
    event_data = []

    for raw_line in body_stream.iter_lines():
        if not raw_line:
            # Empty line marks end of an SSE event
            if event_data:
                complete_json = "".join(event_data)
                try:
                    json.loads(complete_json)  # Validate JSON
                    print(complete_json, flush=True)
                except json.JSONDecodeError:
                    pass  # Skip malformed JSON
                event_data = []
            continue

        line = raw_line.decode("utf-8", errors="replace")
        if line.startswith("data:"):
            event_data.append(line[5:].lstrip())

    # Handle any remaining data
    if event_data:
        complete_json = "".join(event_data)
        try:
            json.loads(complete_json)
            print(complete_json, flush=True)
        except json.JSONDecodeError:
            pass


def main() -> None:
    agent_arn = os.getenv("AGENTCORE_AGENT_ARN") or os.getenv("AGENT_ARN")
    if not agent_arn:
        print(
            _error_response(None, -32000, "Set AGENTCORE_AGENT_ARN (or AGENT_ARN)"),
            flush=True,
        )
        sys.exit(2)

    config = _resolve_runtime_session_config()

    try:
        session_manager = RuntimeSessionManager(config)
    except RuntimeSessionError as exc:
        print(_error_response(None, -32000, str(exc)), flush=True)
        sys.exit(2)

    client = boto3.client("bedrock-agentcore")

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            print(_error_response(None, -32700, f"Parse error: {exc}"), flush=True)
            continue

        request_id = parsed.get("id") if isinstance(parsed, dict) else None

        try:
            next_runtime_session_id = session_manager.next_session_id()
            mcp_session_id = f"mcp-{next_runtime_session_id}"
            response = client.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                payload=line.encode("utf-8"),
                runtimeSessionId=next_runtime_session_id,
                mcpSessionId=mcp_session_id,
                contentType=DEFAULT_CONTENT_TYPE,
                accept=DEFAULT_ACCEPT,
            )
        except (BotoCoreError, ClientError) as exc:
            detail = getattr(exc, "response", None)
            message = (
                json.dumps(detail, default=str)
                if isinstance(detail, dict)
                else str(exc)
            )
            print(
                _error_response(
                    request_id, -32000, f"InvokeAgentRuntime error: {message}"
                ),
                flush=True,
            )
            continue

        body_stream = response.get("response")
        if body_stream is None:
            print(
                _error_response(
                    request_id, -32001, "Missing response body from InvokeAgentRuntime"
                ),
                flush=True,
            )
            continue

        try:
            response_ct = response.get("contentType", "").lower()
            if "text/event-stream" in response_ct:
                _emit_event_stream(body_stream)
            else:
                body = body_stream.read().decode("utf-8", errors="replace")
                # Only print non-empty responses
                if body.strip():
                    print(body, flush=True)
        except Exception as exc:
            print(
                _error_response(
                    request_id, -32002, f"Failed to process response body: {exc}"
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
