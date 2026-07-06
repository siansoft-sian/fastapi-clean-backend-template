"""BFF auth flow end-to-end with GoTrue mocked and fakes injected on app.state.

Verifies cookie discipline (HttpOnly session id, readable CSRF, cleared PKCE),
401/403 enforcement, session rotation and revocation — and the core invariant:
NO GoTrue token ever appears in any response body or cookie.
"""

import uuid

import httpx
from fastapi import FastAPI

from app.app import create_app
from app.auth import pkce
from app.auth.identity_mapper import FakeIdentityMapper
from app.auth.session_repository import FakeSessionRepository
from app.auth.supabase_auth_client import GoTrueTokenSet, GoTrueUser

ACCESS_SECRET = "gotrue-access-token-SECRET"
REFRESH_SECRET = "gotrue-refresh-token-SECRET"
ROTATED_ACCESS_SECRET = "rotated-access-SECRET"
ROTATED_REFRESH_SECRET = "rotated-refresh-SECRET"
ALL_TOKEN_MARKERS = (ACCESS_SECRET, REFRESH_SECRET, ROTATED_ACCESS_SECRET, ROTATED_REFRESH_SECRET)

GOTRUE_SUBJECT = "gotrue-sub-1"


class FakeGoTrueClient:
    """Same surface as SupabaseAuthClient; no network."""

    def __init__(self) -> None:
        self.exchanged: list[tuple[str, str]] = []
        self.refreshed_with: list[str] = []
        self.logged_out_tokens: list[str] = []

    def build_authorize_url(self, *, code_challenge: str, state: str) -> str:
        return (
            "https://project.supabase.co/auth/v1/authorize?provider=google"
            f"&code_challenge={code_challenge}&code_challenge_method=S256&state={state}"
        )

    async def exchange_code(self, *, code: str, code_verifier: str) -> GoTrueTokenSet:
        self.exchanged.append((code, code_verifier))
        return GoTrueTokenSet(access_token=ACCESS_SECRET, refresh_token=REFRESH_SECRET)

    async def refresh(self, *, refresh_token: str) -> GoTrueTokenSet:
        self.refreshed_with.append(refresh_token)
        return GoTrueTokenSet(
            access_token=ROTATED_ACCESS_SECRET, refresh_token=ROTATED_REFRESH_SECRET
        )

    async def logout(self, *, access_token: str) -> None:
        self.logged_out_tokens.append(access_token)

    async def get_user(self, *, access_token: str) -> GoTrueUser:
        return GoTrueUser(id=GOTRUE_SUBJECT, email="user@example.com")


def build_auth_app() -> tuple[FastAPI, FakeGoTrueClient, FakeSessionRepository]:
    app = create_app()
    gotrue = FakeGoTrueClient()
    sessions = FakeSessionRepository()
    mapper = FakeIdentityMapper()
    mapper.add_mapping(GOTRUE_SUBJECT, user_id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()))
    app.state.supabase_auth_client = gotrue
    app.state.session_repository = sessions
    app.state.identity_mapper = mapper
    return app, gotrue, sessions


def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def raw_cookie(response: httpx.Response, name: str) -> str | None:
    """The full Set-Cookie header line for `name`, or None."""
    for raw in response.headers.get_list("set-cookie"):
        if raw.startswith(f"{name}="):
            return raw
    return None


def cookie_value(response: httpx.Response, name: str) -> str | None:
    raw = raw_cookie(response, name)
    if raw is None:
        return None
    return raw.split(";")[0].split("=", 1)[1].strip('"')


def cookie_header(pairs: dict[str, str]) -> dict[str, str]:
    """Explicit Cookie header (avoids httpx jar semantics with Secure cookies)."""
    return {"Cookie": "; ".join(f"{name}={value}" for name, value in pairs.items())}


def assert_no_token_leak(response: httpx.Response) -> None:
    blob = response.text + " | ".join(response.headers.get_list("set-cookie"))
    for marker in ALL_TOKEN_MARKERS:
        assert marker not in blob, f"token marker {marker!r} leaked to the client"


async def do_login_flow(
    client: httpx.AsyncClient,
) -> tuple[str, str, list[httpx.Response]]:
    """Run login -> callback; return (session_id, csrf_token, responses)."""
    login = await client.get("/api/v1/auth/login")
    assert login.status_code == 302
    packed = cookie_value(login, "auth_state")
    assert packed is not None
    payload = pkce.unpack_state_payload(packed)
    assert payload is not None
    state, _verifier = payload

    callback = await client.get(
        "/api/v1/auth/callback",
        params={"code": "fake-auth-code", "state": state},
        headers=cookie_header({"auth_state": packed}),
    )
    assert callback.status_code == 302, callback.text
    session_id = cookie_value(callback, "sid")
    csrf_token = cookie_value(callback, "csrftoken")
    assert session_id and csrf_token
    return session_id, csrf_token, [login, callback]


async def test_login_redirects_to_authorize_url_and_sets_pkce_cookie() -> None:
    app, _, _ = build_auth_app()
    async with make_client(app) as client:
        response = await client.get("/api/v1/auth/login")
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://project.supabase.co/auth/v1/authorize?")
    assert "code_challenge=" in location and "state=" in location
    pkce_cookie = raw_cookie(response, "auth_state")
    assert pkce_cookie is not None and "httponly" in pkce_cookie.lower()
    assert_no_token_leak(response)


