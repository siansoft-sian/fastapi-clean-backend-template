"""RequestContextMiddleware: request id must reach logs, contextvar, and headers.

Uses a minimal inline app (not create_app) so this is a pure middleware test.
Log assertions parse the JSON emitted on stdout — the exact stream production
ships — which stays deterministic even after structlog has cached its loggers.
"""

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.constants import REQUEST_ID_HEADER
from app.core.context import get_request_id
from app.core.logging.core_logging import configure_logging
from app.core.middleware import install_middleware
from app.core.responses import api_success


def build_app() -> FastAPI:
    configure_logging("INFO")
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


async def test_incoming_request_id_is_honored_bound_and_logged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with make_client(build_app()) as client:
        response = await client.get("/ping", headers={REQUEST_ID_HEADER: "req-123"})

    assert response.headers[REQUEST_ID_HEADER] == "req-123"
    # The contextvar was visible inside the endpoint...
    assert response.json()["data"]["request_id"] == "req-123"
    # ...and the JSON access-log line on stdout carries it.
    stdout = capsys.readouterr().out
    events = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    completed = [event for event in events if event.get("event") == "request_completed"]
    assert completed, f"no request_completed event on stdout: {stdout!r}"
    assert completed[0]["request_id"] == "req-123"
    assert completed[0]["status"] == 200
    assert "duration_ms" in completed[0]
