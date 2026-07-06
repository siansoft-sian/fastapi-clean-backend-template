"""Rate-limit rules: the named registry both layers consume. Pure.

The numbers below are STARTING VALUES to be tuned with real traffic data —
they encode relative sensitivity (refund << reads), not measured capacity.
`fail_open=None` inherits the global `settings.rate_limit_fail_open`;
sensitive rules (auth.login, payment.refund) pin fail-closed explicitly.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class RateLimitScope(StrEnum):
    IP = "ip"
    USER = "user"
    TENANT = "tenant"
    ROUTE = "route"
    ACTION = "action"
    RESOURCE = "resource"


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int
    scope: RateLimitScope
    fail_open: bool | None = None  # None -> settings.rate_limit_fail_open


GLOBAL_IP_RULE_NAME: Final = "global.ip"

RULES: Final[dict[str, RateLimitRule]] = {
    rule.name: rule
    for rule in (
        # Coarse pre-auth ceiling applied by the middleware to every request.
        RateLimitRule(GLOBAL_IP_RULE_NAME, limit=300, window_seconds=60, scope=RateLimitScope.IP),
        # Sensitive, unauthenticated: fail-closed on backend failure.
        RateLimitRule(
            "auth.login", limit=10, window_seconds=60, scope=RateLimitScope.IP, fail_open=False
        ),
        RateLimitRule("booking.create", limit=30, window_seconds=60, scope=RateLimitScope.USER),
        RateLimitRule("booking.approve", limit=60, window_seconds=60, scope=RateLimitScope.USER),
        RateLimitRule("profile.update", limit=20, window_seconds=60, scope=RateLimitScope.USER),
        RateLimitRule("events.read", limit=120, window_seconds=60, scope=RateLimitScope.USER),
        # Sensitive, money-moving: fail-closed on backend failure.
        RateLimitRule(
            "payment.refund",
            limit=5,
            window_seconds=60,
            scope=RateLimitScope.USER,
            fail_open=False,
        ),
        RateLimitRule("webhook.payment", limit=100, window_seconds=60, scope=RateLimitScope.IP),
    )
}


def get_rule(name: str) -> RateLimitRule:
    """Registry lookup; unknown names are a wiring bug and fail loudly."""
    rule = RULES.get(name)
    if rule is None:
        raise ValueError(f"Unknown rate-limit rule: {name!r}")
    return rule
