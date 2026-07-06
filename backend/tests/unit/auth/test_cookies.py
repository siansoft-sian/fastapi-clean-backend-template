"""Cookie attribute contract: HttpOnly/Secure/SameSite exactly as the BFF requires."""

from starlette.responses import Response

from app.auth.cookies import (
    clear_pkce_state_cookie,
    clear_session_cookie,
    set_csrf_cookie,
    set_pkce_state_cookie,
    set_session_cookie,
)
from app.core.config import Settings


def make_settings() -> Settings:
    return Settings(
        session_absolute_ttl_seconds=1000,
        pkce_state_ttl_seconds=60,
    )


def cookie_header(response: Response, name: str) -> str:
    for raw in response.headers.getlist("set-cookie"):
        if raw.startswith(f"{name}="):
            return raw
    raise AssertionError(f"no set-cookie for {name}: {response.headers.getlist('set-cookie')}")


def test_session_cookie_is_httponly_secure_lax() -> None:
    response = Response()
    set_session_cookie(response, "opaque-session-id", settings=make_settings())
    raw = cookie_header(response, "sid").lower()
    assert "opaque-session-id" in raw
    assert "httponly" in raw
    assert "secure" in raw
    assert "samesite=lax" in raw
    assert "path=/" in raw
    assert "max-age=1000" in raw


def test_csrf_cookie_is_readable_but_secure() -> None:
    response = Response()
    set_csrf_cookie(response, "csrf-token-value", settings=make_settings())
    raw = cookie_header(response, "csrftoken").lower()
    assert "httponly" not in raw  # double-submit: frontend must read it
    assert "secure" in raw
    assert "samesite=lax" in raw
    assert "path=/" in raw


def test_pkce_cookie_is_httponly_and_short_lived() -> None:
    response = Response()
    set_pkce_state_cookie(response, "packed-payload", settings=make_settings())
    raw = cookie_header(response, "auth_state").lower()
    assert "httponly" in raw
    assert "secure" in raw
    assert "max-age=60" in raw


def test_clear_helpers_expire_the_cookies() -> None:
    response = Response()
    settings = make_settings()
    clear_session_cookie(response, settings=settings)
    clear_pkce_state_cookie(response, settings=settings)
    sid_raw = cookie_header(response, "sid").lower()
    pkce_raw = cookie_header(response, "auth_state").lower()
    for raw in (sid_raw, pkce_raw):
        assert "max-age=0" in raw or "expires=" in raw
