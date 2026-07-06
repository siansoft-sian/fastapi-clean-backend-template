"""Adapts the M4 AuthorizationService to the module's AuthorizationPort.

Trivial by design: the port exists so use cases never import the concrete
service (or, transitively, Casbin).
"""

from typing import TYPE_CHECKING

from app.authorization.authorization_service import AuthorizationService
from app.authorization.resource_context import ResourceContext

if TYPE_CHECKING:
    from app.modules.bookings.ports.authorization import AuthorizationPort


class AuthorizationAdapter:
    def __init__(self, service: AuthorizationService) -> None:
        self._service = service

    def enforce(self, ctx: ResourceContext) -> None:
        self._service.enforce(ctx)


if TYPE_CHECKING:
    _proof: AuthorizationPort = AuthorizationAdapter(None)  # type: ignore[arg-type]
