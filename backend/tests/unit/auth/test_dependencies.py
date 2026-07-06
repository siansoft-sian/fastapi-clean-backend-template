"""Auth dependencies called directly (no HTTP): session -> AuthContext or 401/403."""

import pytest
from starlette.requests import Request

from app.auth.auth_context import AuthContext, get_auth_context
from app.auth.dependencies import (
    get_current_principal,
    require_scope,
    verify_csrf,
)
from app.auth.exceptions import (
    AuthenticationRequiredError,
    CsrfValidationError,
    InvalidSessionError,
    SessionExpiredError,
)
from app.auth.session_repository import FakeSessionRepository, SessionDTO
from app.core.config import Settings
from app.core.errors.core_errors import ForbiddenError


def make_settings() -> Settings:
    return Settings(session_idle_ttl_seconds=600)


def make_request(
    cookies: dict[str, str] | None = None, headers: dict[str, str] | None = None
) -> Request:
    raw_headers: list[tuple[bytes, bytes]] = []
    if cookies:
        cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode()))
    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode(), value.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "query_string": b"",
    }
    return Request(scope)


async def make_session(
    repo: FakeSessionRepository, *, absolute_ttl: int = 3600, idle_ttl: int = 600
) -> SessionDTO:
    return await repo.create(
        user_id="user-1",
        tenant_id="tenant-1",
        access_token="at",
        refresh_token="rt",
        absolute_ttl_seconds=absolute_ttl,
        idle_ttl_seconds=idle_ttl,
        email="user@example.com",
    )


async def test_valid_session_builds_auth_context_and_sets_contextvar() -> None:
    repo = FakeSessionRepository()
    session = await make_session(repo)
    request = make_request(cookies={"sid": session.id})

    principal = await get_current_principal(request, repo, make_settings())

    assert isinstance(principal, AuthContext)
    assert principal.user_id == "user-1"
    assert principal.tenant_id == "tenant-1"
    assert principal.session_id == session.id
    assert principal.email == "user@example.com"
    assert principal.scopes == frozenset()
    assert get_auth_context() == principal


async def test_valid_session_slides_idle_expiry() -> None:
    repo = FakeSessionRepository()
    session = await make_session(repo, idle_ttl=60)
    request = make_request(cookies={"sid": session.id})
    await get_current_principal(request, repo, make_settings())  # idle ttl 600 now
    touched = await repo.get(session_id=session.id)
    assert touched is not None
    assert touched.idle_expires_at > session.idle_expires_at


async def test_missing_cookie_raises_authentication_required() -> None:
    with pytest.raises(AuthenticationRequiredError):
        await get_current_principal(make_request(), FakeSessionRepository(), make_settings())


async def test_unknown_session_raises_invalid_session() -> None:
    request = make_request(cookies={"sid": "11111111-1111-1111-1111-111111111111"})
    with pytest.raises(InvalidSessionError):
        await get_current_principal(request, FakeSessionRepository(), make_settings())


async def test_revoked_session_raises_invalid_session() -> None:
    repo = FakeSessionRepository()
    session = await make_session(repo)
    await repo.revoke(session_id=session.id)
    request = make_request(cookies={"sid": session.id})
    with pytest.raises(InvalidSessionError):
        await get_current_principal(request, repo, make_settings())


async def test_idle_expired_session_raises_session_expired() -> None:
    repo = FakeSessionRepository()
    session = await make_session(repo, idle_ttl=0)  # idle expiry == now
    request = make_request(cookies={"sid": session.id})
    with pytest.raises(SessionExpiredError):
        await get_current_principal(request, repo, make_settings())


async def test_absolute_expired_session_raises_session_expired() -> None:
    repo = FakeSessionRepository()
    session = await make_session(repo, absolute_ttl=0, idle_ttl=0)
    request = make_request(cookies={"sid": session.id})
    with pytest.raises(SessionExpiredError):
        await get_current_principal(request, repo, make_settings())


async def test_verify_csrf_accepts_matching_pair() -> None:
    settings = make_settings()
    request = make_request(cookies={"csrftoken": "match-me"}, headers={"X-CSRF-Token": "match-me"})
    await verify_csrf(request, settings)  # must not raise


@pytest.mark.parametrize(
    ("cookies", "headers"),
    [
        ({}, {}),
        ({"csrftoken": "cookie-only"}, {}),
        ({}, {"X-CSRF-Token": "header-only"}),
        ({"csrftoken": "aaa"}, {"X-CSRF-Token": "bbb"}),
    ],
)
async def test_verify_csrf_rejects_missing_or_mismatched(
    cookies: dict[str, str], headers: dict[str, str]
) -> None:
    with pytest.raises(CsrfValidationError):
        await verify_csrf(make_request(cookies=cookies, headers=headers), make_settings())


async def test_require_scope_fails_closed_without_scopes() -> None:
    principal = AuthContext(user_id="u", tenant_id="t", session_id="s")
    guard = require_scope("tenant:admin")
    with pytest.raises(ForbiddenError):
        await guard(principal)


async def test_require_scope_passes_when_scope_present() -> None:
    principal = AuthContext(
        user_id="u", tenant_id="t", session_id="s", scopes=frozenset({"tenant:admin"})
    )
    guard = require_scope("tenant:admin")
    assert await guard(principal) is principal
