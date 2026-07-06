"""RedisClient: strictly lazy — no socket until connect() is awaited."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.core.errors.core_errors import ExternalServiceError
from app.infrastructure.cache.cache_keys import NAMESPACE_RATE_LIMIT, cache_key
from app.infrastructure.cache.redis_client import RedisClient

URL = "redis://cache.example:6379/0"


async def test_construction_opens_no_socket() -> None:
    with patch("app.infrastructure.cache.redis_client.redis.from_url") as from_url:
        client = RedisClient(url=URL)
        assert client.is_connected is False
        from_url.assert_not_called()


async def test_connect_builds_pool_pings_and_is_idempotent() -> None:
    fake = AsyncMock()
    with patch(
        "app.infrastructure.cache.redis_client.redis.from_url", return_value=fake
    ) as from_url:
        client = RedisClient(url=URL)
        await client.connect()
        await client.connect()
    from_url.assert_called_once()
    fake.ping.assert_awaited_once()  # fail-fast ping on startup
    assert client.is_connected is True


async def test_disconnect_closes_and_forgets() -> None:
    fake = AsyncMock()
    with patch("app.infrastructure.cache.redis_client.redis.from_url", return_value=fake):
        client = RedisClient(url=URL)
        await client.connect()
        await client.disconnect()
    fake.aclose.assert_awaited_once()
    assert client.is_connected is False
    await client.disconnect()  # never-connected/second call is safe


def test_client_property_raises_before_connect() -> None:
    with pytest.raises(ExternalServiceError):
        _ = RedisClient(url=URL).client


def test_from_settings_requires_url() -> None:
    with pytest.raises(ExternalServiceError):
        RedisClient.from_settings(Settings(redis_url=None))


def test_cache_keys_are_namespaced_and_separator_safe() -> None:
    key = cache_key(NAMESPACE_RATE_LIMIT, "rule", "scope", "id")
    assert key == "app:rl:rule:scope:id"
    # parts containing the separator cannot forge extra segments
    assert cache_key("ns", "a:b") == "app:ns:a_b"
