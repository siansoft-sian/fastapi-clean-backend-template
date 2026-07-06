"""Shared fakes/builders for the bookings module tests. No I/O anywhere."""

from datetime import UTC, datetime

from app.auth.auth_context import AuthContext
from app.authorization.resource_context import ResourceContext
from app.core.errors.core_errors import ForbiddenError
from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.domain.events import BookingEvent
from app.modules.bookings.infrastructure.fake_booking_repository import FakeBookingRepository

TENANT = "tenant-1"
OTHER_TENANT = "tenant-2"
SCHEDULED_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


class AllowAllAuthorization:
    """Records every ResourceContext it was asked to enforce."""

    def __init__(self) -> None:
        self.contexts: list[ResourceContext] = []

    def enforce(self, ctx: ResourceContext) -> None:
        self.contexts.append(ctx)


class DenyAllAuthorization:
    def enforce(self, ctx: ResourceContext) -> None:
        raise ForbiddenError(details={"action": ctx.action})


class RecordingOutbox:
    def __init__(self) -> None:
        self.events: list[BookingEvent] = []

    async def emit(self, event: BookingEvent) -> None:
        self.events.append(event)


def make_principal(
    *, user_id: str = "user-1", tenant_id: str = TENANT, roles: frozenset[str] = frozenset()
) -> AuthContext:
    return AuthContext(user_id=user_id, tenant_id=tenant_id, session_id="session-1", roles=roles)


async def seed_booking(
    repo: FakeBookingRepository,
    *,
    tenant_id: str = TENANT,
    owner_id: str = "user-1",
    reference: str = "BK-001",
    resource_id: str = "room-a",
) -> BookingDTO:
    return await repo.create(
        tenant_id=tenant_id,
        owner_id=owner_id,
        reference=reference,
        resource_id=resource_id,
        scheduled_at=SCHEDULED_AT,
        created_by=owner_id,
    )
