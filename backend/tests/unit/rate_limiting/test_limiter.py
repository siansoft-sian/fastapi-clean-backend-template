"""RateLimiter with the fake backend: allow-to-limit, deny, fail-open/closed."""

import pytest

from app.core.errors.core_errors import RateLimitExceededError
from app.rate_limiting.backend import BackendResult, FakeRateLimiterBackend
from app.rate_limiting.limiter import RateLimiter
from app.rate_limiting.rules import RateLimitRule, RateLimitScope


def make_rule(*, limit: int = 3, window: int = 60, fail_open: bool | None = None) -> RateLimitRule:
    return RateLimitRule(
        name="test.rule",
        limit=limit,
        window_seconds=window,
        scope=RateLimitScope.USER,
        fail_open=fail_open,
    )


class BrokenBackend:
    """Simulates Redis being down."""

    async def check(self, key: str, limit: int, window_seconds: int) -> BackendResult:
        raise ConnectionError("redis unreachable")


async def test_allows_up_to_limit_then_denies_with_reset() -> None:
    limiter = RateLimiter(FakeRateLimiterBackend())
    rule = make_rule(limit=3)

    for expected_remaining in (2, 1, 0):
        decision = await limiter.check(rule, "user-1")
        assert decision.allowed is True
        assert decision.remaining == expected_remaining

    denied = await limiter.check(rule, "user-1")
    assert denied.allowed is False
    assert denied.remaining == 0
    assert denied.reset_after_seconds > 0


async def test_identifiers_are_isolated() -> None:
    limiter = RateLimiter(FakeRateLimiterBackend())
    rule = make_rule(limit=1)
    assert (await limiter.check(rule, "user-a")).allowed is True
    assert (await limiter.check(rule, "user-a")).allowed is False
    assert (await limiter.check(rule, "user-b")).allowed is True  # separate key


async def test_window_reset_allows_again() -> None:
    now = [0.0]
    limiter = RateLimiter(FakeRateLimiterBackend(clock=lambda: now[0]))
    rule = make_rule(limit=1, window=10)
    assert (await limiter.check(rule, "u")).allowed is True
    assert (await limiter.check(rule, "u")).allowed is False
    now[0] += 11  # window lapses
    assert (await limiter.check(rule, "u")).allowed is True


async def test_enforce_raises_with_header_payload() -> None:
    limiter = RateLimiter(FakeRateLimiterBackend())
    rule = make_rule(limit=1, window=30)
    await limiter.enforce(rule, "user-1")
    with pytest.raises(RateLimitExceededError) as exc_info:
        await limiter.enforce(rule, "user-1")
    error = exc_info.value
    assert error.http_status == 429
    assert error.limit == 1
    assert error.remaining == 0
    assert 1 <= error.retry_after <= 30
    assert error.details["rule"] == "test.rule"


async def test_backend_failure_fails_open_by_default_and_logs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.core.logging.core_logging import configure_logging

    configure_logging("INFO")
    limiter = RateLimiter(BrokenBackend(), default_fail_open=True)
    decision = await limiter.check(make_rule(fail_open=None), "user-1")
    assert decision.allowed is True  # fail-open: never an outage by accident
    assert "rate_limit_backend_failure" in capsys.readouterr().out  # ...but LOUD


async def test_backend_failure_fails_closed_for_pinned_rule() -> None:
    limiter = RateLimiter(BrokenBackend(), default_fail_open=True)
    rule = make_rule(fail_open=False, window=60)
    with pytest.raises(RateLimitExceededError) as exc_info:
        await limiter.check(rule, "user-1")
    assert exc_info.value.details["reason"] == "backend_unavailable"
    assert exc_info.value.retry_after == 60


async def test_global_default_fail_closed_honored_when_rule_unset() -> None:
    limiter = RateLimiter(BrokenBackend(), default_fail_open=False)
    with pytest.raises(RateLimitExceededError):
        await limiter.check(make_rule(fail_open=None), "user-1")
