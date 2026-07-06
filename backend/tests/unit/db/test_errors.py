"""map_asyncpg_error: each driver failure lands on the right AppError subclass."""

import asyncpg
import pytest

from app.core.errors.core_errors import (
    ConflictError,
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseResultError,
    NotFoundError,
)
from app.db.errors import map_asyncpg_error


@pytest.mark.parametrize(
    ("exc", "expected_type", "expected_status"),
    [
        (asyncpg.UniqueViolationError("duplicate key"), ConflictError, 409),
        (asyncpg.PostgresConnectionError("connection lost"), DatabaseConnectionError, 500),
        (asyncpg.InterfaceError("connection released"), DatabaseConnectionError, 500),
        (ConnectionRefusedError("refused"), DatabaseConnectionError, 500),
        (TimeoutError("timed out"), DatabaseConnectionError, 500),
        (asyncpg.ForeignKeyViolationError("fk"), DatabaseOperationError, 500),
        (asyncpg.PostgresSyntaxError("bad sql"), DatabaseOperationError, 500),
        (ValueError("unexpected row shape"), DatabaseResultError, 500),
    ],
)
def test_mapping(exc: Exception, expected_type: type, expected_status: int) -> None:
    mapped = map_asyncpg_error(exc)
    assert type(mapped) is expected_type
    assert mapped.http_status == expected_status


def test_already_mapped_app_error_passes_through() -> None:
    original = NotFoundError("nothing here")
    assert map_asyncpg_error(original) is original


def test_mapped_error_carries_safe_details_only() -> None:
    mapped = map_asyncpg_error(asyncpg.PostgresSyntaxError("syntax error at or near SELECT"))
    # The client-visible details identify the failure class, not internals/SQL.
    assert mapped.details["error_type"] == "PostgresSyntaxError"
    assert "SELECT" not in str(mapped.details)
