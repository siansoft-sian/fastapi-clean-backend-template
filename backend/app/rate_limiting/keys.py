"""Rate-limit key construction. Pure.

Keys are deterministic and collision-free across rules because the rule name
and scope are both part of the key: `app:rl:{rule_name}:{scope}:{identifier}`.
"""

from app.infrastructure.cache.cache_keys import NAMESPACE_RATE_LIMIT, cache_key
from app.rate_limiting.rules import RateLimitRule


class RateLimitKeyBuilder:
    @staticmethod
    def build(rule: RateLimitRule, identifier: str) -> str:
        return cache_key(NAMESPACE_RATE_LIMIT, rule.name, rule.scope.value, identifier)
