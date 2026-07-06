"""Persistence port. Every method takes tenant_id explicitly (a cross-tenant
booking is never returned — `get` answers None, mutations raise not-found)
and returns typed DTOs. Mutations take `expected_version` for optimistic
concurrency; a stale version raises BookingVersionConflictError.
"""

from datetime import datetime
from typing import Protocol

from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.domain.booking_status import BookingStatus


class BookingRepositoryProtocol(Protocol):
    async def create(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        reference: str,
        resource_id: str,
        scheduled_at: datetime,
        created_by: str,
    ) -> BookingDTO: ...

    async def get(self, *, tenant_id: str, booking_id: str) -> BookingDTO | None: ...

    async def approve(
        self, *, tenant_id: str, booking_id: str, actor_id: str, expected_version: int
    ) -> BookingDTO: ...

    async def cancel(
        self,
        *,
        tenant_id: str,
        booking_id: str,
        actor_id: str,
        expected_version: int,
        reason: str | None = None,
    ) -> BookingDTO: ...

    async def list_for_tenant(
        self,
        *,
        tenant_id: str,
        status: BookingStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[BookingDTO]: ...
