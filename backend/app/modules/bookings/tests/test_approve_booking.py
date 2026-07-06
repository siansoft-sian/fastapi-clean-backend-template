"""ApproveBookingUseCase with fakes: happy path, denial, bad transition, 404s."""

import pytest

from app.authorization import permission_actions as pa
from app.core.errors.core_errors import ForbiddenError
from app.modules.bookings.application.commands import ApproveBookingCommand
from app.modules.bookings.application.use_cases.approve_booking import ApproveBookingUseCase
from app.modules.bookings.domain.booking_status import BookingStatus
from app.modules.bookings.domain.errors import (
    BookingNotFoundError,
    InvalidStatusTransitionError,
)
from app.modules.bookings.domain.events import BookingApproved
from app.modules.bookings.infrastructure.fake_booking_repository import FakeBookingRepository
from app.modules.bookings.tests.support import (
    OTHER_TENANT,
    TENANT,
    AllowAllAuthorization,
    DenyAllAuthorization,
    RecordingOutbox,
    make_principal,
    seed_booking,
)


def build(authorization: object | None = None):  # type: ignore[no-untyped-def]
    repo = FakeBookingRepository()
    authz = authorization or AllowAllAuthorization()
    outbox = RecordingOutbox()
    use_case = ApproveBookingUseCase(repository=repo, authorization=authz, outbox=outbox)  # type: ignore[arg-type]
    return use_case, repo, authz, outbox


async def test_happy_path_approves_and_emits() -> None:
    use_case, repo, authz, outbox = build()
    booking = await seed_booking(repo)
    principal = make_principal(user_id="manager-1")

    approved = await use_case.execute(ApproveBookingCommand(booking_id=booking.id), principal)

    assert approved.status is BookingStatus.APPROVED
    assert approved.version == booking.version + 1
    assert outbox.events == [
        BookingApproved(booking_id=booking.id, tenant_id=TENANT, approved_by="manager-1")
    ]
    # fine-grained ctx carries the LOADED resource's attributes
    ctx = authz.contexts[0]
    assert ctx.action == pa.APPROVE
    assert ctx.resource_owner_id == booking.owner_id
    assert ctx.resource_tenant_id == TENANT


async def test_denied_authorization_leaves_booking_pending() -> None:
    use_case, repo, _, outbox = build(authorization=DenyAllAuthorization())
    booking = await seed_booking(repo)
    with pytest.raises(ForbiddenError):
        await use_case.execute(ApproveBookingCommand(booking_id=booking.id), make_principal())
    unchanged = await repo.get(tenant_id=TENANT, booking_id=booking.id)
    assert unchanged is not None and unchanged.status is BookingStatus.PENDING
    assert outbox.events == []


async def test_invalid_transition_raises_domain_error() -> None:
    use_case, repo, _, outbox = build()
    booking = await seed_booking(repo)
    principal = make_principal()
    await use_case.execute(ApproveBookingCommand(booking_id=booking.id), principal)
    with pytest.raises(InvalidStatusTransitionError):  # approving twice
        await use_case.execute(ApproveBookingCommand(booking_id=booking.id), principal)
    assert len(outbox.events) == 1


async def test_missing_booking_is_404() -> None:
    use_case, _, _, _ = build()
    with pytest.raises(BookingNotFoundError):
        await use_case.execute(ApproveBookingCommand(booking_id="nope"), make_principal())


async def test_cross_tenant_booking_is_the_same_404() -> None:
    use_case, repo, _, outbox = build()
    foreign = await seed_booking(repo, tenant_id=OTHER_TENANT)
    with pytest.raises(BookingNotFoundError):  # tenant-scoped load never sees it
        await use_case.execute(
            ApproveBookingCommand(booking_id=foreign.id), make_principal(tenant_id=TENANT)
        )
    assert outbox.events == []
