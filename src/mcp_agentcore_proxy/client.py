# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "boto3",
#     "aws-assume-role-lib",
# ]
# ///
import json
import os
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for absolute imports when run as script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, UnauthorizedSSOTokenError

from mcp_agentcore_proxy.aws_session import (
    AssumeRoleError,
    format_sso_login_message,
    resolve_aws_session,
)
from mcp_agentcore_proxy.session_manager import (
    RuntimeSessionConfig,
    RuntimeSessionError,
    RuntimeSessionManager,
)

DEFAULT_CONTENT_TYPE = "application/json"
DEFAULT_ACCEPT = "application/json, text/event-stream"


def _resolve_runtime_session_config() -> RuntimeSessionConfig:
    mode_env = (os.getenv("RUNTIME_SESSION_MODE") or "").strip().lower()
    if mode_env:
        return RuntimeSessionConfig(mode=mode_env)
    return RuntimeSessionConfig(mode="session")


def _error_response(request_id: Any, code: int, message: str) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


def _print_error(request_id: Any, code: int, message: str) -> None:
    """Print JSON-RPC error response to stdout, skipping notifications."""
    # Per JSON-RPC spec: notifications (requests without id) should not receive responses
    # Exception: parse errors must send error response with id=null per spec
    if request_id is None and code != -32700:
        return
    print(_error_response(request_id, code, message), flush=True)


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
            "Error: Set AGENTCORE_AGENT_ARN (or AGENT_ARN)", file=sys.stderr, flush=True
        )
        sys.exit(2)

    config = _resolve_runtime_session_config()

    try:
        session_manager = RuntimeSessionManager(config)
    except RuntimeSessionError as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)

    client_config = Config(
        read_timeout=int(os.getenv("AGENTCORE_READ_TIMEOUT", "300")),
        connect_timeout=int(os.getenv("AGENTCORE_CONNECT_TIMEOUT", "10")),
        retries={"max_attempts": 2},
    )

    def _create_client() -> tuple[Any, Any]:
        """Create a fresh AgentCore client from a newly resolved AWS session."""
        session_local = resolve_aws_session()
        try:
            client_local = session_local.client(
                "bedrock-agentcore", config=client_config
            )
        except UnauthorizedSSOTokenError as exc:
            raise AssumeRoleError(format_sso_login_message()) from exc
        return session_local, client_local

    try:
        session, client = _create_client()
    except AssumeRoleError as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)

    # Cache last initialize payload for potential handshake replay
    last_initialize_payload: str | None = None
    # Guard to avoid infinite retry loops per process lifetime
    replay_attempted: bool = False

    def _debug(msg: str) -> None:
        lvl = (os.getenv("LOG_LEVEL") or "").upper()
        if lvl == "DEBUG" or os.getenv("MCP_PROXY_DEBUG") == "1":
            print(f"[mcp-agentcore-proxy] {msg}", file=sys.stderr, flush=True)

    def _emit_mcp_log(
        level: str, data: Any, logger: str | None = "mcp-agentcore-proxy"
    ) -> None:
        """Emit an MCP logging notification to the IDE (client) via stdout.

        Always emits; intended to be low-volume (container restarts are rare).
        """
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {
                "level": level,
                "data": data,
            },
        }
        if logger:
            payload["params"]["logger"] = logger
        print(json.dumps(payload), flush=True)

    def _is_expired_token_error(exc: ClientError) -> bool:
        error = exc.response if isinstance(getattr(exc, "response", None), dict) else {}
        if not isinstance(error, dict):
            return False
        code = error.get("Error", {}).get("Code")
        if not isinstance(code, str):
            return False
        return code in {
            "ExpiredToken",
            "ExpiredTokenException",
            "InvalidClientTokenId",
            "RequestExpired",
            "UnrecognizedClientException",
        }

    def _invoke_raw(payload: str) -> dict[str, Any]:
        """Invoke AgentCore and return the raw boto3 response dict.

        The caller decides how to handle streaming vs JSON bodies.
        """
        nonlocal session, client
        next_runtime_session_id = session_manager.next_session_id()
        attempts = 0

        while True:
            attempts += 1
            try:
                return client.invoke_agent_runtime(
                    agentRuntimeArn=agent_arn,
                    payload=payload.encode("utf-8"),
                    runtimeSessionId=next_runtime_session_id,
                    mcpSessionId=f"mcp-{next_runtime_session_id}",
                    contentType=DEFAULT_CONTENT_TYPE,
                    accept=DEFAULT_ACCEPT,
                )
            except ClientError as exc:
                if attempts == 1 and _is_expired_token_error(exc):
                    _debug(
                        "AWS credentials expired; attempting to refresh session and retry"
                    )
                    _emit_mcp_log(
                        "debug",
                        "AWS credentials expired; refreshing assume-role session before retrying request.",
                    )
                    session, client = _create_client()
                    continue
                raise
            except UnauthorizedSSOTokenError as exc:
                raise AssumeRoleError(format_sso_login_message()) from exc

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            _print_error(None, -32700, f"Parse error: {exc}")
            continue

        request_id = parsed.get("id") if isinstance(parsed, dict) else None

        # Skip notifications EXCEPT for 'notifications/initialized' which the server needs
        # Notifications don't expect a response, so we won't wait for one
        is_notification = request_id is None and isinstance(parsed, dict)
        is_initialized_notification = (
            is_notification and parsed.get("method") == "notifications/initialized"
        )

        # Skip all notifications except notifications/initialized
        if is_notification and not is_initialized_notification:
            continue

        # Cache initialize/initialized messages for potential replay
        if isinstance(parsed, dict) and parsed.get("method") == "initialize":
            last_initialize_payload = line
        # No need to cache initialized notification; we can safely re-send one

        try:
            resp = _invoke_raw(line)
        except AssumeRoleError as exc:
            _debug(f"Credential refresh failed: {exc}")
            _emit_mcp_log("error", f"Credential refresh failed: {exc}")
            _print_error(request_id, -32000, f"Credential refresh failed: {exc}")
            continue
        except (BotoCoreError, ClientError) as exc:
            # HTTP 204 (No Content) is the correct response for notifications
            # Don't treat it as an error when we're sending a notification
            detail = getattr(exc, "response", None)
            if (
                is_initialized_notification
                and isinstance(detail, dict)
                and detail.get("ResponseMetadata", {}).get("HTTPStatusCode") == 204
            ):
                # Silently ignore 204 for notifications - it's expected
                continue

            message = (
                json.dumps(detail, default=str)
                if isinstance(detail, dict)
                else str(exc)
            )
            _print_error(request_id, -32000, f"InvokeAgentRuntime error: {message}")
            continue
        # Handle streaming vs JSON body
        body_stream = resp.get("response")
        if body_stream is None:
            _print_error(
                request_id, -32001, "Missing response body from InvokeAgentRuntime"
            )
            continue

        response_ct = resp.get("contentType", "").lower()
        if "text/event-stream" in response_ct:
            _emit_event_stream(body_stream)
            continue

        # JSON body
        try:
            body = body_stream.read().decode("utf-8", errors="replace")
        except Exception as exc:
            _print_error(request_id, -32002, f"Failed to process response body: {exc}")
            continue

        try:
            parsed_body = json.loads(body) if body and body.strip() else None
        except json.JSONDecodeError as exc:
            _print_error(request_id, -32002, f"Failed to process response body: {exc}")
            continue

        # Detect uninitialized stdio server case and perform handshake replay once per process
        should_attempt_replay = (
            # Only for non-initialize requests with an error
            isinstance(parsed, dict)
            and parsed.get("method") != "initialize"
            and isinstance(parsed_body, dict)
            and isinstance(parsed_body.get("error"), dict)
            and parsed_body["error"].get("code") == -32602
            and last_initialize_payload is not None
            and not replay_attempted
        )

        if should_attempt_replay:
            replay_attempted = True
            try:
                _debug(
                    "Handshake replay triggered due to -32602: sending initialize "
                    "+ notifications/initialized, then retrying original request"
                )
                _emit_mcp_log(
                    "debug",
                    "Handshake replay triggered (-32602). Re-sending initialize and initialized, then retrying request.",
                )
                # 1) Re-send cached initialize (suppress output)
                replay_resp = _invoke_raw(last_initialize_payload)
                replay_stream = replay_resp.get("response")
                if (
                    replay_stream is not None
                    and "text/event-stream"
                    not in replay_resp.get("contentType", "").lower()
                ):
                    # Consume without printing
                    replay_stream.read()
                # 2) Re-send notifications/initialized (suppress output)
                #    If we never saw it, still send one — it is harmless for servers expecting the handshake
                try:
                    notif_resp = _invoke_raw(
                        json.dumps(
                            {"jsonrpc": "2.0", "method": "notifications/initialized"}
                        )
                    )
                    notif_stream = notif_resp.get("response")
                    if (
                        notif_stream is not None
                        and "text/event-stream"
                        not in notif_resp.get("contentType", "").lower()
                    ):
                        notif_stream.read()
                except (BotoCoreError, ClientError):
                    # Likely 204 No Content; safe to ignore
                    pass
                # 3) Retry original request and print its output
                final_resp = _invoke_raw(line)
                final_stream = final_resp.get("response")
                if final_stream is None:
                    _print_error(
                        request_id,
                        -32001,
                        "Missing response body from InvokeAgentRuntime",
                    )
                else:
                    final_ct = final_resp.get("contentType", "").lower()
                    if "text/event-stream" in final_ct:
                        _emit_event_stream(final_stream)
                    else:
                        final_body = final_stream.read().decode(
                            "utf-8", errors="replace"
                        )
                        if final_body.strip():
                            print(final_body, flush=True)
                _debug(
                    "Handshake replay succeeded; original request retried successfully"
                )
                _emit_mcp_log(
                    "debug",
                    "Handshake replay succeeded; original request retried successfully.",
                )
                continue
            except (BotoCoreError, ClientError) as exc:
                # Fall back to original error if replay fails
                _debug(f"Handshake replay failed: {exc}")
                _emit_mcp_log("warning", f"Handshake replay failed: {exc}")

        # No replay or replay not applicable: print original body (if any)
        if body and body.strip():
            print(body, flush=True)


if __name__ == "__main__":
    main()
