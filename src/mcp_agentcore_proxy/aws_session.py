"""AWS session management with optional role assumption."""

import os

import boto3
from aws_assume_role_lib import assume_role as assume_role_with_refresh
from botocore.exceptions import BotoCoreError, ClientError, UnauthorizedSSOTokenError


class AssumeRoleError(Exception):
    """Raised when the proxy cannot assume the requested role."""


def format_sso_login_message() -> str:
    """Return a user-facing message indicating SSO re-authentication is required."""
    profile = (os.getenv("AWS_PROFILE") or "").strip()
    if profile:
        return (
            "AWS SSO session is expired or invalid. Run "
            f"`aws sso login --profile {profile}` to refresh it, then retry."
        )
    return "AWS SSO session is expired or invalid. Run `aws sso login` to refresh it, then retry."


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

    base_session = boto3.session.Session()
    if not assume_role_arn:
        return base_session

    session_name_env = (os.getenv("AGENTCORE_ASSUME_ROLE_SESSION_NAME") or "").strip()
    session_name = session_name_env or "mcpAgentCoreProxy"
    try:
        return assume_role_with_refresh(
            base_session,
            assume_role_arn,
            RoleSessionName=session_name,
        )
    except UnauthorizedSSOTokenError as exc:
        raise AssumeRoleError(format_sso_login_message()) from exc
    except (BotoCoreError, ClientError, ValueError) as exc:
        raise AssumeRoleError(
            f"Unable to assume role {assume_role_arn}: {exc}"
        ) from exc
    except Exception as exc:  # pragma: no cover
        raise AssumeRoleError(
            f"Unexpected error assuming role {assume_role_arn}: {exc}"
        ) from exc
