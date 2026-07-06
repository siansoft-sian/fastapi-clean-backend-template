"""Central exception boundary: every error leaves the app as the standard envelope.

Registered once in `create_app()`. Services and domain code raise `AppError`
subclasses; nothing below the boundary builds HTTP responses.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.enums import ErrorCategory
from app.core.errors import error_codes
from app.core.errors.core_errors import AppError, RateLimitExceededError
from app.core.responses import api_error


def rate_limit_headers(exc: RateLimitExceededError) -> dict[str, str]:
    """Retry-After + X-RateLimit-* from the error's payload (delta-seconds).

    Shared by the 429 exception handler and the rate-limit middleware (which
    runs outside the handler stack and must build its response inline).
    """
    headers = {
        "Retry-After": str(exc.retry_after),
        "X-RateLimit-Remaining": str(exc.remaining),
        "X-RateLimit-Reset": str(exc.retry_after),
    }
    if exc.limit is not None:
        headers["X-RateLimit-Limit"] = str(exc.limit)
    return headers


logger = structlog.get_logger(__name__)


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    category: ErrorCategory,
    details: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    meta: dict[str, Any] = {
        "path": request.url.path,
        "method": request.method,
        "category": category.value,
    }
    # The catch-all handler runs outside the middleware stack; recover the id
    # from request.state in case the contextvar is not visible there.
    state_request_id = getattr(request.state, "request_id", None)
    if state_request_id is not None:
        meta["request_id"] = state_request_id
    body = api_error(code=code, message=message, details=details, meta=meta)
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the exception boundary. Starlette dispatches by most-specific type."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        log = logger.error if exc.http_status >= 500 else logger.warning
        log(
            "app_error",
            error_code=exc.code,
            status=exc.http_status,
            path=request.url.path,
            method=request.method,
            exc_info=exc if exc.http_status >= 500 else None,
        )
        return _error_response(
            request,
            status_code=exc.http_status,
            code=exc.code,
            message=exc.message,
            category=exc.category,
            details=exc.details,
        )

    @app.exception_handler(RateLimitExceededError)
    async def handle_rate_limit_error(
        request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        logger.warning(
            "rate_limited",
            error_code=exc.code,
            path=request.url.path,
            method=request.method,
        )
        return _error_response(
            request,
            status_code=exc.http_status,
            code=exc.code,
            message=exc.message,
            category=exc.category,
            details=exc.details,
            headers=rate_limit_headers(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code=error_codes.VALIDATION_ERROR,
            message="Request validation failed",
            category=ErrorCategory.VALIDATION,
            details={"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=error_codes.HTTP_ERROR,
            message=str(exc.detail),
            category=ErrorCategory.HTTP,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Full traceback to the logs; a generic body to the client — never a stack trace.
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exc_info=exc,
        )
        return _error_response(
            request,
            status_code=500,
            code=error_codes.INTERNAL_ERROR,
            message="Internal server error",
            category=ErrorCategory.INTERNAL,
        )
