# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "boto3",
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
from botocore.exceptions import BotoCoreError, ClientError

from mcp_agentcore_proxy.aws_session import AssumeRoleError, resolve_aws_session
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
        print("Error: Set AGENTCORE_AGENT_ARN (or AGENT_ARN)", file=sys.stderr, flush=True)
        sys.exit(2)

    config = _resolve_runtime_session_config()

    try:
        session_manager = RuntimeSessionManager(config)
    except RuntimeSessionError as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)

    try:
        session = resolve_aws_session()
    except AssumeRoleError as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)

    client_config = Config(
        read_timeout=int(os.getenv("AGENTCORE_READ_TIMEOUT", "300")),
        connect_timeout=int(os.getenv("AGENTCORE_CONNECT_TIMEOUT", "10")),
        retries={"max_attempts": 2},
    )
    client = session.client("bedrock-agentcore", config=client_config)

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

        try:
            next_runtime_session_id = session_manager.next_session_id()
            response = client.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                payload=line.encode("utf-8"),
                runtimeSessionId=next_runtime_session_id,
                mcpSessionId=f"mcp-{next_runtime_session_id}",
                contentType=DEFAULT_CONTENT_TYPE,
                accept=DEFAULT_ACCEPT,
            )
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

        body_stream = response.get("response")
        if body_stream is None:
            _print_error(
                request_id, -32001, "Missing response body from InvokeAgentRuntime"
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
            _print_error(request_id, -32002, f"Failed to process response body: {exc}")


if __name__ == "__main__":
    main()
