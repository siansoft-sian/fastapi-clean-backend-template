"""One booking-repository contract, two implementations (M2 pattern).

The fake runs in the fast gate. The asyncpg half runs under the integration
markers and SELF-SKIPS until database-designer/sqitch apply the bookings
functions (checks to_regprocedure) — it activates automatically when they land.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors.core_errors import ConflictError
from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.domain.booking_status import BookingStatus
from app.modules.bookings.domain.errors import (
    BookingNotFoundError,
    BookingSlotUnavailableError,
    BookingVersionConflictError,
    InvalidStatusTransitionError,
)
from app.modules.bookings.infrastructure.fake_booking_repository import FakeBookingRepository
from app.modules.bookings.ports.booking_repository import BookingRepositoryProtocol


@dataclass
class Actors:
    tenant_id: str
    owner_id: str


@dataclass
class RepoContext:
    repo: BookingRepositoryProtocol
    seed_actors: Callable[[], Awaitable[Actors]]


def _fake_context() -> RepoContext:
    repo = FakeBookingRepository()

    async def seed() -> Actors:
        return Actors(tenant_id=str(uuid.uuid4()), owner_id=str(uuid.uuid4()))

    return RepoContext(repo=repo, seed_actors=seed)


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

    import asyncpg

    from app.auth.identity_mapper import AsyncpgIdentityMapper
    from app.modules.bookings.infrastructure.database_booking_repository import (
        DatabaseBookingRepository,
    )
    from tests.integration.sqitch_harness import POSTGRES_TEST_DSN, reset_and_deploy

    await reset_and_deploy(POSTGRES_TEST_DSN)
    pool = await asyncpg.create_pool(
        dsn=POSTGRES_TEST_DSN, min_size=1, max_size=2, statement_cache_size=0
    )
    assert pool is not None
    try:
        if await pool.fetchval(
            "SELECT to_regprocedure($1) IS NULL",
            "app.fn_create_booking(uuid, uuid, text, text, timestamptz, uuid)",
        ):
            pytest.skip(
                "bookings functions not applied yet (pending database-designer/"
                "sqitch milestone — see database/postgres/functions/README.md)"
            )
        mapper = AsyncpgIdentityMapper(pool)

        async def seed() -> Actors:
            identity = await mapper.map_identity(
                provider="test",
                subject=f"sub-{uuid.uuid4().hex}",
                email=f"{uuid.uuid4().hex[:8]}@example.com",
                provision=True,
            )
            return Actors(tenant_id=identity.tenant_id, owner_id=identity.user_id)

        yield RepoContext(repo=DatabaseBookingRepository(pool), seed_actors=seed)
    finally:
        await pool.close()


def slot(hours_from_base: int = 0) -> datetime:
    return datetime(2026, 9, 1, 9, 0, tzinfo=UTC) + timedelta(hours=hours_from_base)


async def create(
    ctx: RepoContext, actors: Actors, *, reference: str, resource: str = "room-a", hour: int = 0
) -> BookingDTO:
    return await ctx.repo.create(
        tenant_id=actors.tenant_id,
        owner_id=actors.owner_id,
        reference=reference,
        resource_id=resource,
        scheduled_at=slot(hour),
        created_by=actors.owner_id,
    )


async def test_create_then_get_round_trips(ctx: RepoContext) -> None:
    actors = await ctx.seed_actors()
    created = await create(ctx, actors, reference="BK-1")
    assert created.status is BookingStatus.PENDING
    assert created.version == 1

    fetched = await ctx.repo.get(tenant_id=actors.tenant_id, booking_id=created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.reference == "BK-1"
    assert fetched.owner_id == actors.owner_id


async def test_get_unknown_and_cross_tenant_return_none(ctx: RepoContext) -> None:
    actors = await ctx.seed_actors()
    other = await ctx.seed_actors()
    created = await create(ctx, actors, reference="BK-2")
    assert await ctx.repo.get(tenant_id=actors.tenant_id, booking_id=str(uuid.uuid4())) is None
    # Same id, different tenant: never visible.
    assert await ctx.repo.get(tenant_id=other.tenant_id, booking_id=created.id) is None


async def test_duplicate_reference_conflicts(ctx: RepoContext) -> None:
    actors = await ctx.seed_actors()
    await create(ctx, actors, reference="BK-3", hour=0)
    with pytest.raises(ConflictError):
        await create(ctx, actors, reference="BK-3", hour=5)


async def test_same_slot_same_resource_is_unavailable(ctx: RepoContext) -> None:
    actors = await ctx.seed_actors()
    await create(ctx, actors, reference="BK-4a", resource="room-x", hour=0)
    with pytest.raises(BookingSlotUnavailableError):
        await create(ctx, actors, reference="BK-4b", resource="room-x", hour=0)
    # Different resource at the same instant is fine.
    await create(ctx, actors, reference="BK-4c", resource="room-y", hour=0)


async def test_approve_and_cancel_lifecycle_with_versions(ctx: RepoContext) -> None:
    actors = await ctx.seed_actors()
    created = await create(ctx, actors, reference="BK-5")

    approved = await ctx.repo.approve(
        tenant_id=actors.tenant_id,
        booking_id=created.id,
        actor_id=actors.owner_id,
        expected_version=created.version,
    )
    assert approved.status is BookingStatus.APPROVED
    assert approved.version == 2

    cancelled = await ctx.repo.cancel(
        tenant_id=actors.tenant_id,
        booking_id=created.id,
        actor_id=actors.owner_id,
        expected_version=approved.version,
        reason="test",
    )
    assert cancelled.status is BookingStatus.CANCELLED
    assert cancelled.version == 3


async def test_stale_version_conflicts(ctx: RepoContext) -> None:
    actors = await ctx.seed_actors()
    created = await create(ctx, actors, reference="BK-6")
    await ctx.repo.approve(
        tenant_id=actors.tenant_id,
        booking_id=created.id,
        actor_id=actors.owner_id,
        expected_version=1,
    )
    with pytest.raises(BookingVersionConflictError):  # still holding version 1
        await ctx.repo.cancel(
            tenant_id=actors.tenant_id,
            booking_id=created.id,
            actor_id=actors.owner_id,
            expected_version=1,
        )


async def test_invalid_transition_guard_in_repository(ctx: RepoContext) -> None:
    """Belt-and-suspenders: even bypassing the domain policy, the repository
    (and the DB function behind it) refuses an illegal transition."""
    actors = await ctx.seed_actors()
    created = await create(ctx, actors, reference="BK-7")
    cancelled = await ctx.repo.cancel(
        tenant_id=actors.tenant_id,
        booking_id=created.id,
        actor_id=actors.owner_id,
        expected_version=1,
    )
    with pytest.raises(InvalidStatusTransitionError):
        await ctx.repo.approve(
            tenant_id=actors.tenant_id,
            booking_id=created.id,
            actor_id=actors.owner_id,
            expected_version=cancelled.version,
        )


async def test_mutations_are_tenant_scoped(ctx: RepoContext) -> None:
    actors = await ctx.seed_actors()
    intruder = await ctx.seed_actors()
    created = await create(ctx, actors, reference="BK-8")
    with pytest.raises(BookingNotFoundError):
        await ctx.repo.approve(
            tenant_id=intruder.tenant_id,
            booking_id=created.id,
            actor_id=intruder.owner_id,
            expected_version=1,
        )


async def test_list_for_tenant_filters_and_paginates(ctx: RepoContext) -> None:
    actors = await ctx.seed_actors()
    first = await create(ctx, actors, reference="BK-9a", hour=0)
    await create(ctx, actors, reference="BK-9b", hour=1)
    await ctx.repo.approve(
        tenant_id=actors.tenant_id,
        booking_id=first.id,
        actor_id=actors.owner_id,
        expected_version=1,
    )

    everything = await ctx.repo.list_for_tenant(tenant_id=actors.tenant_id)
    assert {row.reference for row in everything} == {"BK-9a", "BK-9b"}
    approved_only = await ctx.repo.list_for_tenant(
        tenant_id=actors.tenant_id, status=BookingStatus.APPROVED
    )
    assert [row.reference for row in approved_only] == ["BK-9a"]
    paged = await ctx.repo.list_for_tenant(tenant_id=actors.tenant_id, limit=1, offset=1)
    assert len(paged) == 1
