"""Postgres-only guarantees of the sessions/identity DB contract.

Runs against the REAL sqitch migrations (sqitch_harness). Covers what the
shared contract suite cannot: constraints, encryption at rest, the rotation
race, tenant isolation of revoke_all, retention, map_identity semantics, and
the full deploy -> verify -> revert -> redeploy migration cycle.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg
import pytest

from app.auth.exceptions import IdentityMappingError, InvalidSessionError
from app.auth.identity_mapper import AsyncpgIdentityMapper
from app.auth.session_repository import AsyncpgSessionRepository
from app.auth.session_tokens import generate_session_token, hash_session_token
from app.auth.token_cipher import TokenCipher
from tests.integration.sqitch_harness import (
    POSTGRES_TEST_DSN,
    deploy_all,
    plan_changes,
    reset_and_deploy,
    revert_all,
    verify_all,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@dataclass
class DbContext:
    pool: asyncpg.Pool
    repo: AsyncpgSessionRepository
    mapper: AsyncpgIdentityMapper
    cipher: TokenCipher


@pytest.fixture
async def db() -> AsyncIterator[DbContext]:
    await reset_and_deploy(POSTGRES_TEST_DSN)
    pool = await asyncpg.create_pool(
        dsn=POSTGRES_TEST_DSN, min_size=2, max_size=4, statement_cache_size=0
    )
    assert pool is not None
    cipher = TokenCipher(TokenCipher.generate_key())
    try:
        yield DbContext(
            pool=pool,
            repo=AsyncpgSessionRepository(pool, cipher),
            mapper=AsyncpgIdentityMapper(pool),
            cipher=cipher,
        )
    finally:
        await pool.close()


async def seed_identity(db: DbContext) -> tuple[str, str]:
    identity = await db.mapper.map_identity(
        provider="test",
        subject=f"sub-{uuid.uuid4().hex}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        provision=True,
    )
    return identity.user_id, identity.tenant_id


async def create_session(db: DbContext, user_id: str, tenant_id: str, token: str) -> None:
    await db.repo.create(
        session_token=token,
        user_id=user_id,
        tenant_id=tenant_id,
        access_token="access-plain",
        refresh_token="refresh-plain",
        gotrue_expires_at=None,
        absolute_ttl_seconds=3600,
        idle_ttl_seconds=600,
    )


# --- constraints -------------------------------------------------------------


async def test_duplicate_token_hash_rejected(db: DbContext) -> None:
    user_id, tenant_id = await seed_identity(db)
    token = generate_session_token()
    await create_session(db, user_id, tenant_id, token)
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.pool.execute(
            """
            INSERT INTO app.user_sessions
                (token_hash, user_id, tenant_id, gotrue_access_token, gotrue_refresh_token,
                 absolute_expires_at, idle_expires_at)
            VALUES ($1, $2, $3, 'x', 'y', now() + interval '1h', now() + interval '10m')
            """,
            hash_session_token(token),
            uuid.UUID(user_id),
            uuid.UUID(tenant_id),
        )


async def test_idle_beyond_absolute_rejected(db: DbContext) -> None:
    user_id, tenant_id = await seed_identity(db)
    with pytest.raises(asyncpg.CheckViolationError):
        await db.pool.execute(
            """
            INSERT INTO app.user_sessions
                (token_hash, user_id, tenant_id, gotrue_access_token, gotrue_refresh_token,
                 absolute_expires_at, idle_expires_at)
            VALUES ($1, $2, $3, 'x', 'y', now() + interval '1h', now() + interval '2h')
            """,
            hash_session_token(generate_session_token()),
            uuid.UUID(user_id),
            uuid.UUID(tenant_id),
        )


async def test_non_sha256_token_hash_rejected(db: DbContext) -> None:
    user_id, tenant_id = await seed_identity(db)
    with pytest.raises(asyncpg.CheckViolationError):
        await db.pool.execute(
            """
            INSERT INTO app.user_sessions
                (token_hash, user_id, tenant_id, gotrue_access_token, gotrue_refresh_token,
                 absolute_expires_at, idle_expires_at)
            VALUES ($1, $2, $3, 'x', 'y', now() + interval '1h', now() + interval '10m')
            """,
            b"short-hash",
            uuid.UUID(user_id),
            uuid.UUID(tenant_id),
        )


# --- encryption at rest (Decision A) -----------------------------------------


async def test_tokens_are_ciphertext_at_rest_and_hash_only_lookup(db: DbContext) -> None:
    user_id, tenant_id = await seed_identity(db)
    token = generate_session_token()
    await create_session(db, user_id, tenant_id, token)

    row = await db.pool.fetchrow(
        "SELECT token_hash, gotrue_access_token, gotrue_refresh_token "
        "FROM app.user_sessions WHERE token_hash = $1",
        hash_session_token(token),
    )
    assert row is not None
    # Raw cookie token never reaches the DB — only its 32-byte hash.
    assert bytes(row["token_hash"]) == hash_session_token(token)
    assert token.encode() not in bytes(row["token_hash"])
    # GoTrue tokens are Fernet ciphertext, opaque to the DB.
    assert b"access-plain" not in bytes(row["gotrue_access_token"])
    assert b"refresh-plain" not in bytes(row["gotrue_refresh_token"])
    # ...and the adapter round-trips the plaintext.
    session = await db.repo.get(session_token=token)
    assert session.gotrue_access_token.get_secret_value() == "access-plain"


# --- rotation race (concurrency) ---------------------------------------------


async def test_concurrent_rotations_exactly_one_wins(db: DbContext) -> None:
    user_id, tenant_id = await seed_identity(db)
    token = generate_session_token()
    await create_session(db, user_id, tenant_id, token)

    async def rotate() -> object:
        return await db.repo.rotate(
            old_session_token=token,
            new_session_token=generate_session_token(),
            access_token="a",
            refresh_token="r",
            gotrue_expires_at=None,
            idle_ttl_seconds=600,
        )

    results = await asyncio.gather(rotate(), rotate(), return_exceptions=True)
    winners = [r for r in results if not isinstance(r, BaseException)]
    losers = [r for r in results if isinstance(r, BaseException)]
    assert len(winners) == 1, f"expected exactly one winner, got {results}"
    assert len(losers) == 1 and isinstance(losers[0], InvalidSessionError)
    # The old session is revoked exactly once; only one new live session exists.
    live = await db.pool.fetchval(
        "SELECT count(*) FROM app.user_sessions WHERE user_id = $1 AND revoked_at IS NULL",
        uuid.UUID(user_id),
    )
    assert live == 1


# --- tenant isolation ---------------------------------------------------------


async def test_revoke_all_is_tenant_scoped(db: DbContext) -> None:
    user_id, tenant_a = await seed_identity(db)
    # Same user, second tenant + membership (seeded directly: test setup).
    tenant_b = str(uuid.uuid4())
    await db.pool.execute(
        "INSERT INTO app.tenants (id, name) VALUES ($1, 'tenant-b')", uuid.UUID(tenant_b)
    )
    await db.pool.execute(
        "INSERT INTO app.memberships (user_id, tenant_id) VALUES ($1, $2)",
        uuid.UUID(user_id),
        uuid.UUID(tenant_b),
    )
    token_a, token_b = generate_session_token(), generate_session_token()
    await create_session(db, user_id, tenant_a, token_a)
    await create_session(db, user_id, tenant_b, token_b)

    revoked = await db.repo.revoke_all(user_id=user_id, tenant_id=tenant_a)
    assert revoked == 1
    with pytest.raises(InvalidSessionError):
        await db.repo.get(session_token=token_a)
    # The other tenant's session is untouched.
    assert (await db.repo.get(session_token=token_b)).tenant_id == tenant_b


# --- retention -----------------------------------------------------------------


async def test_delete_expired_sessions_purges_only_past_window(db: DbContext) -> None:
    user_id, tenant_id = await seed_identity(db)
    live_token = generate_session_token()
    await create_session(db, user_id, tenant_id, live_token)
    # An expired session: hard expiry in the past (seeded directly).
    await db.pool.execute(
        """
        INSERT INTO app.user_sessions
            (token_hash, user_id, tenant_id, gotrue_access_token, gotrue_refresh_token,
             absolute_expires_at, idle_expires_at)
        VALUES ($1, $2, $3, 'x', 'y', now() - interval '2 days', now() - interval '2 days')
        """,
        hash_session_token(generate_session_token()),
        uuid.UUID(user_id),
        uuid.UUID(tenant_id),
    )

    envelope = json.loads(
        await db.pool.fetchval("SELECT app.delete_expired_sessions(interval '1 day')")
    )
    assert envelope["success"] is True
    assert envelope["data"]["deleted_count"] == 1
    # The live session survived the purge.
    assert (await db.repo.get(session_token=live_token)).user_id == user_id


# --- map_identity ---------------------------------------------------------------


async def test_map_identity_provision_flag_and_no_active_tenant(db: DbContext) -> None:
    subject = f"sub-{uuid.uuid4().hex}"
    with pytest.raises(IdentityMappingError) as exc_info:
        await db.mapper.map_identity(
            provider="test", subject=subject, email="x@y.z", provision=False
        )
    assert exc_info.value.details["db_code"] == "IDENTITY_NOT_FOUND"

    provisioned = await db.mapper.map_identity(
        provider="test", subject=subject, email="x@y.z", provision=True
    )
    resolved = await db.mapper.map_identity(
        provider="test", subject=subject, email="x@y.z", provision=False
    )
    assert resolved == provisioned

    # A user whose only membership is suspended -> NO_ACTIVE_TENANT.
    await db.pool.execute(
        "UPDATE app.memberships SET status = 'suspended' WHERE user_id = $1",
        uuid.UUID(provisioned.user_id),
    )
    with pytest.raises(IdentityMappingError) as exc_info:
        await db.mapper.map_identity(
            provider="test", subject=subject, email="x@y.z", provision=False
        )
    assert exc_info.value.details["db_code"] == "NO_ACTIVE_TENANT"


# --- migration cycle -------------------------------------------------------------


async def test_migration_cycle_deploy_verify_revert_redeploy() -> None:
    connection = await asyncpg.connect(POSTGRES_TEST_DSN)
    try:
        await connection.execute("DROP SCHEMA IF EXISTS app CASCADE")
        assert len(plan_changes()) == 14
        await deploy_all(connection)
        await verify_all(connection)  # every verify script raises on failure
        await revert_all(connection)
        assert await connection.fetchval("SELECT to_regnamespace('app') IS NULL"), (
            "app schema must be gone after a full revert"
        )
        await deploy_all(connection)
        await verify_all(connection)
    finally:
        await connection.close()
