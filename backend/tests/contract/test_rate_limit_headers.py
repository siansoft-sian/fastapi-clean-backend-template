"""Contract: a RateLimitExceededError leaves as a 429 envelope carrying
Retry-After and all three X-RateLimit-* headers."""

from typing import Any

import httpx

from app.app import create_app
from app.core.errors.core_errors import RateLimitExceededError
from tests.conftest import assert_envelope


def app_with_limited_route() -> Any:
    app = create_app()

    @app.get("/boom/limited")
    async def limited() -> dict[str, Any]:
        raise RateLimitExceededError(
            details={"rule": "booking.create"}, retry_after=42, limit=30, remaining=0
        )

    return app


async def test_429_envelope_with_all_rate_limit_headers() -> None:
    transport = httpx.ASGITransport(app=app_with_limited_route())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom/limited")

    assert response.status_code == 429
    body = response.json()
    assert_envelope(body)
    assert body["success"] is False
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert body["error"]["details"]["rule"] == "booking.create"
    assert body["meta"]["category"] == "rate_limit"
    assert body["meta"]["request_id"]

    assert response.headers["Retry-After"] == "42"
    assert response.headers["X-RateLimit-Limit"] == "30"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Reset"] == "42"
