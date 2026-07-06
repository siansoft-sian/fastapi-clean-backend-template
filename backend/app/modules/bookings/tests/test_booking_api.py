"""Bookings API end-to-end with fakes: the full per-request stack —
auth -> CSRF -> coarse scope -> rate limit -> use case (fine authz + policy)
-> repository -> outbox -> envelope. No GoTrue/DB/Redis; Casbin is REAL (the
authorization service factory loads the authored policy), so principals carry
roles the policy grants.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.app import create_app
from app.auth.auth_context import AuthContext
from app.auth.dependencies import get_current_principal
from app.auth.session_repository import FakeSessionRepository
from app.modules.bookings.infrastructure.fake_booking_repository import FakeBookingRepository
from app.modules.bookings.infrastructure.outbox_adapter import LoggingOutboxAdapter

TENANT = "tenant-1"
OTHER_TENANT = "tenant-2"
ADMIN_SCOPES = frozenset({"booking.create", "booking.read", "booking.approve", "booking.cancel"})
CSRF = {"Cookie": "csrftoken=tok", "X-CSRF-Token": "tok"}

CREATE_BODY = {
    "reference": "BK-100",
    "resource_id": "room-a",
    "scheduled_at": datetime(2026, 8, 1, 10, 0, tzinfo=UTC).isoformat(),
}


def make_principal(
    *,
    user_id: str = "user-1",
    tenant_id: str = TENANT,
    roles: frozenset[str] = frozenset({"admin"}),
    scopes: frozenset[str] = ADMIN_SCOPES,
) -> AuthContext:
    return AuthContext(
        user_id=user_id, tenant_id=tenant_id, session_id="session-1", roles=roles, scopes=scopes
    )


def build_app(
    principal: AuthContext | None = None,
) -> tuple[FastAPI, FakeBookingRepository, LoggingOutboxAdapter]:
    app = create_app()
    repo = FakeBookingRepository()
    outbox = LoggingOutboxAdapter()
    app.state.booking_repository = repo
    app.state.booking_outbox = outbox
    # A session store always exists in production; without it the dependency
    # graph fails as a wiring error before the missing-cookie 401 can fire.
    app.state.session_repository = FakeSessionRepository()
    if principal is not None:
        app.dependency_overrides[get_current_principal] = lambda: principal
    return app, repo, outbox


def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def create_booking(client: httpx.AsyncClient, body: dict[str, Any] | None = None) -> Any:
    return await client.post("/api/v1/bookings", json=body or CREATE_BODY, headers=CSRF)


# --- happy paths -------------------------------------------------------------


async def test_create_get_approve_cancel_happy_path() -> None:
    app, _, outbox = build_app(make_principal())
    async with make_client(app) as client:
        created = await create_booking(client)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["success"] is True
        booking = body["data"]
        assert booking["status"] == "pending"
        assert booking["reference"] == "BK-100"
        assert booking["owner_id"] == "user-1"
        assert body["meta"]["request_id"]

        fetched = await client.get(f"/api/v1/bookings/{booking['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["data"]["id"] == booking["id"]

        approved = await client.post(f"/api/v1/bookings/{booking['id']}/approve", headers=CSRF)
        assert approved.status_code == 200, approved.text
        assert approved.json()["data"]["status"] == "approved"
        assert approved.json()["data"]["version"] == 2

        cancelled = await client.post(
            f"/api/v1/bookings/{booking['id']}/cancel",
            json={"reason": "client asked"},
            headers=CSRF,
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["status"] == "cancelled"

    assert [event.event_type for event in outbox.events] == [
        "booking.created",
        "booking.approved",
        "booking.cancelled",
    ]


# --- the guard stack ----------------------------------------------------------


async def test_no_session_is_401() -> None:
    app, _, _ = build_app(principal=None)  # no override: missing cookie -> 401
    async with make_client(app) as client:
        response = await create_booking(client)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


async def test_insufficient_scope_is_403_before_any_work() -> None:
    principal = make_principal(scopes=frozenset({"booking.read"}))
    app, repo, outbox = build_app(principal)
    async with make_client(app) as client:
        response = await create_booking(client)
    assert response.status_code == 403
    assert response.json()["error"]["details"]["missing_scope"] == "booking.create"
    assert await repo.list_for_tenant(tenant_id=TENANT) == []
    assert outbox.events == []


async def test_fine_grained_layer_denies_even_with_coarse_scope() -> None:
    # Scope cache says yes, but the actor's ROLES can't create bookings:
    # Layer 2 (real Casbin policy) is authoritative.
    principal = make_principal(roles=frozenset({"staff"}), scopes=ADMIN_SCOPES)
    app, repo, _ = build_app(principal)
    async with make_client(app) as client:
        response = await create_booking(client)
    assert response.status_code == 403
    assert await repo.list_for_tenant(tenant_id=TENANT) == []


async def test_missing_or_mismatched_csrf_is_403() -> None:
    app, _, _ = build_app(make_principal())
    async with make_client(app) as client:
        missing = await client.post("/api/v1/bookings", json=CREATE_BODY)
        mismatched = await client.post(
            "/api/v1/bookings",
            json=CREATE_BODY,
            headers={"Cookie": "csrftoken=tok", "X-CSRF-Token": "wrong"},
        )
    for response in (missing, mismatched):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


async def test_invalid_body_is_422() -> None:
    app, _, _ = build_app(make_principal())
    async with make_client(app) as client:
        response = await client.post("/api/v1/bookings", json={"reference": ""}, headers=CSRF)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_cross_tenant_booking_is_404() -> None:
    app, repo, _ = build_app(make_principal(tenant_id=TENANT))
    foreign = await repo.create(
        tenant_id=OTHER_TENANT,
        owner_id="stranger",
        reference="BK-X",
        resource_id="room-z",
        scheduled_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        created_by="stranger",
    )
    async with make_client(app) as client:
        read = await client.get(f"/api/v1/bookings/{foreign.id}")
        mutate = await client.post(f"/api/v1/bookings/{foreign.id}/approve", headers=CSRF)
    assert read.status_code == 404
    assert read.json()["error"]["code"] == "BOOKING_NOT_FOUND"
    assert mutate.status_code == 404


async def test_invalid_transition_is_409() -> None:
    app, _, _ = build_app(make_principal())
    async with make_client(app) as client:
        booking = (await create_booking(client)).json()["data"]
        url = f"/api/v1/bookings/{booking['id']}/approve"
        assert (await client.post(url, headers=CSRF)).status_code == 200
        second = await client.post(url, headers=CSRF)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "BOOKING_INVALID_TRANSITION"


async def test_over_the_rate_limit_is_429(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.rate_limiting.backend import FakeRateLimiterBackend
    from app.rate_limiting.limiter import RateLimiter
    from app.rate_limiting.rules import RULES, RateLimitRule, RateLimitScope

    monkeypatch.setitem(
        RULES,
        "booking.create",
        RateLimitRule("booking.create", limit=1, window_seconds=60, scope=RateLimitScope.USER),
    )
    app, _, _ = build_app(make_principal())
    app.state.rate_limiter = RateLimiter(FakeRateLimiterBackend())
    async with make_client(app) as client:
        assert (await create_booking(client)).status_code == 201
        blocked = await create_booking(
            client, {**CREATE_BODY, "reference": "BK-101", "resource_id": "room-b"}
        )
    assert blocked.status_code == 429
    assert blocked.headers["X-RateLimit-Limit"] == "1"
    assert "Retry-After" in blocked.headers
