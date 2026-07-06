"""RateLimiter — the shared core both the middleware and the dependency call.

Pure (no FastAPI). Backend failures are a STORED decision, never an accident:
the effective fail mode is `rule.fail_open` when set, else the injected global
default. Fail-open allows the request but logs loudly and emits a log-based
metric event (`rate_limit_backend_failure`); fail-closed raises. Neither path
is silent.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.core.errors.core_errors import RateLimitExceededError
from app.rate_limiting.backend import RateLimiterBackendProtocol
from app.rate_limiting.keys import RateLimitKeyBuilder
from app.rate_limiting.rules import RateLimitRule

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


class RateLimiter:
    def __init__(
        self, backend: RateLimiterBackendProtocol, *, default_fail_open: bool = True
    ) -> None:
        self._backend = backend
        self._default_fail_open = default_fail_open

    async def check(self, rule: RateLimitRule, identifier: str) -> RateLimitDecision:
        key = RateLimitKeyBuilder.build(rule, identifier)
        try:
            result = await self._backend.check(key, rule.limit, rule.window_seconds)
        except Exception as exc:  # backend down — apply the stored fail mode, loudly
            fail_open = rule.fail_open if rule.fail_open is not None else self._default_fail_open
            # This event doubles as the metric for backend failures.
            logger.error(
                "rate_limit_backend_failure",
                module="rate_limiting",
                operation="check",
                rule=rule.name,
                fail_open=fail_open,
                error_type=type(exc).__name__,
            )
            if fail_open:
                return RateLimitDecision(
                    allowed=True,
                    limit=rule.limit,
                    remaining=rule.limit,
                    reset_after_seconds=0,
                )
            raise RateLimitExceededError(
                "Rate limiting unavailable for a protected action",
                details={"rule": rule.name, "reason": "backend_unavailable"},
                retry_after=rule.window_seconds,
                limit=rule.limit,
                remaining=0,
            ) from exc

        return RateLimitDecision(
            allowed=result.count <= rule.limit,
            limit=rule.limit,
            remaining=result.remaining,
            reset_after_seconds=result.reset_after_seconds,
        )

    async def enforce(self, rule: RateLimitRule, identifier: str) -> RateLimitDecision:
        """check() that raises on denial — callers cannot forget the bool."""
        decision = await self.check(rule, identifier)
        if not decision.allowed:
            logger.warning(
                "rate_limit_exceeded",
                module="rate_limiting",
                operation="enforce",
                rule=rule.name,
            )
            raise RateLimitExceededError(
                details={"rule": rule.name},
                retry_after=decision.reset_after_seconds,
                limit=decision.limit,
                remaining=decision.remaining,
            )
        return decision
