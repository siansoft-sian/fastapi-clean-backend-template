"""Async Redis client lifecycle — mirrors the M2 DatabasePool pattern.

No I/O at import or construction time: the connection pool is created and
pinged only when `connect()` is awaited, which `container.startup()` does iff
`settings.startup_connect_redis` is true. No FastAPI imports here.
"""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import Settings
from app.core.errors.core_errors import ExternalServiceError

_DEFAULT_TIMEOUT_SECONDS = 5.0


class RedisClient:
    """Owns the redis.asyncio client. Constructing this object performs no I/O."""

    def __init__(self, *, url: str) -> None:
        self._url = url
        self._client: redis.Redis | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisClient:
        if settings.redis_url is None:
            raise ExternalServiceError(
                "REDIS_URL is not set but a Redis client was requested",
                details={"service": "redis"},
            )
        return cls(url=settings.redis_url.get_secret_value())

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    @property
    def client(self) -> redis.Redis:
        """The live client. Raises if `connect()` has not been awaited yet."""
        if self._client is None:
            raise ExternalServiceError(
                "Redis client is not connected; container.startup() must run "
                "with STARTUP_CONNECT_REDIS=true before Redis is used",
                details={"service": "redis"},
            )
        return self._client

    async def connect(self) -> None:
        """Create the pool and ping once (fail fast). Idempotent."""
        if self._client is not None:
            return
        client = redis.from_url(
            self._url,
            socket_connect_timeout=_DEFAULT_TIMEOUT_SECONDS,
            socket_timeout=_DEFAULT_TIMEOUT_SECONDS,
            decode_responses=False,
        )
        await client.ping()
        self._client = client

    async def disconnect(self) -> None:
        """Close the pool and forget it. Safe to call when never connected."""
        if self._client is None:
            return
        await self._client.aclose()
        self._client = None
