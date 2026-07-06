"""AsyncpgTransactionManager: commit on clean exit, rollback when the block raises."""

from contextlib import asynccontextmanager
from typing import Any, cast

import pytest

from app.db.connection import DatabasePool
from app.db.transaction_manager import AsyncpgTransactionManager


class FakeTransaction:
    def __init__(self) -> None:
        self.started = False
        self.committed = False
        self.rolled_back = False

    async def start(self) -> None:
        self.started = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeConnection:
    def __init__(self) -> None:
        self.txn = FakeTransaction()

    def transaction(self) -> FakeTransaction:
        return self.txn


class FakePoolOwner:
    """Stands in for DatabasePool: exposes `.pool` with an acquire() context."""

    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.acquired = 0
        self.released = 0
        owner = self

        class _Pool:
            @asynccontextmanager
            async def acquire(self) -> Any:
                owner.acquired += 1
                try:
                    yield owner.connection
                finally:
                    owner.released += 1

        self.pool = _Pool()


def make_manager(owner: FakePoolOwner) -> AsyncpgTransactionManager:
    return AsyncpgTransactionManager(cast(DatabasePool, owner))


async def test_transaction_commits_on_clean_exit() -> None:
    owner = FakePoolOwner()
    manager = make_manager(owner)
    async with manager.transaction() as connection:
        assert connection is owner.connection
        assert owner.connection.txn.started is True
    assert owner.connection.txn.committed is True
    assert owner.connection.txn.rolled_back is False
    assert owner.acquired == owner.released == 1


async def test_transaction_rolls_back_when_block_raises() -> None:
    owner = FakePoolOwner()
    manager = make_manager(owner)
    with pytest.raises(RuntimeError, match="boom"):
        async with manager.transaction():
            raise RuntimeError("boom")
    assert owner.connection.txn.rolled_back is True
    assert owner.connection.txn.committed is False
    assert owner.acquired == owner.released == 1


async def test_plain_connection_has_no_transaction() -> None:
    owner = FakePoolOwner()
    manager = make_manager(owner)
    async with manager.connection() as connection:
        assert connection is owner.connection
    assert owner.connection.txn.started is False
    assert owner.acquired == owner.released == 1
