"""API boundary models — deliberately separate from the internal BookingDTO
so the wire contract can evolve independently of the persistence shape."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.domain.booking_status import BookingStatus


class CreateBookingRequest(BaseModel):
    # `reference` is the client-supplied, tenant-unique business key — the
    # determinism anchor for safe retries. # TODO(M7-idempotency)
    reference: str = Field(min_length=1, max_length=64)
    resource_id: str = Field(min_length=1, max_length=128)
    scheduled_at: datetime


class CancelBookingRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BookingResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

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

    @classmethod
    def from_dto(cls, dto: BookingDTO) -> "BookingResponse":
        return cls(**dto.model_dump())
