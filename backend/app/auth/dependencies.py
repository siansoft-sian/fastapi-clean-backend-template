"""Per-route auth dependencies — the BFF enforcement point.

Auth is NEVER middleware in this template: routes opt in with Depends().
Chain: opaque session cookie -> session repository -> validity checks ->
idle-slide touch -> AuthContext (contextvar + structlog binding).

CSRF (double-submit) is its own dependency, applied to state-changing routes.
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import Depends, Request

from app.api.deps import SettingsDep
from app.auth import csrf
from app.auth.auth_context import AuthContext, auth_context_var
from app.auth.exceptions import (
    AuthenticationRequiredError,
    CsrfValidationError,
    InvalidSessionError,
    SessionExpiredError,
)
from app.auth.session_repository import SessionRepositoryProtocol
from app.bootstrap.factories import provide_session_repository
from app.core.errors.core_errors import ForbiddenError

SessionRepositoryDep = Annotated[SessionRepositoryProtocol, Depends(provide_session_repository)]


async def get_current_principal(
    request: Request,
    session_repository: SessionRepositoryDep,
    settings: SettingsDep,
) -> AuthContext:
    """Resolve the session cookie into an AuthContext or raise a 401."""
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise AuthenticationRequiredError()

    session = await session_repository.get(session_id=session_id)
    if session is None or session.revoked_at is not None:
        raise InvalidSessionError()

    now = datetime.now(UTC)
    if now >= session.absolute_expires_at or now >= session.idle_expires_at:
        raise SessionExpiredError()

    await session_repository.touch(
        session_id=session.id, idle_ttl_seconds=settings.session_idle_ttl_seconds
    )

    principal = AuthContext(
        user_id=session.user_id,
        tenant_id=session.tenant_id,
        session_id=session.id,
        email=session.email,
        scopes=frozenset(),  # populated by the M4 authorization milestone
    )
    auth_context_var.set(principal)
    # Bind identity (never the session id or tokens) for the request's log lines.
    structlog.contextvars.bind_contextvars(user_id=principal.user_id, tenant_id=principal.tenant_id)
    return principal


PrincipalDep = Annotated[AuthContext, Depends(get_current_principal)]


async def require_authenticated(principal: PrincipalDep) -> AuthContext:
    """The guard routes list in Depends(); returns the principal."""
    return principal


async def verify_csrf(request: Request, settings: SettingsDep) -> None:
    """Double-submit check for state-changing routes (a dependency, not middleware)."""
    header_value = request.headers.get(settings.csrf_header_name)
    cookie_value = request.cookies.get(settings.csrf_cookie_name)
    if not csrf.verify_csrf(header_value, cookie_value):
        raise CsrfValidationError()


def require_scope(scope: str) -> Callable[[AuthContext], Coroutine[Any, Any, AuthContext]]:
    """Guard factory: `Depends(require_scope(SCOPE_TENANT_ADMIN))`.

    Scope population arrives in M4; until then, principals carry no scopes and
    this guard denies (fail closed).
    """

    async def _check_scope(principal: PrincipalDep) -> AuthContext:
        if scope not in principal.scopes:
            raise ForbiddenError(details={"missing_scope": scope})
        return principal

    return _check_scope
