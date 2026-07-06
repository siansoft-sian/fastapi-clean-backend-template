"""One session-repository contract, two implementations (M2 pattern).

The fake runs in the fast gate; the asyncpg adapter (against the scaffold
implementing the documented DB contract) runs under the integration markers.
"""

import uuid
from collections.abc import AsyncIterator

import pytest

from app.auth.session_repository import (
    FakeSessionRepository,
    SessionDTO,
    SessionRepositoryProtocol,
)


def unique_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture(
    params=[
        pytest.param("fake"),
        pytest.param("postgres", marks=[pytest.mark.integration, pytest.mark.postgres]),
    ]
)
async def repo(request: pytest.FixtureRequest) -> AsyncIterator[SessionRepositoryProtocol]:
    if request.param == "fake":
        yield FakeSessionRepository()
        return

    import asyncpg

    from app.auth.session_repository import AsyncpgSessionRepository
    from tests.integration.session_scaffold import POSTGRES_TEST_DSN, apply_session_scaffold

    await apply_session_scaffold(POSTGRES_TEST_DSN)
    pool = await asyncpg.create_pool(
        dsn=POSTGRES_TEST_DSN, min_size=1, max_size=2, statement_cache_size=0
    )
    assert pool is not None
    try:
        yield AsyncpgSessionRepository(pool)
    finally:
        await pool.close()


async def create_session(
    repo: SessionRepositoryProtocol,
    *,
    absolute_ttl: int = 3600,
    idle_ttl: int = 600,
) -> SessionDTO:
    return await repo.create(
        user_id=unique_id(),
        tenant_id=unique_id(),
        access_token="gotrue-access-secret",
        refresh_token="gotrue-refresh-secret",
        absolute_ttl_seconds=absolute_ttl,
        idle_ttl_seconds=idle_ttl,
        email="user@example.com",
        user_agent="pytest",
        ip="127.0.0.1",
    )


async def test_create_then_get_round_trips(repo: SessionRepositoryProtocol) -> None:
    created = await create_session(repo)
    assert created.id and created.revoked_at is None
    assert created.idle_expires_at <= created.absolute_expires_at

    fetched = await repo.get(session_id=created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.user_id == created.user_id
    assert fetched.tenant_id == created.tenant_id
    assert fetched.email == "user@example.com"
    assert fetched.gotrue_access_token.get_secret_value() == "gotrue-access-secret"
    assert fetched.gotrue_refresh_token.get_secret_value() == "gotrue-refresh-secret"


async def test_get_unknown_or_garbage_id_returns_none(repo: SessionRepositoryProtocol) -> None:
    assert await repo.get(session_id=unique_id()) is None
    assert await repo.get(session_id="not-a-uuid") is None
    assert await repo.get(session_id="") is None


async def test_touch_slides_idle_expiry(repo: SessionRepositoryProtocol) -> None:
    created = await create_session(repo, absolute_ttl=3600, idle_ttl=60)
    touched = await repo.touch(session_id=created.id, idle_ttl_seconds=600)
    assert touched is not None
    assert touched.idle_expires_at > created.idle_expires_at


async def test_touch_never_exceeds_absolute_expiry(repo: SessionRepositoryProtocol) -> None:
    created = await create_session(repo, absolute_ttl=30, idle_ttl=10)
    touched = await repo.touch(session_id=created.id, idle_ttl_seconds=99999)
    assert touched is not None
    assert touched.idle_expires_at == created.absolute_expires_at


async def test_touch_missing_or_revoked_returns_none(repo: SessionRepositoryProtocol) -> None:
    assert await repo.touch(session_id=unique_id(), idle_ttl_seconds=60) is None
    created = await create_session(repo)
    await repo.revoke(session_id=created.id)
    assert await repo.touch(session_id=created.id, idle_ttl_seconds=60) is None


async def test_rotate_issues_new_id_and_revokes_old(repo: SessionRepositoryProtocol) -> None:
    created = await create_session(repo)
    rotated = await repo.rotate(
        session_id=created.id,
        access_token="new-access",
        refresh_token="new-refresh",
        idle_ttl_seconds=600,
    )
    assert rotated is not None
    assert rotated.id != created.id
    assert rotated.user_id == created.user_id
    assert rotated.tenant_id == created.tenant_id
    assert rotated.gotrue_access_token.get_secret_value() == "new-access"
    assert rotated.absolute_expires_at == created.absolute_expires_at  # never extended

    old = await repo.get(session_id=created.id)
    assert old is not None and old.revoked_at is not None
    fresh = await repo.get(session_id=rotated.id)
    assert fresh is not None and fresh.revoked_at is None


async def test_rotate_missing_or_revoked_returns_none(repo: SessionRepositoryProtocol) -> None:
    assert (
        await repo.rotate(
            session_id=unique_id(), access_token="a", refresh_token="r", idle_ttl_seconds=60
        )
        is None
    )
    created = await create_session(repo)
    await repo.revoke(session_id=created.id)
    assert (
        await repo.rotate(
            session_id=created.id, access_token="a", refresh_token="r", idle_ttl_seconds=60
        )
        is None
    )


async def test_revoke_is_idempotent(repo: SessionRepositoryProtocol) -> None:
    created = await create_session(repo)
    await repo.revoke(session_id=created.id)
    await repo.revoke(session_id=created.id)  # second call must not raise
    fetched = await repo.get(session_id=created.id)
    assert fetched is not None and fetched.revoked_at is not None
