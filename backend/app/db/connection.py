"""asyncpg pool lifecycle — the only place a Postgres connection is created.

No I/O happens at import or construction time: the socket opens only when
`connect()` is awaited, which `container.startup()` does iff
`settings.startup_connect_database` is true.
"""

from __future__ import annotations

import asyncpg

from app.core.config import Settings
from app.core.errors.core_errors import DatabaseConnectionError


class DatabasePool:
    """Owns the asyncpg pool. Constructing this object performs no I/O."""

    def __init__(
        self,
        *,
        dsn: str,
        min_size: int = 2,
        max_size: int = 10,
        command_timeout: float = 30.0,
    ) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._command_timeout = command_timeout
        self._pool: asyncpg.Pool | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> DatabasePool:
        if settings.postgres_database_url is None:
            raise DatabaseConnectionError(
                "POSTGRES_DATABASE_URL is not set but a database pool was requested"
            )
        return cls(
            dsn=settings.postgres_database_url.get_secret_value(),
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=settings.db_command_timeout,
        )

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    @property
    def pool(self) -> asyncpg.Pool:
        """The live pool. Raises if `connect()` has not been awaited yet."""
        if self._pool is None:
            raise DatabaseConnectionError(
                "Database pool is not connected; container.startup() must run "
                "with STARTUP_CONNECT_DATABASE=true before the pool is used"
            )
        return self._pool

    async def connect(self) -> None:
        """Open the pool. Idempotent; the only method here that performs I/O."""
        if self._pool is not None:
            return
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=self._min_size,
                max_size=self._max_size,
                command_timeout=self._command_timeout,
                # statement_cache_size=0 keeps the pool safe behind PgBouncer in
                # transaction-pooling mode, where prepared statements break.
                statement_cache_size=0,
            )
        except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
            raise DatabaseConnectionError(
                "Failed to connect the database pool",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def disconnect(self) -> None:
        """Close the pool and forget it. Safe to call when never connected."""
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None
