"""CreateBookingUseCase with fakes: happy path, denial, duplicate reference."""

import pytest

from app.authorization import permission_actions as pa
from app.core.errors.core_errors import ConflictError, ForbiddenError
from app.modules.bookings.application.commands import CreateBookingCommand
from app.modules.bookings.application.use_cases.create_booking import CreateBookingUseCase
from app.modules.bookings.domain.booking_status import BookingStatus
from app.modules.bookings.domain.events import BookingCreated
from app.modules.bookings.infrastructure.fake_booking_repository import FakeBookingRepository
from app.modules.bookings.tests.support import (
    SCHEDULED_AT,
    TENANT,
    AllowAllAuthorization,
    DenyAllAuthorization,
    RecordingOutbox,
    make_principal,
)

COMMAND = CreateBookingCommand(reference="BK-100", resource_id="room-a", scheduled_at=SCHEDULED_AT)


def make_use_case(
    repo: FakeBookingRepository | None = None,
    authorization: object | None = None,
    outbox: RecordingOutbox | None = None,
) -> tuple[CreateBookingUseCase, FakeBookingRepository, AllowAllAuthorization, RecordingOutbox]:
    repo = repo or FakeBookingRepository()
    authz = authorization or AllowAllAuthorization()
    outbox = outbox or RecordingOutbox()
    return (
        CreateBookingUseCase(repository=repo, authorization=authz, outbox=outbox),  # type: ignore[arg-type]
        repo,
        authz,  # type: ignore[return-value]
        outbox,
    )


async def test_happy_path_creates_pending_booking_and_emits_event() -> None:
    use_case, repo, authz, outbox = make_use_case()
    principal = make_principal()

    booking = await use_case.execute(COMMAND, principal)

    assert booking.status is BookingStatus.PENDING
    assert booking.tenant_id == TENANT
    assert booking.owner_id == principal.user_id
    assert booking.reference == "BK-100"
    assert booking.version == 1
    # persisted, tenant-scoped
    assert await repo.get(tenant_id=TENANT, booking_id=booking.id) == booking
    # exactly one event with the right payload
    assert outbox.events == [
        BookingCreated(
            booking_id=booking.id,
            tenant_id=TENANT,
            owner_id=principal.user_id,
            reference="BK-100",
        )
    ]
    # the fine-grained check saw a CREATE intent scoped to the actor's tenant
    ctx = authz.contexts[0]
    assert ctx.action == pa.CREATE
    assert ctx.resource_type == pa.BOOKING
    assert ctx.tenant_id == TENANT == ctx.resource_tenant_id


async def test_denied_authorization_prevents_creation_and_event() -> None:
    use_case, repo, _, outbox = make_use_case(authorization=DenyAllAuthorization())
    with pytest.raises(ForbiddenError):
        await use_case.execute(COMMAND, make_principal())
    assert await repo.list_for_tenant(tenant_id=TENANT) == []
    assert outbox.events == []


async def test_duplicate_reference_conflicts_and_emits_nothing() -> None:
    """Determinism seam: replaying the same command cannot create twice.
    # TODO(M7-idempotency): the middleware will replay the stored response."""
    use_case, _, _, outbox = make_use_case()
    principal = make_principal()
    await use_case.execute(COMMAND, principal)
    with pytest.raises(ConflictError):
        await use_case.execute(COMMAND, principal)
    assert len(outbox.events) == 1
