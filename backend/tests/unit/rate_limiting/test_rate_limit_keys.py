"""Key construction: deterministic, scoped, collision-free across rules.
Plus the client-IP resolver's proxy-trust behavior (pure)."""

from app.rate_limiting.client_ip import parse_trusted_proxies, resolve_client_ip
from app.rate_limiting.keys import RateLimitKeyBuilder
from app.rate_limiting.rules import RateLimitRule, RateLimitScope


def make_rule(name: str, scope: RateLimitScope) -> RateLimitRule:
    return RateLimitRule(name=name, limit=10, window_seconds=60, scope=scope)


def test_key_contains_rule_scope_and_identifier() -> None:
    rule = make_rule("booking.create", RateLimitScope.USER)
    key = RateLimitKeyBuilder.build(rule, "user-42")
    assert key == "app:rl:booking.create:user:user-42"


def test_keys_differ_per_rule_scope_and_identifier() -> None:
    user_rule = make_rule("booking.create", RateLimitScope.USER)
    other_rule = make_rule("booking.approve", RateLimitScope.USER)
    ip_rule = make_rule("booking.create", RateLimitScope.IP)

    keys = {
        RateLimitKeyBuilder.build(user_rule, "id-1"),
        RateLimitKeyBuilder.build(user_rule, "id-2"),
        RateLimitKeyBuilder.build(other_rule, "id-1"),
        RateLimitKeyBuilder.build(ip_rule, "id-1"),
    }
    assert len(keys) == 4  # no collisions across rules/scopes/identifiers


def test_identifier_cannot_forge_key_segments() -> None:
    rule = make_rule("x", RateLimitScope.IP)
    key = RateLimitKeyBuilder.build(rule, "1.2.3.4:evil:suffix")
    assert key == "app:rl:x:ip:1.2.3.4_evil_suffix"


# --- client ip resolution ---


def test_xff_ignored_without_trusted_proxies() -> None:
    assert resolve_client_ip("203.0.113.9", "10.0.0.1, 198.51.100.7", ()) == "203.0.113.9"


def test_xff_ignored_when_peer_is_untrusted() -> None:
    trusted = parse_trusted_proxies("10.0.0.0/8")
    assert resolve_client_ip("203.0.113.9", "198.51.100.7", trusted) == "203.0.113.9"


def test_xff_walked_right_to_left_skipping_trusted_hops() -> None:
    trusted = parse_trusted_proxies("10.0.0.0/8")
    # client -> (spoofed entry) -> real client -> our proxy chain
    header = "6.6.6.6, 198.51.100.7, 10.0.0.5"
    assert resolve_client_ip("10.0.0.1", header, trusted) == "198.51.100.7"


def test_all_hops_trusted_falls_back_to_leftmost() -> None:
    trusted = parse_trusted_proxies("10.0.0.0/8")
    assert resolve_client_ip("10.0.0.1", "10.0.0.9, 10.0.0.5", trusted) == "10.0.0.9"


def test_missing_peer_is_unknown() -> None:
    assert resolve_client_ip(None, "198.51.100.7", ()) == "unknown"
