"""Outbox port — reliable side effects seam.

# TODO(M7-outbox): the real transactional outbox (events persisted in the
same transaction as the state change, relayed by a worker) lands in M7. Until
then the adapter is an in-memory/logging sink; use cases already emit through
this port so M7 is a wiring change, not a refactor.
"""

from typing import Protocol

from app.modules.bookings.domain.events import BookingEvent


class OutboxPort(Protocol):
    async def emit(self, event: BookingEvent) -> None: ...
