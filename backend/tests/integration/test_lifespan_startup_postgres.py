"""App startup against real Postgres.

Requires a reachable server (docker compose up -d postgres). Entering the
app's lifespan context runs the real startup: container.startup() connects
the pool, the readiness probe pings it, and shutdown() disconnects cleanly.
"""

import os
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.app import create_app
from app.core.config import get_settings

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

POSTGRES_TEST_DSN = os.environ.get("POSTGRES_TEST_DSN", "postgresql://app:app@localhost:5432/app")


def make_db_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("STARTUP_CONNECT_DATABASE", "true")
    monkeypatch.setenv("POSTGRES_DATABASE_URL", POSTGRES_TEST_DSN)
    get_settings.cache_clear()
    return create_app()


def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_lifespan_connects_pool_and_ready_reports_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = make_db_app(monkeypatch)
    async with app.router.lifespan_context(app):  # the real startup/shutdown path
        assert app.state.transaction_manager is not None
        assert app.state.db_pool is not None

        async with make_client(app) as client:
            response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "ok"
        assert body["data"]["components"]["database"] == "ok"

    # Lifespan exit tore the pool down again.
    assert app.state.db_pool is None
    assert app.state.transaction_manager is None


async def test_mutating_request_gets_request_scoped_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: middleware acquires a real transaction-scoped connection."""
    from app.api.deps import DbConnectionDep
    from app.core.responses import api_success

    app = make_db_app(monkeypatch)

    @app.post("/echo-connection")
    async def echo_connection(connection: DbConnectionDep) -> dict[str, Any]:
        value = await connection.fetchval("SELECT 41 + 1")
        return api_success({"value": value})

    async with app.router.lifespan_context(app), make_client(app) as client:
        response = await client.post("/echo-connection")
    assert response.status_code == 200
    assert response.json()["data"]["value"] == 42
