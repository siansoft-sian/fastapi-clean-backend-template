"""Booking domain errors — extend the core AppError family so the exception
boundary maps them to the standard envelope. Codes are stable API contract."""

from app.core.errors.core_errors import ConflictError, NotFoundError
from app.modules.bookings.domain.booking_status import BookingStatus

BOOKING_NOT_FOUND = "BOOKING_NOT_FOUND"
BOOKING_INVALID_TRANSITION = "BOOKING_INVALID_TRANSITION"
BOOKING_SLOT_UNAVAILABLE = "BOOKING_SLOT_UNAVAILABLE"
BOOKING_VERSION_CONFLICT = "BOOKING_VERSION_CONFLICT"


class BookingNotFoundError(NotFoundError):
    """Also the cross-tenant answer: existence is never revealed."""

    code = BOOKING_NOT_FOUND
    default_message = "Booking not found"


class InvalidStatusTransitionError(ConflictError):
    code = BOOKING_INVALID_TRANSITION
    default_message = "Booking cannot change to the requested status"

    def __init__(self, current: BookingStatus, target: BookingStatus) -> None:
        super().__init__(details={"current": current.value, "target": target.value})


class BookingSlotUnavailableError(ConflictError):
    """The resource/time window is already booked (DB exclusion constraint)."""

    code = BOOKING_SLOT_UNAVAILABLE
    default_message = "The requested slot is no longer available"


class BookingVersionConflictError(ConflictError):
    """Optimistic-concurrency failure: the booking changed since it was read."""

    code = BOOKING_VERSION_CONFLICT
    default_message = "Booking was modified concurrently; reload and retry"
