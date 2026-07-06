"""Request-scoped authenticated principal. Pure: no FastAPI.

Set by `get_current_principal` (dependency chain, never middleware) via a
ContextVar — each request runs in its own task, so the value cannot leak
across requests; like the request-id var it is set-per-request, not reset.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    tenant_id: str
    session_id: str
    email: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)


auth_context_var: ContextVar[AuthContext | None] = ContextVar("auth_context", default=None)


def get_auth_context() -> AuthContext | None:
    """Current principal, or None outside an authenticated request."""
    return auth_context_var.get()
