"""Write-side inputs. Plain frozen dataclasses — no framework.

CreateBookingCommand is DETERMINISTIC given its fields: `reference` is the
client-supplied, tenant-unique business key, which makes the create use case
idempotency-friendly. # TODO(M7-idempotency): the Idempotency-Key middleware
lands in M7 and will key replays on this command's route.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CreateBookingCommand:
    reference: str
    resource_id: str
    scheduled_at: datetime


@dataclass(frozen=True)
class ApproveBookingCommand:
    booking_id: str


@dataclass(frozen=True)
class CancelBookingCommand:
    booking_id: str
    reason: str | None = None
