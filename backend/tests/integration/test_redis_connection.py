"""RedisClient against real Redis (docker compose up -d redis)."""

import os

import pytest

from app.infrastructure.cache.redis_client import RedisClient

pytestmark = [pytest.mark.integration, pytest.mark.redis]

REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6379/0")


async def test_connect_ping_roundtrip_disconnect() -> None:
    client = RedisClient(url=REDIS_TEST_URL)
    await client.connect()
    try:
        assert await client.client.ping() is True
        await client.client.set(b"app:test:probe", b"1", ex=5)
        assert await client.client.get(b"app:test:probe") == b"1"
    finally:
        await client.disconnect()
    assert client.is_connected is False


async def test_lifespan_with_redis_builds_limiter_and_ready_reports_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from app.app import create_app
    from app.core.config import get_settings

    monkeypatch.setenv("STARTUP_CONNECT_REDIS", "true")
    monkeypatch.setenv("REDIS_URL", REDIS_TEST_URL)
    get_settings.cache_clear()

    app = create_app()
    async with app.router.lifespan_context(app):
        assert app.state.rate_limiter is not None
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["components"]["redis"] == "ok"
        assert body["data"]["status"] == "ok"
    assert app.state.rate_limiter is None  # torn down with the container
