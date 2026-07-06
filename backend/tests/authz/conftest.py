"""Shared harness for the two-layer authorization tests.

Principals are injected by overriding get_current_principal (roles/scopes on
AuthContext are the M3-reconcile injection point until get_user_roles ships);
CSRF is overridden to a no-op — it has its own suite in tests/api. The
AuthorizationService is the REAL one, lazily built by the factory from the
authored model + policy files.
"""

import httpx
import pytest
from fastapi import FastAPI

from app.app import create_app
from app.auth.auth_context import AuthContext
from app.auth.dependencies import get_current_principal, verify_csrf


def make_principal(
    *,
    user_id: str = "user-1",
    tenant_id: str = "tenant-1",
    roles: frozenset[str] = frozenset(),
    scopes: frozenset[str] = frozenset(),
) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        session_id="session-1",
        email="user@example.com",
        roles=roles,
        scopes=scopes,
    )


def build_app(principal: AuthContext) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[verify_csrf] = lambda: None
    return app


def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
def approve_url() -> str:
    return "/api/v1/_authz-demo/approve"
