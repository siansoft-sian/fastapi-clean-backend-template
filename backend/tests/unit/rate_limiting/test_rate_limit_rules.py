"""Rules registry: lookup, fields, and the fail-mode pinning of sensitive rules."""

import pytest

from app.rate_limiting.rules import (
    GLOBAL_IP_RULE_NAME,
    RULES,
    RateLimitScope,
    get_rule,
)


def test_registry_lookup_returns_rule_fields() -> None:
    rule = get_rule("booking.create")
    assert rule.name == "booking.create"
    assert rule.limit == 30
    assert rule.window_seconds == 60
    assert rule.scope is RateLimitScope.USER
    assert rule.fail_open is None  # inherits the global default


def test_unknown_rule_fails_loudly() -> None:
    with pytest.raises(ValueError, match="Unknown rate-limit rule"):
        get_rule("nope.nothing")


def test_global_ip_ceiling_exists_for_the_middleware() -> None:
    rule = get_rule(GLOBAL_IP_RULE_NAME)
    assert rule.scope is RateLimitScope.IP
    assert rule.limit >= 100  # coarse ceiling, not a per-feature limit


def test_sensitive_rules_are_fail_closed() -> None:
    assert get_rule("auth.login").fail_open is False
    assert get_rule("payment.refund").fail_open is False


def test_registry_names_match_rule_names() -> None:
    for name, rule in RULES.items():
        assert name == rule.name
