"""Cookie issuance — the ONLY place auth cookie attributes are set.

Routes never call `response.set_cookie` directly; the security attributes
(HttpOnly/Secure/SameSite/Path/Max-Age) live here so they cannot drift.

- session cookie: HttpOnly (JS must never read the opaque session id)
- CSRF cookie: NOT HttpOnly by design — the frontend reads it and echoes it
  back as a header (double-submit)
- PKCE state cookie: HttpOnly, short-lived, scoped to the callback exchange
"""

from starlette.responses import Response

from app.core.config import Settings


def set_session_cookie(response: Response, session_id: str, *, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=settings.session_absolute_ttl_seconds,
        path="/",
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def clear_session_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def set_csrf_cookie(response: Response, token: str, *, settings: Settings) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.session_absolute_ttl_seconds,
        path="/",
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=False,  # double-submit: the frontend must be able to read it
        samesite=settings.session_cookie_samesite,
    )


def clear_csrf_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite=settings.session_cookie_samesite,
    )


def set_pkce_state_cookie(response: Response, value: str, *, settings: Settings) -> None:
    response.set_cookie(
        key=settings.pkce_state_cookie_name,
        value=value,
        max_age=settings.pkce_state_ttl_seconds,
        path="/",
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def clear_pkce_state_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.pkce_state_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
