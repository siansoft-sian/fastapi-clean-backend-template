"""RequestContextMiddleware: request id must reach logs, contextvar, and headers.

Uses a minimal inline app (not create_app) so this is a pure middleware test.
"""

from typing import Any

import httpx
import structlog
from fastapi import FastAPI

from app.core.constants import REQUEST_ID_HEADER
from app.core.context import get_request_id
from app.core.middleware import install_middleware
from app.core.responses import api_success


def build_app() -> FastAPI:
    app = FastAPI()
    install_middleware(app)

    @app.get("/ping")
    async def ping() -> dict[str, Any]:
        return api_success({"request_id": get_request_id()})

    return app


def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_response_carries_generated_request_id_header() -> None:
    async with make_client(build_app()) as client:
        response = await client.get("/ping")
    assert response.status_code == 200
    assert response.headers.get(REQUEST_ID_HEADER)


async def test_incoming_request_id_is_honored_bound_and_logged() -> None:
    with structlog.testing.capture_logs() as logs:
        async with make_client(build_app()) as client:
            response = await client.get("/ping", headers={REQUEST_ID_HEADER: "req-123"})

    assert response.headers[REQUEST_ID_HEADER] == "req-123"
    # The contextvar was visible inside the endpoint...
    assert response.json()["data"]["request_id"] == "req-123"
    # ...and the access log line carries it.
    completed = [entry for entry in logs if entry["event"] == "request_completed"]
    assert completed, f"no request_completed event in {logs}"
    assert completed[0]["request_id"] == "req-123"
    assert completed[0]["status"] == 200
    assert "duration_ms" in completed[0]
