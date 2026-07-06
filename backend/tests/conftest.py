"""Shared test harness.

The autouse fixture pins a hermetic environment — testing env, sqlite provider,
every startup flag off — and clears the settings cache so each test reads it
fresh. No test in the fast suite may touch the network or a real database.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.app import create_app
from app.core.config import get_settings

TEST_ENV = {
    "APP_ENV": "testing",
    "DB_PROVIDER": "sqlite",
    "STARTUP_CONNECT_DATABASE": "false",
    "STARTUP_CONNECT_REDIS": "false",
    "STARTUP_LOAD_CASBIN": "false",
    "STARTUP_CREATE_CELERY": "false",
}


def route_paths(app: FastAPI) -> set[str]:
    """Effective route paths, tolerant of FastAPI's lazy included-router objects."""
    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is not None:
            paths.add(path)
            continue
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            paths.update(ctx.path for ctx in contexts())
    return paths


@pytest.fixture(autouse=True)
def test_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def assert_envelope(body: dict[str, Any]) -> None:
    """Every response body is exactly {success, data, error, meta} with a request id."""
    assert set(body) == {"success", "data", "error", "meta"}, body
    assert "request_id" in body["meta"], body
