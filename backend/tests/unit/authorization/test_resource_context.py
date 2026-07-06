"""ResourceContext: construction, defaults, immutability, scope format."""

import dataclasses

import pytest

from app.authorization import permission_actions as pa
from app.authorization.resource_context import ResourceContext


def make_context(**overrides: object) -> ResourceContext:
    defaults: dict = {
        "actor_user_id": "user-1",
        "tenant_id": "tenant-1",
        "roles": frozenset({"manager"}),
        "action": pa.APPROVE,
        "resource_type": pa.BOOKING,
    }
    defaults.update(overrides)
    return ResourceContext(**defaults)


def test_minimal_construction_and_defaults() -> None:
    ctx = make_context()
    assert ctx.resource_id is None
    assert ctx.resource_owner_id is None
    assert ctx.assigned_user_ids == frozenset()
    assert ctx.resource_tenant_id is None


def test_full_construction() -> None:
    ctx = make_context(
        resource_id="booking-9",
        resource_owner_id="user-2",
        assigned_user_ids=frozenset({"user-1"}),
        resource_tenant_id="tenant-1",
    )
    assert ctx.resource_id == "booking-9"
    assert "user-1" in ctx.assigned_user_ids


def test_context_is_frozen() -> None:
    ctx = make_context()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.action = pa.DELETE  # type: ignore[misc]


def test_scope_format_is_centralized() -> None:
    assert pa.scope_for(pa.BOOKING, pa.APPROVE) == "booking.approve"
    # every registered action belongs to its resource's registry
    for resource_type, actions in pa.ACTIONS_BY_RESOURCE.items():
        for action in actions:
            assert pa.scope_for(resource_type, action) == f"{resource_type}.{action}"
