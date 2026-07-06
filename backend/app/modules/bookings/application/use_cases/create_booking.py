"""Create a booking.

Deterministic given the command (client-supplied tenant-unique `reference`),
so a replay creates nothing twice — the repository/DB rejects the duplicate
reference. # TODO(M7-idempotency): the Idempotency-Key middleware will replay
the stored response instead of re-executing.
"""

from app.auth.auth_context import AuthContext
from app.authorization import permission_actions
from app.authorization.resource_context import ResourceContext
from app.modules.bookings.application.commands import CreateBookingCommand
from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.domain.events import BookingCreated
from app.modules.bookings.ports.authorization import AuthorizationPort
from app.modules.bookings.ports.booking_repository import BookingRepositoryProtocol
from app.modules.bookings.ports.outbox import OutboxPort


class CreateBookingUseCase:
    def __init__(
        self,
        *,
        repository: BookingRepositoryProtocol,
        authorization: AuthorizationPort,
        outbox: OutboxPort,
    ) -> None:
        self._repository = repository
        self._authorization = authorization
        self._outbox = outbox

    async def execute(self, command: CreateBookingCommand, principal: AuthContext) -> BookingDTO:
        # No resource exists yet: the fine-grained check runs on the intent.
        self._authorization.enforce(
            ResourceContext(
                actor_user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                roles=principal.roles,
                action=permission_actions.CREATE,
                resource_type=permission_actions.BOOKING,
                resource_tenant_id=principal.tenant_id,
            )
        )
        booking = await self._repository.create(
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            reference=command.reference,
            resource_id=command.resource_id,
            scheduled_at=command.scheduled_at,
            created_by=principal.user_id,
        )
        await self._outbox.emit(
            BookingCreated(
                booking_id=booking.id,
                tenant_id=booking.tenant_id,
                owner_id=booking.owner_id,
                reference=booking.reference,
            )
        )
        return booking
