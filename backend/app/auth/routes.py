"""BFF auth routes — thin delivery layer.

All GoTrue traffic is server-to-server; the browser receives only redirects
and cookies (opaque session id + readable CSRF token). Cookies are set
exclusively through `cookies.py`. No token appears in any response body,
cookie, or log line.
"""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import SettingsDep
from app.auth import pkce
from app.auth.auth_context import AuthContext
from app.auth.cookies import (
    clear_csrf_cookie,
    clear_pkce_state_cookie,
    clear_session_cookie,
    set_csrf_cookie,
    set_pkce_state_cookie,
    set_session_cookie,
)
from app.auth.csrf import generate_csrf_token
from app.auth.dependencies import (
    SessionRepositoryDep,
    require_authenticated,
    verify_csrf,
)
from app.auth.exceptions import CsrfValidationError, InvalidSessionError, OAuthExchangeError
from app.auth.identity_mapper import IdentityMapperProtocol
from app.auth.supabase_auth_client import SupabaseAuthClient
from app.bootstrap.factories import provide_identity_mapper, provide_supabase_auth_client
from app.core.responses import api_success

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

GoTrueClientDep = Annotated[SupabaseAuthClient, Depends(provide_supabase_auth_client)]
IdentityMapperDep = Annotated[IdentityMapperProtocol, Depends(provide_identity_mapper)]
AuthenticatedDep = Annotated[AuthContext, Depends(require_authenticated)]


@router.get("/login")
async def login(client: GoTrueClientDep, settings: SettingsDep) -> RedirectResponse:
    """Start the PKCE flow: 302 to the GoTrue authorize URL.

    The verifier+state survive the round-trip in a short-lived HttpOnly cookie
    (there is no session yet at this point).
    """
    verifier = pkce.generate_code_verifier()
    state = pkce.generate_state()
    authorize_url = client.build_authorize_url(
        code_challenge=pkce.code_challenge_s256(verifier), state=state
    )
    response = RedirectResponse(authorize_url, status_code=302)
    set_pkce_state_cookie(
        response, pkce.pack_state_payload(state=state, verifier=verifier), settings=settings
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str,
    state: str,
    client: GoTrueClientDep,
    identity_mapper: IdentityMapperDep,
    session_repository: SessionRepositoryDep,
    settings: SettingsDep,
) -> RedirectResponse:
    """Finish the PKCE flow: exchange the code, map identity, mint the session."""
    payload = pkce.unpack_state_payload(request.cookies.get(settings.pkce_state_cookie_name))
    if payload is None:
        raise CsrfValidationError("Login state cookie missing or corrupt")
    expected_state, verifier = payload
    if not pkce.states_match(expected_state, state):
        raise CsrfValidationError("OAuth state mismatch")

    tokens = await client.exchange_code(code=code, code_verifier=verifier)
    user = await client.get_user(access_token=tokens.access_token.get_secret_value())
    identity = await identity_mapper.map_identity(provider_subject=user.id, email=user.email)
    session = await session_repository.create(
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        access_token=tokens.access_token.get_secret_value(),
        refresh_token=tokens.refresh_token.get_secret_value(),
        absolute_ttl_seconds=settings.session_absolute_ttl_seconds,
        idle_ttl_seconds=settings.session_idle_ttl_seconds,
        email=user.email,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )

    response = RedirectResponse(settings.frontend_post_login_url, status_code=302)
    set_session_cookie(response, session.id, settings=settings)
    set_csrf_cookie(response, generate_csrf_token(), settings=settings)
    clear_pkce_state_cookie(response, settings=settings)
    return response


@router.post("/refresh", dependencies=[Depends(verify_csrf)])
async def refresh(
    principal: AuthenticatedDep,
    client: GoTrueClientDep,
    session_repository: SessionRepositoryDep,
    settings: SettingsDep,
) -> JSONResponse:
    """Refresh the GoTrue tokens AND rotate the session id (fixation defense)."""
    session = await session_repository.get(session_id=principal.session_id)
    if session is None or session.revoked_at is not None:
        raise InvalidSessionError()

    tokens = await client.refresh(refresh_token=session.gotrue_refresh_token.get_secret_value())
    rotated = await session_repository.rotate(
        session_id=session.id,
        access_token=tokens.access_token.get_secret_value(),
        refresh_token=tokens.refresh_token.get_secret_value(),
        idle_ttl_seconds=settings.session_idle_ttl_seconds,
    )
    if rotated is None:
        raise InvalidSessionError()

    response = JSONResponse(api_success({"rotated": True}))
    set_session_cookie(response, rotated.id, settings=settings)
    set_csrf_cookie(response, generate_csrf_token(), settings=settings)
    return response


@router.post("/logout", dependencies=[Depends(verify_csrf)])
async def logout(
    principal: AuthenticatedDep,
    client: GoTrueClientDep,
    session_repository: SessionRepositoryDep,
    settings: SettingsDep,
) -> JSONResponse:
    """Revoke server-side (GoTrue best-effort, local always) and clear cookies."""
    session = await session_repository.get(session_id=principal.session_id)
    if session is not None and session.revoked_at is None:
        try:
            await client.logout(access_token=session.gotrue_access_token.get_secret_value())
        except OAuthExchangeError:
            # Best effort: provider downtime must never keep the user logged
            # in locally. The local revoke below always happens.
            logger.warning("gotrue_logout_failed_revoking_locally")

    await session_repository.revoke(session_id=principal.session_id)

    response = JSONResponse(api_success({"logged_out": True}))
    clear_session_cookie(response, settings=settings)
    clear_csrf_cookie(response, settings=settings)
    return response


@router.get("/me")
async def me(principal: AuthenticatedDep) -> dict[str, Any]:
    """The current principal — safe fields only, never tokens."""
    return api_success(
        {
            "user_id": principal.user_id,
            "tenant_id": principal.tenant_id,
            "email": principal.email,
            "scopes": sorted(principal.scopes),
        }
    )
