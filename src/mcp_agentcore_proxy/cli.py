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
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_CONTENT_TYPE = "application/json"
DEFAULT_ACCEPT = "application/json, text/event-stream"


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

    sts = boto3.client("sts")
    try:
        ident = sts.get_caller_identity()
    except (BotoCoreError, ClientError):
        print(
            _error_response(None, -32000, "Unable to call sts:GetCallerIdentity"),
            flush=True,
        )
        sys.exit(2)

    uid = f"{ident.get('Account', '')}/{ident.get('UserId', '')}/{ident.get('Arn', '')}"
    runtime_session_id = hashlib.sha256(uid.encode("utf-8")).hexdigest()

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

        mcp_session_id = "mcp-" + uuid.uuid4().hex

        try:
            response = client.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                payload=line.encode("utf-8"),
                runtimeSessionId=runtime_session_id,
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
