"""Per-route auth dependencies — the BFF enforcement point.

Auth is NEVER middleware in this template: routes opt in with Depends().
Chain: opaque session cookie -> session repository (the DATABASE decides
validity and raises the typed 401s) -> idle-slide touch -> AuthContext
(contextvar + structlog binding).

CSRF (double-submit) is its own dependency, applied to state-changing routes.
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import structlog
from fastapi import Depends, Request

from app.api.deps import SettingsDep
from app.auth import csrf
from app.auth.auth_context import AuthContext, auth_context_var
from app.auth.exceptions import (
    AuthenticationRequiredError,
    CsrfValidationError,
)
from app.auth.session_repository import SessionRepositoryProtocol
from app.authorization.authorization_service import AuthorizationService
from app.bootstrap.factories import (
    provide_authorization_service,
    provide_session_repository,
)
from app.core.errors.core_errors import ForbiddenError

SessionRepositoryDep = Annotated[SessionRepositoryProtocol, Depends(provide_session_repository)]
AuthorizationServiceDep = Annotated[AuthorizationService, Depends(provide_authorization_service)]


async def get_current_principal(
    request: Request,
    session_repository: SessionRepositoryDep,
    settings: SettingsDep,
) -> AuthContext:
    """Resolve the session cookie into an AuthContext or raise a 401.

    `get` raises InvalidSessionError/SessionExpiredError itself (validity is
    the database's decision); only the missing-cookie case is decided here.
    """
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise AuthenticationRequiredError()

    session = await session_repository.get(session_token=session_token)
    await session_repository.touch(
        session_token=session_token, idle_ttl_seconds=settings.session_idle_ttl_seconds
    )

    # TODO(M3-reconcile): resolve roles via the DB `get_user_roles(user_id,
    # tenant_id)` at session creation, cache them (and
    # AuthorizationService.compute_scopes(roles, tenant_id)) on the session
    # record, refresh on /auth/refresh. Until the identity/RBAC milestone
    # ships that function, principals resolved from sessions carry empty
    # roles/scopes; tests and the _authz_demo inject AuthContexts directly.
    principal = AuthContext(
        user_id=session.user_id,
        tenant_id=session.tenant_id,
        session_id=session.session_internal_id,  # internal id — safe for audit/logs
        email=session.email,
        roles=frozenset(),
        scopes=frozenset(),
    )
    auth_context_var.set(principal)
    # Bind identity (never the cookie token) for the request's log lines.
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


def require_scope(
    scope: str,
) -> Callable[[AuthContext, AuthorizationService], Coroutine[Any, Any, AuthContext]]:
    """Layer-1 route gate: `Depends(require_scope(scopes.BOOKING_APPROVE))`.

    A coarse pre-filter over the principal's cached scopes — fails closed for
    principals without scopes. NEVER sufficient for ownership/assignment/
    tenant decisions: those go through AuthorizationService.enforce() in the
    use case (Layer 2, authoritative).
    """

    async def _check_scope(
        principal: PrincipalDep, authorization: AuthorizationServiceDep
    ) -> AuthContext:
        if not authorization.has_scope(principal, scope):
            raise ForbiddenError(details={"missing_scope": scope})
        return principal

    return _check_scope
