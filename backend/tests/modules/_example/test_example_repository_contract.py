"""One contract, two implementations.

The same behavioral suite runs against the in-memory fake (fast gate) and the
asyncpg adapter (integration gate) — proving both satisfy
ExampleRepositoryProtocol identically. Tenant isolation comes from unique
tenant ids per test, so the Postgres run needs no truncation between tests.
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest

from app.modules._example.infrastructure.fake_example_repository import FakeExampleRepository
from app.modules._example.ports.example_repository import (
    ExampleItemDTO,
    ExampleRepositoryProtocol,
)

POSTGRES_TEST_DSN = os.environ.get("POSTGRES_TEST_DSN", "postgresql://app:app@localhost:5432/app")


def unique_tenant() -> str:
    return f"tenant-{uuid.uuid4().hex}"


@pytest.fixture(
    params=[
        pytest.param("fake"),
        pytest.param("postgres", marks=[pytest.mark.integration, pytest.mark.postgres]),
    ]
)
async def repo(request: pytest.FixtureRequest) -> AsyncIterator[ExampleRepositoryProtocol]:
    if request.param == "fake":
        yield FakeExampleRepository()
        return

    # Integration path: tests construct the infrastructure adapter directly.
    import asyncpg

    from app.modules._example.infrastructure.database_example_repository import (
        DatabaseExampleRepository,
    )

    pool = await asyncpg.create_pool(
        dsn=POSTGRES_TEST_DSN, min_size=1, max_size=2, statement_cache_size=0
    )
    assert pool is not None
    repository = DatabaseExampleRepository(pool)
    await repository.ensure_schema()
    try:
        yield repository
    finally:
        await pool.close()


async def test_create_returns_dto_and_get_round_trips(repo: ExampleRepositoryProtocol) -> None:
    tenant_id = unique_tenant()
    created = await repo.create(tenant_id=tenant_id, name="first item")
    assert isinstance(created, ExampleItemDTO)
    assert created.tenant_id == tenant_id
    assert created.name == "first item"
    assert created.id

    fetched = await repo.get(tenant_id=tenant_id, item_id=created.id)
    assert fetched == created


async def test_get_missing_id_returns_none(repo: ExampleRepositoryProtocol) -> None:
    assert await repo.get(tenant_id=unique_tenant(), item_id="does-not-exist") is None


async def test_get_does_not_cross_tenants(repo: ExampleRepositoryProtocol) -> None:
    tenant_a, tenant_b = unique_tenant(), unique_tenant()
    created = await repo.create(tenant_id=tenant_a, name="private to a")
    assert await repo.get(tenant_id=tenant_b, item_id=created.id) is None


async def test_list_for_tenant_isolates_tenants(repo: ExampleRepositoryProtocol) -> None:
    tenant_a, tenant_b = unique_tenant(), unique_tenant()
    await repo.create(tenant_id=tenant_a, name="a1")
    await repo.create(tenant_id=tenant_a, name="a2")
    await repo.create(tenant_id=tenant_b, name="b1")

    names_a = [item.name for item in await repo.list_for_tenant(tenant_id=tenant_a)]
    names_b = [item.name for item in await repo.list_for_tenant(tenant_id=tenant_b)]
    assert names_a == ["a1", "a2"]
    assert names_b == ["b1"]


async def test_list_for_empty_tenant_is_empty(repo: ExampleRepositoryProtocol) -> None:
    assert await repo.list_for_tenant(tenant_id=unique_tenant()) == []


async def test_dto_is_immutable(repo: ExampleRepositoryProtocol) -> None:
    created = await repo.create(tenant_id=unique_tenant(), name="frozen")
    with pytest.raises(Exception, match="frozen"):
        created.name = "mutated"  # type: ignore[misc]
