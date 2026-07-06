"""asyncpg exception → AppError mapping.

Repositories call `map_asyncpg_error` in their `except` blocks and raise the
result — raw driver exceptions must never cross a repository boundary:

    try:
        record = await pool.fetchrow(...)
    except asyncpg.PostgresError as exc:
        raise map_asyncpg_error(exc) from exc
"""

from __future__ import annotations

import asyncpg

from app.core.errors.core_errors import (
    AppError,
    ConflictError,
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseResultError,
)


def map_asyncpg_error(exc: Exception) -> AppError:
    """Translate a driver/OS-level failure into the AppError taxonomy.

    Order matters: most specific classes first (UniqueViolation and
    PostgresConnectionError are both subclasses of PostgresError).
    """
    if isinstance(exc, AppError):
        return exc  # already translated upstream; pass through unchanged

    if isinstance(exc, asyncpg.UniqueViolationError):
        return ConflictError(
            "Resource already exists",
            details={"constraint": getattr(exc, "constraint_name", None)},
        )

    if isinstance(exc, asyncpg.PostgresConnectionError | asyncpg.InterfaceError):
        return DatabaseConnectionError(details={"error_type": type(exc).__name__})

    if isinstance(exc, OSError | TimeoutError):
        return DatabaseConnectionError(details={"error_type": type(exc).__name__})

    if isinstance(exc, asyncpg.PostgresError):
        return DatabaseOperationError(
            details={"error_type": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)},
        )

    # Anything else (e.g. a surprise while parsing a result row) is a result error.
    return DatabaseResultError(details={"error_type": type(exc).__name__})
