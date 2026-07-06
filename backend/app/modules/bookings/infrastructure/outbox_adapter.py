"""Outbox adapter — M6 interim sink.

# TODO(M7-outbox): replace with the transactional outbox: events written to
an outbox table IN THE SAME TRANSACTION as the state change, relayed by a
worker. Use cases already emit through OutboxPort, so M7 swaps this adapter
in bootstrap/factories.py without touching application code.

Until then: structured log + in-memory buffer (observable in tests/dev,
NOT durable).
"""

from typing import TYPE_CHECKING

import structlog

from app.modules.bookings.domain.events import BookingEvent

if TYPE_CHECKING:
    from app.modules.bookings.ports.outbox import OutboxPort

logger = structlog.get_logger(__name__)


class LoggingOutboxAdapter:
    def __init__(self) -> None:
        self.events: list[BookingEvent] = []

    async def emit(self, event: BookingEvent) -> None:
        self.events.append(event)
        logger.info(
            "domain_event_emitted",
            module="bookings",
            operation="outbox_emit",
            event_type=event.event_type,
            tenant_id=event.tenant_id,
        )


if TYPE_CHECKING:
    _proof: OutboxPort = LoggingOutboxAdapter()
