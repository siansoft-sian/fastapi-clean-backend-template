"""Eligibility guards used by the use cases BEFORE persisting a transition.

TEMPLATE DEFAULTS — # TODO(BA): the real approval/cancellation eligibility
(cut-off windows, who may cancel after approval, fees, ...) comes from the
business-analyst stage. Keep these as pure functions of the entity.
"""

from app.modules.bookings.domain.booking import Booking
from app.modules.bookings.domain.booking_status import BookingStatus
from app.modules.bookings.domain.errors import InvalidStatusTransitionError


def ensure_can_approve(booking: Booking) -> None:
    # TODO(BA): template default — only PENDING bookings are approvable.
    if booking.status is not BookingStatus.PENDING:
        raise InvalidStatusTransitionError(booking.status, BookingStatus.APPROVED)


def ensure_can_cancel(booking: Booking) -> None:
    # TODO(BA): template default — PENDING and APPROVED bookings may cancel.
    if booking.status not in (BookingStatus.PENDING, BookingStatus.APPROVED):
        raise InvalidStatusTransitionError(booking.status, BookingStatus.CANCELLED)
