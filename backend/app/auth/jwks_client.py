"""Cached JWKS client for verifying GoTrue access tokens server-side.

Construction opens no socket. The first fetch happens on first use, or during
lifespan when STARTUP_PRELOAD_JWKS=true. Keys are cached for a TTL and
refreshed when an unknown `kid` arrives — but at most once per
`min_refresh_interval_seconds`, so garbage tokens cannot hammer the endpoint.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from app.auth.exceptions import TokenVerificationError

_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class JwksClient:
    def __init__(
        self,
        *,
        jwks_url: str,
        cache_ttl_seconds: int = 3600,
        min_refresh_interval_seconds: int = 30,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._jwks_url = jwks_url
        self._ttl = cache_ttl_seconds
        self._min_refresh_interval = min_refresh_interval_seconds
        self._http_client = http_client
        self._clock = clock
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float | None = None

    async def preload(self) -> None:
        """Optional warm-up (used by container.startup when the flag is set)."""
        await self._refresh()

    async def get_key(self, kid: str) -> dict[str, Any]:
        """Return the JWK for `kid`, refreshing the cache when stale or unknown."""
        if self._is_stale():
            await self._refresh()
        if kid not in self._keys and self._may_refresh_for_unknown_kid():
            await self._refresh()
        key = self._keys.get(kid)
        if key is None:
            raise TokenVerificationError("Unknown signing key", details={"kid": kid})
        return key

    def _is_stale(self) -> bool:
        if self._fetched_at is None:
            return True
        return (self._clock() - self._fetched_at) >= self._ttl

    def _may_refresh_for_unknown_kid(self) -> bool:
        if self._fetched_at is None:
            return True
        return (self._clock() - self._fetched_at) >= self._min_refresh_interval

    async def _refresh(self) -> None:
        try:
            if self._http_client is not None:
                response = await self._http_client.get(self._jwks_url)
            else:
                async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                    response = await client.get(self._jwks_url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise TokenVerificationError(
                "JWKS fetch failed", details={"error_type": type(exc).__name__}
            ) from exc
        keys: dict[str, dict[str, Any]] = {}
        for jwk in payload.get("keys", []):
            kid = jwk.get("kid")
            if isinstance(kid, str) and kid:
                keys[kid] = jwk
        self._keys = keys
        self._fetched_at = self._clock()
