"""Application error family. Framework-free: raised from any layer, translated
to HTTP exactly once in the exception boundary.

Never raise `HTTPException` from services or domain code — raise these.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import ErrorCategory
from app.core.errors import error_codes


class AppError(Exception):
    """Base error carrying a stable code, HTTP status, category, and safe details.

    `details` must never contain secrets; the boundary redacts credential-like
    keys as a second line of defense, not as permission.
    """

    code: str = error_codes.INTERNAL_ERROR
    http_status: int = 500
    category: ErrorCategory = ErrorCategory.INTERNAL
    default_message: str = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details: dict[str, Any] = details or {}
        super().__init__(self.message)


class UnauthorizedError(AppError):
    code = error_codes.UNAUTHORIZED
    http_status = 401
    category = ErrorCategory.AUTH
    default_message = "Authentication required"


class ForbiddenError(AppError):
    code = error_codes.FORBIDDEN
    http_status = 403
    category = ErrorCategory.AUTH
    default_message = "Not allowed"


class NotFoundError(AppError):
    code = error_codes.NOT_FOUND
    http_status = 404
    category = ErrorCategory.NOT_FOUND
    default_message = "Resource not found"


class ConflictError(AppError):
    code = error_codes.CONFLICT
    http_status = 409
    category = ErrorCategory.CONFLICT
    default_message = "Conflict with current state"


class RateLimitExceededError(AppError):
    code = error_codes.RATE_LIMIT_EXCEEDED
    http_status = 429
    category = ErrorCategory.RATE_LIMIT
    default_message = "Rate limit exceeded"


class DatabaseError(AppError):
    code = error_codes.DATABASE_ERROR
    http_status = 500
    category = ErrorCategory.DATABASE
    default_message = "Database error"


class DatabaseConnectionError(DatabaseError):
    code = error_codes.DATABASE_CONNECTION_ERROR
    default_message = "Database connection failed"


class DatabaseOperationError(DatabaseError):
    code = error_codes.DATABASE_OPERATION_ERROR
    default_message = "Database operation failed"


class DatabaseResultError(DatabaseError):
    code = error_codes.DATABASE_RESULT_ERROR
    default_message = "Database returned an unexpected result"


class ExternalServiceError(AppError):
    code = error_codes.EXTERNAL_SERVICE_ERROR
    http_status = 502
    category = ErrorCategory.EXTERNAL
    default_message = "Upstream service failed"
