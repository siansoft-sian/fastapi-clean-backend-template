"""Pure domain: lifecycle transitions, entity methods, policy guards."""

from datetime import UTC, datetime

import pytest

from app.modules.bookings.domain.booking import Booking
from app.modules.bookings.domain.booking_policy import ensure_can_approve, ensure_can_cancel
from app.modules.bookings.domain.booking_status import (
    BookingStatus,
    allowed_targets,
    is_allowed_transition,
)
from app.modules.bookings.domain.errors import InvalidStatusTransitionError


def make_booking(status: BookingStatus = BookingStatus.PENDING) -> Booking:
    now = datetime.now(UTC)
    return Booking(
        id="booking-1",
        tenant_id="tenant-1",
        owner_id="user-1",
        status=status,
        reference="BK-001",
        resource_id="room-a",
        scheduled_at=now,
        created_at=now,
        updated_at=now,
        version=1,
    )


# --- transition map ---


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (BookingStatus.PENDING, BookingStatus.APPROVED, True),
        (BookingStatus.PENDING, BookingStatus.CANCELLED, True),
        (BookingStatus.PENDING, BookingStatus.COMPLETED, False),
        (BookingStatus.APPROVED, BookingStatus.CANCELLED, True),
        (BookingStatus.APPROVED, BookingStatus.COMPLETED, True),
        (BookingStatus.APPROVED, BookingStatus.PENDING, False),
        (BookingStatus.CANCELLED, BookingStatus.PENDING, False),
        (BookingStatus.COMPLETED, BookingStatus.CANCELLED, False),
    ],
)
def test_transition_map(current: BookingStatus, target: BookingStatus, allowed: bool) -> None:
    assert is_allowed_transition(current, target) is allowed


def test_terminal_states_have_no_targets() -> None:
    assert allowed_targets(BookingStatus.CANCELLED) == frozenset()
    assert allowed_targets(BookingStatus.COMPLETED) == frozenset()


# --- entity transitions ---


def test_approve_returns_new_instance_and_bumps_version() -> None:
    booking = make_booking()
    approved = booking.approve()
    assert approved is not booking
    assert booking.status is BookingStatus.PENDING  # original untouched (frozen)
    assert approved.status is BookingStatus.APPROVED
    assert approved.version == booking.version + 1


def test_cancel_from_approved_is_allowed() -> None:
    cancelled = make_booking(BookingStatus.APPROVED).cancel()
    assert cancelled.status is BookingStatus.CANCELLED


def test_invalid_entity_transition_raises_domain_error() -> None:
    with pytest.raises(InvalidStatusTransitionError) as exc_info:
        make_booking(BookingStatus.CANCELLED).approve()
    assert exc_info.value.http_status == 409
    assert exc_info.value.details == {"current": "cancelled", "target": "approved"}


def test_complete_only_from_approved() -> None:
    assert make_booking(BookingStatus.APPROVED).complete().status is BookingStatus.COMPLETED
    with pytest.raises(InvalidStatusTransitionError):
        make_booking(BookingStatus.PENDING).complete()


# --- policy guards (template defaults, TODO(BA)) ---


def test_policy_allows_approving_pending_only() -> None:
    ensure_can_approve(make_booking(BookingStatus.PENDING))  # no raise
    for status in (BookingStatus.APPROVED, BookingStatus.CANCELLED, BookingStatus.COMPLETED):
        with pytest.raises(InvalidStatusTransitionError):
            ensure_can_approve(make_booking(status))


def test_policy_allows_cancelling_pending_and_approved() -> None:
    ensure_can_cancel(make_booking(BookingStatus.PENDING))
    ensure_can_cancel(make_booking(BookingStatus.APPROVED))
    for status in (BookingStatus.CANCELLED, BookingStatus.COMPLETED):
        with pytest.raises(InvalidStatusTransitionError):
            ensure_can_cancel(make_booking(status))
