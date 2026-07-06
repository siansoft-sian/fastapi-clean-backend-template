"""In-memory BookingRepository — tenant-scoped, no I/O.

Used by the module's fast tests and reusable by any other module that needs a
booking dependency. Mirrors the DB contract's semantics: PENDING on create,
transition guard (belt-and-suspenders with the domain), optimistic version
check, slot-conflict emulation for active bookings on the same
resource/instant.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.errors.core_errors import ConflictError
from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.domain.booking_status import BookingStatus, is_allowed_transition
from app.modules.bookings.domain.errors import (
    BookingNotFoundError,
    BookingSlotUnavailableError,
    BookingVersionConflictError,
    InvalidStatusTransitionError,
)

if TYPE_CHECKING:
    from app.modules.bookings.ports.booking_repository import BookingRepositoryProtocol

_ACTIVE = (BookingStatus.PENDING, BookingStatus.APPROVED)


@dataclass
class FakeBookingRepository:
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _bookings: dict[tuple[str, str], BookingDTO] = field(default_factory=dict)

    async def create(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        reference: str,
        resource_id: str,
        scheduled_at: datetime,
        created_by: str,
    ) -> BookingDTO:
        for existing in self._bookings.values():
            if existing.tenant_id != tenant_id or existing.status not in _ACTIVE:
                continue
            if existing.reference == reference:
                raise ConflictError(
                    "Booking reference already exists", details={"reference": reference}
                )
            if existing.resource_id == resource_id and existing.scheduled_at == scheduled_at:
                raise BookingSlotUnavailableError(details={"resource_id": resource_id})
        now = self.clock()
        booking = BookingDTO(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            owner_id=owner_id,
            status=BookingStatus.PENDING,
            reference=reference,
            resource_id=resource_id,
            scheduled_at=scheduled_at,
            created_at=now,
            updated_at=now,
            version=1,
        )
        self._bookings[(tenant_id, booking.id)] = booking
        return booking

    async def get(self, *, tenant_id: str, booking_id: str) -> BookingDTO | None:
        return self._bookings.get((tenant_id, booking_id))

    def _require(self, tenant_id: str, booking_id: str) -> BookingDTO:
        booking = self._bookings.get((tenant_id, booking_id))
        if booking is None:
            raise BookingNotFoundError()
        return booking

    def _transition(
        self, booking: BookingDTO, target: BookingStatus, expected_version: int
    ) -> BookingDTO:
        if booking.version != expected_version:
            raise BookingVersionConflictError()
        if not is_allowed_transition(booking.status, target):
            raise InvalidStatusTransitionError(booking.status, target)
        updated = booking.model_copy(
            update={
                "status": target,
                "version": booking.version + 1,
                "updated_at": self.clock(),
            }
        )
        self._bookings[(booking.tenant_id, booking.id)] = updated
        return updated

    async def approve(
        self, *, tenant_id: str, booking_id: str, actor_id: str, expected_version: int
    ) -> BookingDTO:
        booking = self._require(tenant_id, booking_id)
        return self._transition(booking, BookingStatus.APPROVED, expected_version)

    async def cancel(
        self,
        *,
        tenant_id: str,
        booking_id: str,
        actor_id: str,
        expected_version: int,
        reason: str | None = None,
    ) -> BookingDTO:
        booking = self._require(tenant_id, booking_id)
        return self._transition(booking, BookingStatus.CANCELLED, expected_version)

    async def list_for_tenant(
        self,
        *,
        tenant_id: str,
        status: BookingStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[BookingDTO]:
        rows = [
            booking
            for (row_tenant, _), booking in self._bookings.items()
            if row_tenant == tenant_id and (status is None or booking.status is status)
        ]
        rows.sort(key=lambda booking: (booking.created_at, booking.id))
        return rows[offset : offset + limit]


if TYPE_CHECKING:
    _proof: BookingRepositoryProtocol = FakeBookingRepository()
