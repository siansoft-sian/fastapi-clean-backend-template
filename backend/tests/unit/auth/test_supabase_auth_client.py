"""SupabaseAuthClient: no network at construction, explicit timeouts, typed
DTOs out, provider failures mapped to OAuthExchangeError."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.auth.exceptions import OAuthExchangeError
from app.auth.supabase_auth_client import (
    DEFAULT_TIMEOUT,
    GoTrueTokenSet,
    SupabaseAuthClient,
)

PROJECT_URL = "https://project.supabase.co"


def make_client(handler: object | None = None) -> SupabaseAuthClient:
    transport = httpx.MockTransport(handler) if handler else None  # type: ignore[arg-type]
    http_client = httpx.AsyncClient(transport=transport, timeout=DEFAULT_TIMEOUT)
    return SupabaseAuthClient(
        http_client=http_client,
        project_url=PROJECT_URL,
        anon_key="anon-key-value",
        redirect_uri="https://api.example.com/api/v1/auth/callback",
        provider="google",
    )


def test_default_timeouts_are_explicit_and_bounded() -> None:
    assert DEFAULT_TIMEOUT.connect == 5.0
    assert DEFAULT_TIMEOUT.read == 10.0
    assert DEFAULT_TIMEOUT.write == 5.0
    assert DEFAULT_TIMEOUT.pool == 5.0


def test_construction_needs_no_network_and_builds_authorize_url() -> None:
    client = make_client()
    url = client.build_authorize_url(code_challenge="challenge-abc", state="state-xyz")
    parsed = urlparse(url)
    assert url.startswith(f"{PROJECT_URL}/auth/v1/authorize?")
    query = parse_qs(parsed.query)
    assert query["provider"] == ["google"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge"] == ["challenge-abc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["state-xyz"]
    assert query["redirect_to"] == ["https://api.example.com/api/v1/auth/callback"]


async def test_exchange_code_returns_token_set_and_sends_apikey() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["apikey"] = request.headers.get("apikey")
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "access_token": "at-secret",
                "refresh_token": "rt-secret",
                "expires_in": 3600,
                "token_type": "bearer",
            },
        )

    tokens = await make_client(handler).exchange_code(code="auth-code", code_verifier="verifier")
    assert isinstance(tokens, GoTrueTokenSet)
    assert tokens.access_token.get_secret_value() == "at-secret"
    assert seen["apikey"] == "anon-key-value"
    assert "grant_type=pkce" in str(seen["url"])


async def test_token_values_do_not_leak_in_repr() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "at-secret", "refresh_token": "rt-secret"})

    tokens = await make_client(handler).refresh(refresh_token="old-rt")
    assert "at-secret" not in repr(tokens)
    assert "rt-secret" not in str(tokens)


async def test_gotrue_error_maps_to_oauth_exchange_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "bad code"})

    with pytest.raises(OAuthExchangeError) as exc_info:
        await make_client(handler).exchange_code(code="bad", code_verifier="v")
    assert exc_info.value.http_status == 502
    assert exc_info.value.details["status"] == 400
    assert exc_info.value.details["provider_code"] == "invalid_grant"


async def test_network_failure_maps_to_oauth_exchange_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(OAuthExchangeError) as exc_info:
        await make_client(handler).get_user(access_token="at")
    assert exc_info.value.details["error_type"] == "ConnectError"


async def test_logout_sends_bearer_and_tolerates_204() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(204)

    await make_client(handler).logout(access_token="at-secret")
    assert seen["authorization"] == "Bearer at-secret"
