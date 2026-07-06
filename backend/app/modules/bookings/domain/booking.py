"""Booking entity — pure. Transitions return NEW frozen instances and raise
InvalidStatusTransitionError when the lifecycle forbids the change.

Timestamps are persistence concerns (the DB sets created_at/updated_at);
`version` supports optimistic concurrency and bumps on every transition.
"""

from dataclasses import dataclass, replace
from datetime import datetime

from app.modules.bookings.domain.booking_status import BookingStatus, is_allowed_transition
from app.modules.bookings.domain.errors import InvalidStatusTransitionError


@dataclass(frozen=True)
class Booking:
    id: str
    tenant_id: str
    owner_id: str
    status: BookingStatus
    reference: str
    resource_id: str
    scheduled_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int

    def _transition(self, target: BookingStatus) -> "Booking":
        if not is_allowed_transition(self.status, target):
            raise InvalidStatusTransitionError(self.status, target)
        return replace(self, status=target, version=self.version + 1)

    def approve(self) -> "Booking":
        return self._transition(BookingStatus.APPROVED)

    def cancel(self) -> "Booking":
        return self._transition(BookingStatus.CANCELLED)

    def complete(self) -> "Booking":
        return self._transition(BookingStatus.COMPLETED)
