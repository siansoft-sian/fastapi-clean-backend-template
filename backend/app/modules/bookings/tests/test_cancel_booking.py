"""CancelBookingUseCase with fakes: pending + approved cancel, terminal deny, 404."""

import pytest

from app.modules.bookings.application.commands import (
    ApproveBookingCommand,
    CancelBookingCommand,
)
from app.modules.bookings.application.use_cases.approve_booking import ApproveBookingUseCase
from app.modules.bookings.application.use_cases.cancel_booking import CancelBookingUseCase
from app.modules.bookings.domain.booking_status import BookingStatus
from app.modules.bookings.domain.errors import (
    BookingNotFoundError,
    InvalidStatusTransitionError,
)
from app.modules.bookings.domain.events import BookingCancelled
from app.modules.bookings.infrastructure.fake_booking_repository import FakeBookingRepository
from app.modules.bookings.tests.support import (
    TENANT,
    AllowAllAuthorization,
    RecordingOutbox,
    make_principal,
    seed_booking,
)


def build():  # type: ignore[no-untyped-def]
    repo = FakeBookingRepository()
    authz = AllowAllAuthorization()
    outbox = RecordingOutbox()
    cancel = CancelBookingUseCase(repository=repo, authorization=authz, outbox=outbox)
    approve = ApproveBookingUseCase(repository=repo, authorization=authz, outbox=outbox)
    return cancel, approve, repo, outbox


async def test_cancel_pending_with_reason_emits_event() -> None:
    cancel, _, repo, outbox = build()
    booking = await seed_booking(repo)
    principal = make_principal()

    cancelled = await cancel.execute(
        CancelBookingCommand(booking_id=booking.id, reason="client asked"), principal
    )

    assert cancelled.status is BookingStatus.CANCELLED
    assert outbox.events == [
        BookingCancelled(
            booking_id=booking.id,
            tenant_id=TENANT,
            cancelled_by=principal.user_id,
            reason="client asked",
        )
    ]


async def test_cancel_after_approval_is_allowed() -> None:
    cancel, approve, repo, _ = build()
    booking = await seed_booking(repo)
    principal = make_principal()
    await approve.execute(ApproveBookingCommand(booking_id=booking.id), principal)

    cancelled = await cancel.execute(CancelBookingCommand(booking_id=booking.id), principal)
    assert cancelled.status is BookingStatus.CANCELLED
    assert cancelled.version == 3  # created -> approved -> cancelled


async def test_cancel_terminal_booking_raises_domain_error() -> None:
    cancel, _, repo, outbox = build()
    booking = await seed_booking(repo)
    principal = make_principal()
    await cancel.execute(CancelBookingCommand(booking_id=booking.id), principal)
    with pytest.raises(InvalidStatusTransitionError):  # cancelling twice
        await cancel.execute(CancelBookingCommand(booking_id=booking.id), principal)
    assert len(outbox.events) == 1


async def test_missing_booking_is_404() -> None:
    cancel, _, _, _ = build()
    with pytest.raises(BookingNotFoundError):
        await cancel.execute(CancelBookingCommand(booking_id="nope"), make_principal())
