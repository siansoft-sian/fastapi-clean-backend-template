"""Rate-limiter backends: the Protocol, the atomic Redis implementation, and
an in-memory fake for the fast gate. Pure modules — no FastAPI.

The Redis check is a FIXED-WINDOW counter executed as ONE Lua script: INCR,
EXPIRE-on-first-hit, and a TTL repair for keys that somehow lost their expiry,
all in a single atomic round trip. There is deliberately no INCR-then-EXPIRE
from Python — that either races (two firsts) or leaks an immortal key.
Sliding-window counters or a token bucket are drop-in upgrades behind the
same Protocol if fixed-window burst behavior ever matters.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.infrastructure.cache.redis_client import RedisClient


@dataclass(frozen=True)
class BackendResult:
    count: int  # requests seen in the current window, INCLUDING this one
    remaining: int  # max(0, limit - count)
    reset_after_seconds: int  # seconds until the window resets (>= 1 while active)


class RateLimiterBackendProtocol(Protocol):
    async def check(self, key: str, limit: int, window_seconds: int) -> BackendResult: ...


# KEYS[1] = counter key, ARGV[1] = window seconds.
# Returns {count, ttl_seconds} atomically.
_FIXED_WINDOW_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


class RedisRateLimiterBackend:
    def __init__(self, redis_client: RedisClient) -> None:
        self._redis = redis_client
        self._script: Callable | None = None  # registered lazily, cached by SHA

    async def check(self, key: str, limit: int, window_seconds: int) -> BackendResult:
        if self._script is None:
            self._script = self._redis.client.register_script(_FIXED_WINDOW_LUA)
        count, ttl = await self._script(keys=[key], args=[window_seconds])
        return BackendResult(
            count=int(count),
            remaining=max(0, limit - int(count)),
            reset_after_seconds=max(1, int(ttl)),
        )


@dataclass
class _Window:
    expires_at: float
    count: int


@dataclass
class FakeRateLimiterBackend:
    """In-memory fixed-window counters; monotonic clock injectable. No I/O."""

    clock: Callable[[], float] = time.monotonic
    _windows: dict[str, _Window] = field(default_factory=dict)

    async def check(self, key: str, limit: int, window_seconds: int) -> BackendResult:
        now = self.clock()
        window = self._windows.get(key)
        if window is None or now >= window.expires_at:
            window = _Window(expires_at=now + window_seconds, count=1)
            self._windows[key] = window
        else:
            window.count += 1
        return BackendResult(
            count=window.count,
            remaining=max(0, limit - window.count),
            reset_after_seconds=max(1, math.ceil(window.expires_at - now)),
        )


# mypy-only structural proof that both implementations satisfy the Protocol.
def _static_protocol_check(
    real: RedisRateLimiterBackend, fake: FakeRateLimiterBackend
) -> tuple[RateLimiterBackendProtocol, RateLimiterBackendProtocol]:
    return real, fake
