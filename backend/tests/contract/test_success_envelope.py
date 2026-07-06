"""Contract: success responses are exactly {success, data, error, meta}."""

import httpx

from tests.conftest import assert_envelope


async def test_success_envelope_contract(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert_envelope(body)
    assert body["success"] is True
    assert body["error"] is None
    assert body["meta"]["request_id"]


async def test_request_id_round_trips_into_meta(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health/live", headers={"X-Request-ID": "trace-42"})
    body = response.json()
    assert body["meta"]["request_id"] == "trace-42"
    assert response.headers["X-Request-ID"] == "trace-42"
