"""Health endpoints respond 200 with the standard envelope."""

import httpx

from app.core.constants import REQUEST_ID_HEADER
from tests.conftest import assert_envelope

LIVE_PATHS = ("/health/live", "/api/v1/health/live")


async def test_liveness_endpoints(client: httpx.AsyncClient) -> None:
    for path in LIVE_PATHS:
        response = await client.get(path)
        assert response.status_code == 200, path
        body = response.json()
        assert_envelope(body)
        assert body["success"] is True
        assert body["data"] == {"status": "ok"}
        assert response.headers.get(REQUEST_ID_HEADER)


async def test_readiness_degrades_when_dependencies_disabled(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    assert body["data"]["status"] == "degraded"
    components = body["data"]["components"]
    assert components["database"] == "disabled"
    assert components["redis"] == "disabled"
    assert components["casbin"] == "disabled"
    assert components["jwks"] == "disabled"


async def test_deep_health_placeholder(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health/deep")
    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    assert body["data"]["status"] == "degraded"
    assert body["data"]["checks"] == {}
