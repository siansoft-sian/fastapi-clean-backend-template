"""JwksClient: lazy fetch, TTL cache, refresh-on-unknown-kid with rate limit."""

import json

import httpx
import pytest

from app.auth.exceptions import TokenVerificationError
from app.auth.jwks_client import JwksClient

JWKS_URL = "https://project.supabase.co/auth/v1/.well-known/jwks.json"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_client(
    keys_by_fetch: list[list[dict[str, str]]], clock: FakeClock
) -> tuple[JwksClient, list[int]]:
    """JwksClient over a MockTransport serving successive JWKS payloads."""
    fetch_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        index = min(fetch_count[0], len(keys_by_fetch) - 1)
        fetch_count[0] += 1
        return httpx.Response(200, text=json.dumps({"keys": keys_by_fetch[index]}))

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = JwksClient(
        jwks_url=JWKS_URL,
        cache_ttl_seconds=3600,
        min_refresh_interval_seconds=30,
        http_client=http_client,
        clock=clock,
    )
    return client, fetch_count


KEY_A = {"kid": "key-a", "kty": "RSA", "n": "x", "e": "AQAB"}
KEY_B = {"kid": "key-b", "kty": "RSA", "n": "y", "e": "AQAB"}


def test_construction_performs_no_fetch() -> None:
    _, fetch_count = make_client([[KEY_A]], FakeClock())
    assert fetch_count[0] == 0


async def test_cache_hit_within_ttl_fetches_once() -> None:
    client, fetch_count = make_client([[KEY_A]], FakeClock())
    assert (await client.get_key("key-a"))["kid"] == "key-a"
    assert (await client.get_key("key-a"))["kid"] == "key-a"
    assert fetch_count[0] == 1


async def test_ttl_expiry_refetches() -> None:
    clock = FakeClock()
    client, fetch_count = make_client([[KEY_A], [KEY_A]], clock)
    await client.get_key("key-a")
    clock.now += 3601
    await client.get_key("key-a")
    assert fetch_count[0] == 2


async def test_unknown_kid_triggers_refresh_and_finds_rotated_key() -> None:
    clock = FakeClock()
    client, fetch_count = make_client([[KEY_A], [KEY_A, KEY_B]], clock)
    await client.get_key("key-a")
    clock.now += 31  # past the min refresh interval
    assert (await client.get_key("key-b"))["kid"] == "key-b"
    assert fetch_count[0] == 2


async def test_unknown_kid_refresh_is_rate_limited() -> None:
    clock = FakeClock()
    client, fetch_count = make_client([[KEY_A]], clock)
    await client.get_key("key-a")
    # Within the min refresh interval: unknown kid must NOT refetch.
    with pytest.raises(TokenVerificationError):
        await client.get_key("key-nope")
    assert fetch_count[0] == 1


async def test_fetch_failure_maps_to_token_verification_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = JwksClient(jwks_url=JWKS_URL, http_client=http_client)
    with pytest.raises(TokenVerificationError):
        await client.get_key("any")
