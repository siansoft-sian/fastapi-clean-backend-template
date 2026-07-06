"""Postgres-only session guarantees beyond the shared contract:
encryption at rest, and the identity_map function behavior."""

import uuid

import asyncpg
import pytest

from app.auth.exceptions import IdentityMappingError
from app.auth.identity_mapper import AsyncpgIdentityMapper
from app.auth.session_repository import AsyncpgSessionRepository
from tests.integration.session_scaffold import POSTGRES_TEST_DSN, apply_session_scaffold

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


@pytest.fixture
async def pool() -> asyncpg.Pool:
    await apply_session_scaffold(POSTGRES_TEST_DSN)
    pool = await asyncpg.create_pool(
        dsn=POSTGRES_TEST_DSN, min_size=1, max_size=2, statement_cache_size=0
    )
    assert pool is not None
    try:
        yield pool
    finally:
        await pool.close()


async def test_tokens_are_encrypted_at_rest(pool: asyncpg.Pool) -> None:
    repo = AsyncpgSessionRepository(pool)
    created = await repo.create(
        user_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        access_token="PLAINTEXT-ACCESS-MARKER",
        refresh_token="PLAINTEXT-REFRESH-MARKER",
        absolute_ttl_seconds=600,
        idle_ttl_seconds=60,
    )
    raw_access, raw_refresh = await pool.fetchrow(
        "SELECT gotrue_access_token, gotrue_refresh_token FROM app.user_sessions WHERE id = $1",
        uuid.UUID(created.id),
    )
    # The stored bytea must not contain the plaintext token anywhere.
    assert b"PLAINTEXT-ACCESS-MARKER" not in bytes(raw_access)
    assert b"PLAINTEXT-REFRESH-MARKER" not in bytes(raw_refresh)
    # ...while the function surface still round-trips the decrypted value.
    fetched = await repo.get(session_id=created.id)
    assert fetched is not None
    assert fetched.gotrue_access_token.get_secret_value() == "PLAINTEXT-ACCESS-MARKER"


async def test_map_identity_function_contract(pool: asyncpg.Pool) -> None:
    mapper = AsyncpgIdentityMapper(pool)
    subject = f"gotrue|{uuid.uuid4().hex}"
    user_id, tenant_id = str(uuid.uuid4()), str(uuid.uuid4())

    with pytest.raises(IdentityMappingError):
        await mapper.map_identity(provider_subject=subject, email=None)

    await pool.execute(
        "INSERT INTO app.identity_map (provider_subject, user_id, tenant_id) VALUES ($1, $2, $3)",
        subject,
        uuid.UUID(user_id),
        uuid.UUID(tenant_id),
    )
    identity = await mapper.map_identity(provider_subject=subject, email="x@y.z")
    assert identity.user_id == user_id
    assert identity.tenant_id == tenant_id
