"""LAYER 2: the authoritative service check on the demo edit route.

Ownership (rule 4), resource-type awareness, and the cross-tenant 404
(existence hidden) — all through the REAL model + policy.
"""

from tests.authz.conftest import build_app, make_client, make_principal


def edit_url(item_id: str) -> str:
    return f"/api/v1/_authz-demo/{item_id}/edit"


async def test_owner_edits_own_item_in_tenant() -> None:
    principal = make_principal(user_id="user-owner", roles=frozenset({"owner"}))
    async with make_client(build_app(principal)) as client:
        response = await client.post(edit_url("item-owned"))
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"edited": "item-owned", "by": "user-owner"}


async def test_non_owner_denied_403() -> None:
    principal = make_principal(user_id="user-intruder", roles=frozenset({"owner"}))
    async with make_client(build_app(principal)) as client:
        response = await client.post(edit_url("item-owned"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_broad_role_still_denied_on_wrong_resource_type() -> None:
    # admin holds booking.* — the fine gate is resource-type aware, so a
    # profile edit is still denied. The coarse gate alone would not catch this.
    principal = make_principal(user_id="user-owner", roles=frozenset({"admin"}))
    async with make_client(build_app(principal)) as client:
        response = await client.post(edit_url("item-other"))
    assert response.status_code == 403


async def test_cross_tenant_resource_surfaces_as_404() -> None:
    # The item exists but belongs to tenant-2; its existence must be hidden.
    principal = make_principal(user_id="user-owner", roles=frozenset({"owner"}))
    async with make_client(build_app(principal)) as client:
        response = await client.post(edit_url("item-foreign"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_unknown_item_is_404() -> None:
    principal = make_principal(user_id="user-owner", roles=frozenset({"owner"}))
    async with make_client(build_app(principal)) as client:
        response = await client.post(edit_url("item-nope"))
    assert response.status_code == 404
