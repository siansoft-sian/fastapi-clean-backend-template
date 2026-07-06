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
