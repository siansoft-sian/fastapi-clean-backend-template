"""asyncpg adapter for the BookingRepository port — the ONLY booking code that
knows the engine.

Calls the envelope-returning Postgres functions documented in
database/postgres/functions/README.md (authored by database-designer +
sqitch-migration-engineer; not yet applied — the integration suite self-skips
until they land). bytea/uuid/timestamptz mapping mirrors the M3 session
repository; DB error codes map to the module's domain errors.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, NoReturn

import asyncpg

from app.core.errors.core_errors import ConflictError, DatabaseResultError
from app.db.errors import map_asyncpg_error
from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.domain.booking_status import BookingStatus
from app.modules.bookings.domain.errors import (
    BookingNotFoundError,
    BookingSlotUnavailableError,
    BookingVersionConflictError,
    InvalidStatusTransitionError,
)

if TYPE_CHECKING:
    from app.modules.bookings.ports.booking_repository import BookingRepositoryProtocol


def _raise_for_db_code(code: str | None, details: dict[str, Any]) -> NoReturn:
    if code == "BOOKING_NOT_FOUND":
        raise BookingNotFoundError()
    if code == "BOOKING_INVALID_TRANSITION":
        raise InvalidStatusTransitionError(
            BookingStatus(details.get("current", "pending")),
            BookingStatus(details.get("target", "pending")),
        )
    if code == "BOOKING_SLOT_UNAVAILABLE":
        raise BookingSlotUnavailableError(details=details)
    if code == "BOOKING_VERSION_CONFLICT":
        raise BookingVersionConflictError()
    if code == "BOOKING_REFERENCE_EXISTS":
        raise ConflictError("Booking reference already exists", details=details)
    raise DatabaseResultError("Booking function reported an error", details={"code": code})


class DatabaseBookingRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

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
        data = await self._call(
            "SELECT app.fn_create_booking($1, $2, $3, $4, $5, $6)",
            uuid.UUID(tenant_id),
            uuid.UUID(owner_id),
            reference,
            resource_id,
            scheduled_at,
            uuid.UUID(created_by),
        )
        return self._to_dto(data)

    async def get(self, *, tenant_id: str, booking_id: str) -> BookingDTO | None:
        if not _is_uuid(booking_id):
            return None  # path params are caller-controlled; never reach SQL malformed
        try:
            data = await self._call(
                "SELECT app.fn_get_booking($1, $2)", uuid.UUID(tenant_id), uuid.UUID(booking_id)
            )
        except BookingNotFoundError:
            return None
        return self._to_dto(data)

    async def approve(
        self, *, tenant_id: str, booking_id: str, actor_id: str, expected_version: int
    ) -> BookingDTO:
        data = await self._call(
            "SELECT app.fn_approve_booking($1, $2, $3, $4)",
            uuid.UUID(tenant_id),
            uuid.UUID(booking_id),
            uuid.UUID(actor_id),
            expected_version,
        )
        return self._to_dto(data)

    async def cancel(
        self,
        *,
        tenant_id: str,
        booking_id: str,
        actor_id: str,
        expected_version: int,
        reason: str | None = None,
    ) -> BookingDTO:
        data = await self._call(
            "SELECT app.fn_cancel_booking($1, $2, $3, $4, $5)",
            uuid.UUID(tenant_id),
            uuid.UUID(booking_id),
            uuid.UUID(actor_id),
            expected_version,
            reason,
        )
        return self._to_dto(data)

    async def list_for_tenant(
        self,
        *,
        tenant_id: str,
        status: BookingStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[BookingDTO]:
        data = await self._call(
            "SELECT app.fn_list_bookings($1, $2, $3, $4)",
            uuid.UUID(tenant_id),
            status.value if status is not None else None,
            limit,
            offset,
        )
        rows = data.get("bookings")
        if not isinstance(rows, list):
            raise DatabaseResultError("fn_list_bookings envelope missing bookings list")
        return [BookingDTO(**row) for row in rows]

    @staticmethod
    def _to_dto(data: dict[str, Any]) -> BookingDTO:
        booking = data.get("booking")
        if not isinstance(booking, dict):
            raise DatabaseResultError("Booking function envelope missing booking object")
        return BookingDTO(**booking)

    async def _call(self, query: str, *args: Any) -> dict[str, Any]:
        try:
            raw = await self._pool.fetchval(query, *args)
        except asyncpg.exceptions.ExclusionViolationError as exc:
            # The double-booking EXCLUDE constraint fired under concurrency.
            raise BookingSlotUnavailableError() from exc
        except asyncpg.UniqueViolationError as exc:
            raise ConflictError(
                "Booking reference already exists",
                details={"constraint": getattr(exc, "constraint_name", None)},
            ) from exc
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc
        envelope = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(envelope, dict):
            raise DatabaseResultError("Booking function returned a non-envelope result")
        if envelope.get("success"):
            data = envelope.get("data")
            return data if isinstance(data, dict) else {}
        error = envelope.get("error") or {}
        _raise_for_db_code(error.get("code"), error.get("details") or {})


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


if TYPE_CHECKING:
    _proof: BookingRepositoryProtocol = DatabaseBookingRepository(None)
