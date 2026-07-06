"""DBTransactionMiddleware semantics through the REAL app stack.

A fake transaction manager is planted on app.state (what lifespan would do
when STARTUP_CONNECT_DATABASE=true), so these tests exercise the exact
middleware + exception-handler pipeline without Postgres:

- 2xx mutating response  -> commit
- AppError -> error response (409) -> rollback
- unhandled exception -> 500 -> rollback
- reads -> plain connection, no transaction
- manager absent -> pass-through (no connection stashed)
"""

from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from app.api.deps import DbConnectionDep
from app.app import create_app
from app.core.errors.core_errors import ConflictError
from app.core.responses import api_success


class FakeTransactionManager:
    def __init__(self) -> None:
        self.outcomes: list[str] = []
        self.plain_connections = 0

    @asynccontextmanager
    async def transaction(self) -> Any:
        try:
            yield object()
        except BaseException:
            self.outcomes.append("rollback")
            raise
        else:
            self.outcomes.append("commit")

    @asynccontextmanager
    async def connection(self) -> Any:
        self.plain_connections += 1
        yield object()


def build_app(manager: FakeTransactionManager | None) -> FastAPI:
    app = create_app()
    app.state.transaction_manager = manager

    @app.post("/things")
    async def create_thing(connection: DbConnectionDep) -> dict[str, Any]:
        return api_success({"has_connection": connection is not None})

    @app.post("/conflict")
    async def conflict(connection: DbConnectionDep) -> dict[str, Any]:
        raise ConflictError("already exists")

    @app.post("/explode")
    async def explode(connection: DbConnectionDep) -> dict[str, Any]:
        raise ValueError("unhandled")

    @app.get("/things")
    async def read_things(connection: DbConnectionDep) -> dict[str, Any]:
        return api_success({"has_connection": connection is not None})

    return app


def make_client(app: FastAPI, *, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_mutating_2xx_commits() -> None:
    manager = FakeTransactionManager()
    async with make_client(build_app(manager)) as client:
        response = await client.post("/things")
    assert response.status_code == 200
    assert response.json()["data"]["has_connection"] is True
    assert manager.outcomes == ["commit"]


async def test_app_error_response_rolls_back_but_returns_envelope() -> None:
    manager = FakeTransactionManager()
    async with make_client(build_app(manager)) as client:
        response = await client.post("/conflict")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert manager.outcomes == ["rollback"]


async def test_unhandled_exception_rolls_back_and_returns_500() -> None:
    manager = FakeTransactionManager()
    async with make_client(build_app(manager), raise_app_exceptions=False) as client:
        response = await client.post("/explode")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert manager.outcomes == ["rollback"]


async def test_reads_use_plain_connection_without_transaction() -> None:
    manager = FakeTransactionManager()
    async with make_client(build_app(manager)) as client:
        response = await client.get("/things")
    assert response.status_code == 200
    assert manager.plain_connections == 1
    assert manager.outcomes == []


async def test_disabled_database_is_a_pass_through() -> None:
    async with make_client(build_app(None), raise_app_exceptions=False) as client:
        response = await client.post("/things")
    # No manager -> no request-scoped connection -> the dependency raises a
    # wiring error, surfaced as a generic 500 (never a silent fake success).
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
