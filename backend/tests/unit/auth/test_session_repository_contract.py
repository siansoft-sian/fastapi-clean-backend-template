"""One session-repository contract, two implementations (M2 pattern).

The fake runs in the fast gate; the asyncpg adapter runs against the REAL
sqitch migrations (via tests.integration.sqitch_harness) under the
integration markers. Validity semantics are identical: get/touch/rotate raise
InvalidSessionError / SessionExpiredError; revoke is idempotent.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest

from app.auth.exceptions import InvalidSessionError, SessionExpiredError
from app.auth.session_repository import (
    CreatedSessionDTO,
    FakeSessionRepository,
    SessionRepositoryProtocol,
)
from app.auth.session_tokens import generate_session_token


@dataclass
class SeededIdentity:
    user_id: str
    tenant_id: str
    email: str


@dataclass
class RepoContext:
    repo: SessionRepositoryProtocol
    seed_identity: Callable[[], Awaitable[SeededIdentity]]


def _fake_context() -> RepoContext:
    fake = FakeSessionRepository()

    async def seed() -> SeededIdentity:
        identity = SeededIdentity(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            email=f"{uuid.uuid4().hex[:8]}@example.com",
        )
        fake.set_user_email(identity.user_id, identity.email)
        return identity

    return RepoContext(repo=fake, seed_identity=seed)


@pytest.fixture(
    params=[
        pytest.param("fake"),
        pytest.param("postgres", marks=[pytest.mark.integration, pytest.mark.postgres]),
    ]
)
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[RepoContext]:
    if request.param == "fake":
        yield _fake_context()
        return

    # Integration path: the REAL migrations + adapters, no scaffold.
    import asyncpg

    from app.auth.identity_mapper import AsyncpgIdentityMapper
    from app.auth.session_repository import AsyncpgSessionRepository
    from app.auth.token_cipher import TokenCipher
    from tests.integration.sqitch_harness import POSTGRES_TEST_DSN, reset_and_deploy

    await reset_and_deploy(POSTGRES_TEST_DSN)
    pool = await asyncpg.create_pool(
        dsn=POSTGRES_TEST_DSN, min_size=1, max_size=2, statement_cache_size=0
    )
    assert pool is not None
    mapper = AsyncpgIdentityMapper(pool)
    repo = AsyncpgSessionRepository(pool, TokenCipher(TokenCipher.generate_key()))

    async def seed() -> SeededIdentity:
        email = f"{uuid.uuid4().hex[:8]}@example.com"
        identity = await mapper.map_identity(
            provider="test", subject=f"sub-{uuid.uuid4().hex}", email=email, provision=True
        )
        return SeededIdentity(user_id=identity.user_id, tenant_id=identity.tenant_id, email=email)

    try:
        yield RepoContext(repo=repo, seed_identity=seed)
    finally:
        await pool.close()


async def create_session(
    ctx: RepoContext,
    identity: SeededIdentity,
    *,
    token: str,
    absolute_ttl: int = 3600,
    idle_ttl: int = 600,
) -> CreatedSessionDTO:
    return await ctx.repo.create(
        session_token=token,
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        access_token="gotrue-access-secret",
        refresh_token="gotrue-refresh-secret",
        gotrue_expires_at=None,
        absolute_ttl_seconds=absolute_ttl,
        idle_ttl_seconds=idle_ttl,
        user_agent="pytest",
        ip="127.0.0.1",
    )


async def test_create_then_get_round_trips(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    token = generate_session_token()
    created = await create_session(ctx, identity, token=token)
    assert created.session_internal_id
    assert created.idle_expires_at <= created.absolute_expires_at

    session = await ctx.repo.get(session_token=token)
    assert session.session_internal_id == created.session_internal_id
    assert session.user_id == identity.user_id
    assert session.tenant_id == identity.tenant_id
    assert session.email == identity.email
    assert session.gotrue_access_token.get_secret_value() == "gotrue-access-secret"
    assert session.gotrue_refresh_token.get_secret_value() == "gotrue-refresh-secret"


async def test_get_unknown_token_raises_invalid(ctx: RepoContext) -> None:
    with pytest.raises(InvalidSessionError):
        await ctx.repo.get(session_token=generate_session_token())


async def test_get_revoked_raises_invalid(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    token = generate_session_token()
    await create_session(ctx, identity, token=token)
    await ctx.repo.revoke(session_token=token)
    with pytest.raises(InvalidSessionError):
        await ctx.repo.get(session_token=token)


async def test_get_expired_raises_expired(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    token = generate_session_token()
    await create_session(ctx, identity, token=token, absolute_ttl=0, idle_ttl=0)
    with pytest.raises(SessionExpiredError):
        await ctx.repo.get(session_token=token)


async def test_touch_slides_idle_expiry(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    token = generate_session_token()
    created = await create_session(ctx, identity, token=token, idle_ttl=60)
    new_idle = await ctx.repo.touch(session_token=token, idle_ttl_seconds=600)
    assert new_idle > created.idle_expires_at


async def test_touch_never_exceeds_absolute(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    token = generate_session_token()
    created = await create_session(ctx, identity, token=token, absolute_ttl=30, idle_ttl=10)
    new_idle = await ctx.repo.touch(session_token=token, idle_ttl_seconds=99999)
    assert new_idle == created.absolute_expires_at


async def test_touch_missing_or_revoked_raises(ctx: RepoContext) -> None:
    with pytest.raises(InvalidSessionError):
        await ctx.repo.touch(session_token=generate_session_token(), idle_ttl_seconds=60)
    identity = await ctx.seed_identity()
    token = generate_session_token()
    await create_session(ctx, identity, token=token)
    await ctx.repo.revoke(session_token=token)
    with pytest.raises(InvalidSessionError):
        await ctx.repo.touch(session_token=token, idle_ttl_seconds=60)


async def test_rotate_revokes_old_and_carries_absolute(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    old_token, new_token = generate_session_token(), generate_session_token()
    created = await create_session(ctx, identity, token=old_token)

    rotated = await ctx.repo.rotate(
        old_session_token=old_token,
        new_session_token=new_token,
        access_token="new-access",
        refresh_token="new-refresh",
        gotrue_expires_at=None,
        idle_ttl_seconds=600,
    )
    assert rotated.session_internal_id != created.session_internal_id
    assert rotated.absolute_expires_at == created.absolute_expires_at  # never extended

    with pytest.raises(InvalidSessionError):
        await ctx.repo.get(session_token=old_token)
    fresh = await ctx.repo.get(session_token=new_token)
    assert fresh.user_id == identity.user_id
    assert fresh.gotrue_access_token.get_secret_value() == "new-access"


async def test_rotate_on_revoked_raises(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    token = generate_session_token()
    await create_session(ctx, identity, token=token)
    await ctx.repo.revoke(session_token=token)
    with pytest.raises(InvalidSessionError):
        await ctx.repo.rotate(
            old_session_token=token,
            new_session_token=generate_session_token(),
            access_token="a",
            refresh_token="r",
            gotrue_expires_at=None,
            idle_ttl_seconds=60,
        )


async def test_revoke_is_idempotent(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    token = generate_session_token()
    await create_session(ctx, identity, token=token)
    await ctx.repo.revoke(session_token=token)
    await ctx.repo.revoke(session_token=token)  # second call must not raise
    await ctx.repo.revoke(session_token=generate_session_token())  # missing: still ok


async def test_revoke_all_counts_only_active_sessions(ctx: RepoContext) -> None:
    identity = await ctx.seed_identity()
    token_a, token_b = generate_session_token(), generate_session_token()
    await create_session(ctx, identity, token=token_a)
    await create_session(ctx, identity, token=token_b)

    revoked = await ctx.repo.revoke_all(user_id=identity.user_id, tenant_id=identity.tenant_id)
    assert revoked == 2
    for token in (token_a, token_b):
        with pytest.raises(InvalidSessionError):
            await ctx.repo.get(session_token=token)
    # Nothing left to revoke: count drops to zero.
    assert await ctx.repo.revoke_all(user_id=identity.user_id, tenant_id=identity.tenant_id) == 0
