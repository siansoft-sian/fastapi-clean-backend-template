"""Read-side inputs. Plain frozen dataclasses — no framework."""

from dataclasses import dataclass

from app.modules.bookings.domain.booking_status import BookingStatus


@dataclass(frozen=True)
class GetBookingQuery:
    booking_id: str


@dataclass(frozen=True)
class ListBookingsQuery:
    status: BookingStatus | None = None
    limit: int = 20
    offset: int = 0
