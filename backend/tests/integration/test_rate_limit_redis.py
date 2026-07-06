"""RedisRateLimiterBackend against real Redis: atomicity, deny-after-limit,
window reset. (docker compose up -d redis)"""

import asyncio
import uuid

import pytest

from app.infrastructure.cache.redis_client import RedisClient
from app.rate_limiting.backend import RedisRateLimiterBackend
from tests.integration.test_redis_connection import REDIS_TEST_URL

pytestmark = [pytest.mark.integration, pytest.mark.redis]


@pytest.fixture
async def backend():
    client = RedisClient(url=REDIS_TEST_URL)
    await client.connect()
    try:
        yield RedisRateLimiterBackend(client)
    finally:
        await client.disconnect()


def unique_key() -> str:
    return f"app:rl:test:{uuid.uuid4().hex}"


async def test_counts_up_to_limit_then_flags_exhaustion(backend: RedisRateLimiterBackend) -> None:
    key = unique_key()
    for expected_count in range(1, 4):  # limit 3
        result = await backend.check(key, limit=3, window_seconds=30)
        assert result.count == expected_count
        assert result.remaining == 3 - expected_count
    over = await backend.check(key, limit=3, window_seconds=30)
    assert over.count == 4
    assert over.remaining == 0
    assert over.reset_after_seconds >= 1


async def test_concurrent_checks_are_atomic(backend: RedisRateLimiterBackend) -> None:
    """20 concurrent INCRs must produce exactly the counts 1..20 — no lost
    updates, no duplicate counts (the Lua script is one atomic unit)."""
    key = unique_key()
    results = await asyncio.gather(
        *(backend.check(key, limit=10, window_seconds=30) for _ in range(20))
    )
    counts = sorted(result.count for result in results)
    assert counts == list(range(1, 21))
    assert all(result.reset_after_seconds >= 1 for result in results)


async def test_window_resets_after_expiry(backend: RedisRateLimiterBackend) -> None:
    key = unique_key()
    first = await backend.check(key, limit=2, window_seconds=1)
    assert first.count == 1
    await backend.check(key, limit=2, window_seconds=1)
    await asyncio.sleep(1.2)  # let the 1s window lapse
    fresh = await backend.check(key, limit=2, window_seconds=1)
    assert fresh.count == 1  # a brand-new window
    assert fresh.remaining == 1
