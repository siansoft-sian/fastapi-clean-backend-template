"""Domain events emitted through OutboxPort after a state change persists.

`event_type` is the stable name the M7 transactional outbox will store;
payloads stay minimal (ids + the facts of the change, never whole entities).
"""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class BookingCreated:
    event_type: ClassVar[str] = "booking.created"
    booking_id: str
    tenant_id: str
    owner_id: str
    reference: str


@dataclass(frozen=True)
class BookingApproved:
    event_type: ClassVar[str] = "booking.approved"
    booking_id: str
    tenant_id: str
    approved_by: str


@dataclass(frozen=True)
class BookingCancelled:
    event_type: ClassVar[str] = "booking.cancelled"
    booking_id: str
    tenant_id: str
    cancelled_by: str
    reason: str | None = None


BookingEvent = BookingCreated | BookingApproved | BookingCancelled
