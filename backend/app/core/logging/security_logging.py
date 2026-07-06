"""Security event logging: auth failures, permission denials.

Emission points arrive with the auth/authorization milestones; event names are
fixed now so alerting can be built against them early.
"""

import structlog

logger = structlog.get_logger("app.security")


def log_auth_failure(*, reason: str, request_id: str | None = None) -> None:
    logger.warning(
        "auth_failure",
        module="security",
        operation="authenticate",
        reason=reason,
        request_id=request_id,
    )


def log_permission_denied(
    *,
    subject: str,
    action: str,
    resource: str,
    request_id: str | None = None,
) -> None:
    logger.warning(
        "permission_denied",
        module="security",
        operation="authorize",
        subject=subject,
        action=action,
        resource=resource,
        request_id=request_id,
    )
