"""Identity mapping: known subjects map; unknown ones honor the provision flag."""

import pytest

from app.auth.exceptions import IdentityMappingError
from app.auth.identity_mapper import FakeIdentityMapper


async def test_known_subject_maps_to_internal_identity() -> None:
    mapper = FakeIdentityMapper()
    mapper.add_mapping(
        "supabase", "gotrue-sub-1", user_id="user-1", tenant_id="tenant-1", email="a@b.c"
    )
    identity = await mapper.map_identity(
        provider="supabase", subject="gotrue-sub-1", email="a@b.c", provision=False
    )
    assert identity.user_id == "user-1"
    assert identity.tenant_id == "tenant-1"
    assert identity.email == "a@b.c"


async def test_unknown_subject_raises_when_provision_false() -> None:
    mapper = FakeIdentityMapper()
    with pytest.raises(IdentityMappingError) as exc_info:
        await mapper.map_identity(
            provider="supabase", subject="stranger", email=None, provision=False
        )
    assert exc_info.value.details["db_code"] == "IDENTITY_NOT_FOUND"


async def test_provision_true_mints_stable_identity() -> None:
    mapper = FakeIdentityMapper()
    first = await mapper.map_identity(
        provider="supabase", subject="new-user", email="n@e.w", provision=True
    )
    second = await mapper.map_identity(
        provider="supabase", subject="new-user", email="n@e.w", provision=False
    )
    assert first == second
    assert first.email == "n@e.w"


async def test_providers_are_namespaced() -> None:
    mapper = FakeIdentityMapper()
    mapper.add_mapping("supabase", "same-sub", user_id="u1", tenant_id="t1")
    with pytest.raises(IdentityMappingError):
        await mapper.map_identity(
            provider="other-idp", subject="same-sub", email=None, provision=False
        )
