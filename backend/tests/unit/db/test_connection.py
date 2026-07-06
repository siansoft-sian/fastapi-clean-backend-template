"""DatabasePool: strictly lazy — no socket until connect() is awaited."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.core.errors.core_errors import DatabaseConnectionError
from app.db.connection import DatabasePool

DSN = "postgresql://user:pass@db.example:5432/appdb"


def make_pool() -> DatabasePool:
    return DatabasePool(dsn=DSN, min_size=1, max_size=3, command_timeout=5.0)


async def test_construction_does_not_create_pool() -> None:
    with patch("app.db.connection.asyncpg.create_pool", new=AsyncMock()) as create_pool:
        database = make_pool()
        assert database.is_connected is False
        create_pool.assert_not_called()


async def test_connect_creates_pool_with_configured_sizes() -> None:
    with patch("app.db.connection.asyncpg.create_pool", new=AsyncMock()) as create_pool:
        database = make_pool()
        await database.connect()
        create_pool.assert_awaited_once()
        kwargs = create_pool.await_args.kwargs
        assert kwargs["dsn"] == DSN
        assert kwargs["min_size"] == 1
        assert kwargs["max_size"] == 3
        assert kwargs["command_timeout"] == 5.0
        # PgBouncer (transaction pooling) safety: prepared statements disabled.
        assert kwargs["statement_cache_size"] == 0
        assert database.is_connected is True


async def test_connect_is_idempotent() -> None:
    with patch("app.db.connection.asyncpg.create_pool", new=AsyncMock()) as create_pool:
        database = make_pool()
        await database.connect()
        await database.connect()
        assert create_pool.await_count == 1


async def test_pool_property_raises_before_connect() -> None:
    database = make_pool()
    with pytest.raises(DatabaseConnectionError):
        _ = database.pool


async def test_disconnect_closes_and_forgets_pool() -> None:
    fake_pool = AsyncMock()
    with patch("app.db.connection.asyncpg.create_pool", new=AsyncMock(return_value=fake_pool)):
        database = make_pool()
        await database.connect()
        await database.disconnect()
    fake_pool.close.assert_awaited_once()
    assert database.is_connected is False


async def test_disconnect_without_connect_is_safe() -> None:
    database = make_pool()
    await database.disconnect()
    assert database.is_connected is False


def test_from_settings_requires_url() -> None:
    settings = Settings(postgres_database_url=None)
    with pytest.raises(DatabaseConnectionError):
        DatabasePool.from_settings(settings)
