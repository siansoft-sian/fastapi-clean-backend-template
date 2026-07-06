"""LAYER 1: the coarse route scope gate (require_scope) on the demo route."""

from tests.authz.conftest import build_app, make_client, make_principal


async def test_missing_scope_rejected_with_403(approve_url: str) -> None:
    principal = make_principal(scopes=frozenset())  # no scopes at all
    async with make_client(build_app(principal)) as client:
        response = await client.post(approve_url)
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "FORBIDDEN"
    assert body["error"]["details"]["missing_scope"] == "booking.approve"


async def test_unrelated_scope_rejected_with_403(approve_url: str) -> None:
    principal = make_principal(scopes=frozenset({"event.read", "profile.update"}))
    async with make_client(build_app(principal)) as client:
        response = await client.post(approve_url)
    assert response.status_code == 403


async def test_holder_of_scope_passes_the_gate(approve_url: str) -> None:
    principal = make_principal(scopes=frozenset({"booking.approve"}))
    async with make_client(build_app(principal)) as client:
        response = await client.post(approve_url)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"approved": True, "by": "user-1"}
