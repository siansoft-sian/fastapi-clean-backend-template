"""Contract: every error leaves the app as the standard envelope.

Covers the AppError family, request validation, unknown routes (HTTPException),
and the catch-all 500 — which must never leak internals to the client.
"""

from typing import Any

import httpx
from fastapi import FastAPI

from app.app import create_app
from app.core.errors.core_errors import ConflictError
from app.core.errors.error_envelope import REDACTED
from tests.conftest import assert_envelope


def app_with_failing_routes() -> FastAPI:
    app = create_app()

    @app.get("/boom/app-error")
    async def boom_app_error() -> dict[str, Any]:
        raise ConflictError(
            "booking already exists",
            details={"booking_ref": "b-1", "api_token": "should-never-leak"},
        )

    @app.get("/boom/unhandled")
    async def boom_unhandled() -> dict[str, Any]:
        raise ValueError("internal secret detail")

    @app.get("/boom/validated")
    async def boom_validated(limit: int) -> dict[str, Any]:
        return {"limit": limit}

    return app


def make_client(app: FastAPI, *, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_app_error_maps_to_envelope_with_meta_and_redaction() -> None:
    async with make_client(app_with_failing_routes()) as client:
        response = await client.get("/boom/app-error")
    assert response.status_code == 409
    body = response.json()
    assert_envelope(body)
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["message"] == "booking already exists"
    assert body["error"]["details"]["booking_ref"] == "b-1"
    assert body["error"]["details"]["api_token"] == REDACTED
    meta = body["meta"]
    assert meta["request_id"]
    assert meta["path"] == "/boom/app-error"
    assert meta["method"] == "GET"
    assert meta["category"] == "conflict"


async def test_validation_error_maps_to_422_envelope() -> None:
    async with make_client(app_with_failing_routes()) as client:
        response = await client.get("/boom/validated", params={"limit": "not-a-number"})
    assert response.status_code == 422
    body = response.json()
    assert_envelope(body)
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["meta"]["category"] == "validation"
    assert body["error"]["details"]["errors"], "validation details must be present"


async def test_unknown_route_maps_to_404_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/definitely-not-here")
    assert response.status_code == 404
    body = response.json()
    assert_envelope(body)
    assert body["error"]["code"] == "HTTP_ERROR"
    assert body["meta"]["category"] == "http"


async def test_unhandled_exception_returns_generic_500_envelope() -> None:
    async with make_client(app_with_failing_routes(), raise_app_exceptions=False) as client:
        response = await client.get("/boom/unhandled")
    assert response.status_code == 500
    body = response.json()
    assert_envelope(body)
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "Internal server error"
    assert body["meta"]["request_id"], "catch-all must still carry the request id"
    # No stack trace or internal detail may reach the client.
    raw = response.text
    assert "internal secret detail" not in raw
    assert "ValueError" not in raw
    assert "Traceback" not in raw