async def test_callback_issues_session_and_csrf_cookies_and_redirects() -> None:
    app, gotrue, sessions = build_auth_app()
    async with make_client(app) as client:
        session_id, _csrf, responses = await do_login_flow(client)
        callback = responses[1]

    assert callback.headers["location"] == "http://localhost:3000/"
    sid_raw = raw_cookie(callback, "sid")
    csrf_raw = raw_cookie(callback, "csrftoken")
    pkce_raw = raw_cookie(callback, "auth_state")
    assert sid_raw is not None and "httponly" in sid_raw.lower() and "secure" in sid_raw.lower()
    assert csrf_raw is not None and "httponly" not in csrf_raw.lower()
    assert pkce_raw is not None and "max-age=0" in pkce_raw.lower()  # cleared

    # The PKCE verifier really reached the exchange, and a session exists.
    assert gotrue.exchanged and gotrue.exchanged[0][0] == "fake-auth-code"
    stored = await sessions.get(session_id=session_id)
    assert stored is not None and stored.email == "user@example.com"
    for response in responses:
        assert_no_token_leak(response)


async def test_callback_rejects_state_mismatch_and_missing_cookie() -> None:
    app, _, _ = build_auth_app()
    async with make_client(app) as client:
        login = await client.get("/api/v1/auth/login")
        packed = cookie_value(login, "auth_state")
        assert packed is not None

        mismatched = await client.get(
            "/api/v1/auth/callback",
            params={"code": "x", "state": "attacker-controlled"},
            headers=cookie_header({"auth_state": packed}),
        )
        missing = await client.get("/api/v1/auth/callback", params={"code": "x", "state": "any"})
    for response in (mismatched, missing):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


async def test_me_requires_session_cookie() -> None:
    app, _, _ = build_auth_app()
    async with make_client(app) as client:
        anonymous = await client.get("/api/v1/auth/me")
        garbage = await client.get(
            "/api/v1/auth/me", headers=cookie_header({"sid": str(uuid.uuid4())})
        )
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert garbage.status_code == 401
    assert garbage.json()["error"]["code"] == "INVALID_SESSION"


async def test_me_returns_principal_with_valid_session() -> None:
    app, _, _ = build_auth_app()
    async with make_client(app) as client:
        session_id, _csrf, _ = await do_login_flow(client)
        response = await client.get("/api/v1/auth/me", headers=cookie_header({"sid": session_id}))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "user@example.com"
    assert data["user_id"] and data["tenant_id"]
    assert data["scopes"] == []
    assert_no_token_leak(response)


async def test_refresh_rejects_missing_or_mismatched_csrf() -> None:
    app, _, _ = build_auth_app()
    async with make_client(app) as client:
        session_id, csrf_token, _ = await do_login_flow(client)
        no_header = await client.post(
            "/api/v1/auth/refresh",
            headers=cookie_header({"sid": session_id, "csrftoken": csrf_token}),
        )
        mismatched = await client.post(
            "/api/v1/auth/refresh",
            headers={
                **cookie_header({"sid": session_id, "csrftoken": csrf_token}),
                "X-CSRF-Token": "wrong-token",
            },
        )
    for response in (no_header, mismatched):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


async def test_refresh_rotates_session_id_and_tokens() -> None:
    app, gotrue, sessions = build_auth_app()
    async with make_client(app) as client:
        session_id, csrf_token, _ = await do_login_flow(client)
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                **cookie_header({"sid": session_id, "csrftoken": csrf_token}),
                "X-CSRF-Token": csrf_token,
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"rotated": True}

    new_session_id = cookie_value(response, "sid")
    assert new_session_id and new_session_id != session_id  # fixation defense
    assert cookie_value(response, "csrftoken")  # fresh CSRF token issued

    old = await sessions.get(session_id=session_id)
    assert old is not None and old.revoked_at is not None
    new = await sessions.get(session_id=new_session_id)
    assert new is not None and new.revoked_at is None
    assert new.gotrue_access_token.get_secret_value() == ROTATED_ACCESS_SECRET
    assert gotrue.refreshed_with == [REFRESH_SECRET]
    assert_no_token_leak(response)


async def test_logout_revokes_session_and_clears_cookies() -> None:
    app, gotrue, sessions = build_auth_app()
    async with make_client(app) as client:
        session_id, csrf_token, _ = await do_login_flow(client)
        response = await client.post(
            "/api/v1/auth/logout",
            headers={
                **cookie_header({"sid": session_id, "csrftoken": csrf_token}),
                "X-CSRF-Token": csrf_token,
            },
        )
        after = await client.get("/api/v1/auth/me", headers=cookie_header({"sid": session_id}))

    assert response.status_code == 200
    sid_raw = raw_cookie(response, "sid")
    csrf_raw = raw_cookie(response, "csrftoken")
    assert sid_raw is not None and "max-age=0" in sid_raw.lower()
    assert csrf_raw is not None and "max-age=0" in csrf_raw.lower()

    revoked = await sessions.get(session_id=session_id)
    assert revoked is not None and revoked.revoked_at is not None
    assert gotrue.logged_out_tokens == [ACCESS_SECRET]  # server-side GoTrue logout
    assert after.status_code == 401  # the revoked session no longer authenticates
    assert_no_token_leak(response)


async def test_mutating_auth_routes_require_authentication() -> None:
    app, _, _ = build_auth_app()
    async with make_client(app) as client:
        # CSRF passes (header matches cookie) but there is no session.
        response = await client.post(
            "/api/v1/auth/logout",
            headers={**cookie_header({"csrftoken": "t"}), "X-CSRF-Token": "t"},
        )
    assert response.status_code == 401
