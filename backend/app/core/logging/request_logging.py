"""HTTP access-log emission, used by `HTTPLoggingMiddleware`.

Event names and fields are fixed here — dashboards and alerts key on them.
"""

import structlog

logger = structlog.get_logger("app.http")


def log_request_completed(
    *,
    request_id: str | None,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> None:
    logger.info(
        "request_completed",
        request_id=request_id,
        module="http",
        operation="request",
        method=method,
        path=path,
        status=status_code,
        duration_ms=duration_ms,
    )
