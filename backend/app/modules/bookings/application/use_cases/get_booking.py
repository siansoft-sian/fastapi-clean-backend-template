"""Read one booking. The repository is tenant-scoped, so a cross-tenant id
resolves to None -> 404 (existence never leaks); the fine-grained check then
runs against the loaded resource's real attributes."""

from app.auth.auth_context import AuthContext
from app.authorization import permission_actions
from app.authorization.resource_context import ResourceContext
from app.modules.bookings.application.dto import BookingDTO
from app.modules.bookings.application.queries import GetBookingQuery
from app.modules.bookings.domain.errors import BookingNotFoundError
from app.modules.bookings.ports.authorization import AuthorizationPort
from app.modules.bookings.ports.booking_repository import BookingRepositoryProtocol


class GetBookingUseCase:
    def __init__(
        self, *, repository: BookingRepositoryProtocol, authorization: AuthorizationPort
    ) -> None:
        self._repository = repository
        self._authorization = authorization

    async def execute(self, query: GetBookingQuery, principal: AuthContext) -> BookingDTO:
        booking = await self._repository.get(
            tenant_id=principal.tenant_id, booking_id=query.booking_id
        )
        if booking is None:
            raise BookingNotFoundError()
        self._authorization.enforce(
            ResourceContext(
                actor_user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                roles=principal.roles,
                action=permission_actions.READ,
                resource_type=permission_actions.BOOKING,
                resource_id=booking.id,
                resource_owner_id=booking.owner_id,
                resource_tenant_id=booking.tenant_id,
            )
        )
        return booking
