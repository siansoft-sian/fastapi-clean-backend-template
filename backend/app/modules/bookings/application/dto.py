"""BookingDTO — what repositories and use cases return. Frozen, typed, never
a dict/Record. Mirrors the entity; `to_entity()` feeds the domain policy."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.bookings.domain.booking import Booking
from app.modules.bookings.domain.booking_status import BookingStatus


class BookingDTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

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

    def to_entity(self) -> Booking:
        return Booking(
            id=self.id,
            tenant_id=self.tenant_id,
            owner_id=self.owner_id,
            status=self.status,
            reference=self.reference,
            resource_id=self.resource_id,
            scheduled_at=self.scheduled_at,
            created_at=self.created_at,
            updated_at=self.updated_at,
            version=self.version,
        )
