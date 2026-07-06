"""Approve a booking: load -> authorize (fine) -> domain policy -> persist
(optimistic version) -> emit BookingApproved."""

from app.auth.auth_context import AuthContext
from app.authorization import permission_actions
from app.authorization.resource_context import ResourceContext
from app.modules.bookings.application.commands import ApproveBookingCommand
from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.domain.booking_policy import ensure_can_approve
from app.modules.bookings.domain.errors import BookingNotFoundError
from app.modules.bookings.domain.events import BookingApproved
from app.modules.bookings.ports.authorization import AuthorizationPort
from app.modules.bookings.ports.booking_repository import BookingRepositoryProtocol
from app.modules.bookings.ports.outbox import OutboxPort


class ApproveBookingUseCase:
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

    async def execute(self, command: ApproveBookingCommand, principal: AuthContext) -> BookingDTO:
        booking = await self._repository.get(
            tenant_id=principal.tenant_id, booking_id=command.booking_id
        )
        if booking is None:  # unknown OR cross-tenant: identical 404
            raise BookingNotFoundError()

        self._authorization.enforce(
            ResourceContext(
                actor_user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                roles=principal.roles,
                action=permission_actions.APPROVE,
                resource_type=permission_actions.BOOKING,
                resource_id=booking.id,
                resource_owner_id=booking.owner_id,
                resource_tenant_id=booking.tenant_id,
            )
        )
        ensure_can_approve(booking.to_entity())

        approved = await self._repository.approve(
            tenant_id=principal.tenant_id,
            booking_id=booking.id,
            actor_id=principal.user_id,
            expected_version=booking.version,
        )
        await self._outbox.emit(
            BookingApproved(
                booking_id=approved.id,
                tenant_id=approved.tenant_id,
                approved_by=principal.user_id,
            )
        )
        return approved
