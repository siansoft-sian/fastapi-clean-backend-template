"""Authorization port — keeps use cases decoupled from the concrete M4
AuthorizationService (and transitively from Casbin). ResourceContext itself
is a pure dataclass and safe to share across the boundary.
"""

from typing import Protocol

from app.authorization.resource_context import ResourceContext


class AuthorizationPort(Protocol):
    def enforce(self, ctx: ResourceContext) -> None:
        """Raise ForbiddenError on denial; cross-tenant carries
        details.reason == "cross_tenant" for the 404 mapping."""
        ...
