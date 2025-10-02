"""AWS session management with optional role assumption."""

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class AssumeRoleError(Exception):
    """Raised when the proxy cannot assume the requested role."""


def resolve_aws_session() -> boto3.session.Session:
    """
    Resolve an AWS session, optionally assuming a role.

    If AGENTCORE_ASSUME_ROLE_ARN is set, assumes that role and returns
    a session with the temporary credentials. Otherwise, returns a session
    using the default credential chain.

    Returns:
        A boto3 Session object with appropriate credentials.

    Raises:
        AssumeRoleError: If role assumption is configured but fails.
    """
    assume_role_arn = (os.getenv("AGENTCORE_ASSUME_ROLE_ARN") or "").strip()
    if not assume_role_arn:
        return boto3.session.Session()

    session_name_env = (os.getenv("AGENTCORE_ASSUME_ROLE_SESSION_NAME") or "").strip()
    session_name = session_name_env or "mcpAgentCoreProxy"

    sts = boto3.client("sts")
    try:
        response = sts.assume_role(
            RoleArn=assume_role_arn, RoleSessionName=session_name
        )
    except (BotoCoreError, ClientError) as exc:
        raise AssumeRoleError(
            f"Unable to assume role {assume_role_arn}: {exc}"
        ) from exc

    credentials = response.get("Credentials")
    if not credentials:
        raise AssumeRoleError("AssumeRole response missing credentials")

    return boto3.session.Session(
        aws_access_key_id=credentials.get("AccessKeyId"),
        aws_secret_access_key=credentials.get("SecretAccessKey"),
        aws_session_token=credentials.get("SessionToken"),
    )
