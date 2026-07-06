"""M5 hybrid rate limiting through real HTTP:

- the per-scope dependency (post-auth, per-USER) on the demo route
- the global IP-ceiling middleware (pre-auth) incl. health exemption
Both use the fake backend; rules are shrunk via monkeypatch for speed.
"""

import pytest

from app.rate_limiting.backend import FakeRateLimiterBackend
from app.rate_limiting.limiter import RateLimiter
from app.rate_limiting.rules import RULES, RateLimitRule
from tests.authz.conftest import build_app, make_client, make_principal

LIMITED_URL = "/api/v1/_authz-demo/limited"


def shrink_rule(monkeypatch: pytest.MonkeyPatch, name: str, *, limit: int) -> None:
    original = RULES[name]
    monkeypatch.setitem(
        RULES,
        name,
        RateLimitRule(
            name=name,
            limit=limit,
            window_seconds=original.window_seconds,
            scope=original.scope,
            fail_open=original.fail_open,
        ),
    )


def app_with_fake_limiter(principal=None):  # type: ignore[no-untyped-def]
    app = build_app(principal or make_principal())
    app.state.rate_limiter = RateLimiter(FakeRateLimiterBackend())
    return app


async def test_dependency_allows_up_to_limit_then_429_with_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shrink_rule(monkeypatch, "booking.create", limit=2)
    async with make_client(app_with_fake_limiter()) as client:
        for _ in range(2):
            assert (await client.post(LIMITED_URL)).status_code == 200
        blocked = await client.post(LIMITED_URL)

    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert body["error"]["details"]["rule"] == "booking.create"
    assert body["meta"]["request_id"]
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.headers["X-RateLimit-Limit"] == "2"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    assert int(blocked.headers["X-RateLimit-Reset"]) >= 1


async def test_dependency_keys_per_user(monkeypatch: pytest.MonkeyPatch) -> None:
    shrink_rule(monkeypatch, "booking.create", limit=1)
    limiter = RateLimiter(FakeRateLimiterBackend())

    app_a = build_app(make_principal(user_id="user-a"))
    app_a.state.rate_limiter = limiter
    async with make_client(app_a) as client:
        assert (await client.post(LIMITED_URL)).status_code == 200
        assert (await client.post(LIMITED_URL)).status_code == 429

    # A different user shares the limiter but not the bucket.
    app_b = build_app(make_principal(user_id="user-b"))
    app_b.state.rate_limiter = limiter
    async with make_client(app_b) as client:
        assert (await client.post(LIMITED_URL)).status_code == 200


async def test_dependency_pass_through_without_limiter() -> None:
    async with make_client(build_app(make_principal())) as client:  # no limiter injected
        for _ in range(5):
            assert (await client.post(LIMITED_URL)).status_code == 200


async def test_dependency_pass_through_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    shrink_rule(monkeypatch, "booking.create", limit=1)
    async with make_client(app_with_fake_limiter()) as client:
        for _ in range(3):
            assert (await client.post(LIMITED_URL)).status_code == 200


# --- global IP ceiling (middleware, pre-auth) ---


async def test_middleware_ip_ceiling_denies_and_exempts_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shrink_rule(monkeypatch, "global.ip", limit=3)
    async with make_client(app_with_fake_limiter()) as client:
        for _ in range(3):
            assert (await client.get("/api/v1/auth/me")).status_code in (200, 401)
        blocked = await client.get("/api/v1/auth/me")
        assert blocked.status_code == 429
        assert blocked.json()["error"]["details"]["rule"] == "global.ip"
        assert "Retry-After" in blocked.headers
        assert blocked.headers["X-RateLimit-Limit"] == "3"
        # Health probes must never be limited — even with the bucket exhausted.
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/api/v1/health/ready")).status_code == 200
