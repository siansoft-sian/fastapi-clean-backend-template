"""Transaction management: the port consumed by middleware/deps, and the
asyncpg implementation.

Consumers (middleware, boundary deps, repositories' callers) depend on
`TransactionManagerProtocol` and treat the yielded connection as opaque — only
infrastructure adapters know it is an `asyncpg.Connection`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol

import asyncpg

from app.db.connection import DatabasePool


class TransactionManagerProtocol(Protocol):
    """Port for request-scoped database access."""

    def transaction(self) -> AbstractAsyncContextManager[Any]:
        """Yield a connection with an open transaction: commit on clean exit,
        rollback if the block raises."""
        ...

    def connection(self) -> AbstractAsyncContextManager[Any]:
        """Yield a plain pooled connection (reads; no explicit transaction)."""
        ...


class AsyncpgTransactionManager:
    """asyncpg implementation of the transaction port."""

    def __init__(self, database: DatabasePool) -> None:
        self._database = database

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        async with self._database.pool.acquire() as connection:
            # Explicit start/commit/rollback (rather than `async with
            # connection.transaction()`) keeps the outcome observable and testable.
            txn = connection.transaction()
            await txn.start()
            try:
                yield connection
            except BaseException:
                await txn.rollback()
                raise
            else:
                await txn.commit()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        async with self._database.pool.acquire() as connection:
            yield connection


# mypy-only structural proof that the implementation satisfies the port.
def _static_protocol_check(manager: AsyncpgTransactionManager) -> TransactionManagerProtocol:
    return manager
