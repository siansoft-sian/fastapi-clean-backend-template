"""Identity mapping: known subjects map, unknown ones raise unless provisioning."""

import pytest

from app.auth.exceptions import IdentityMappingError
from app.auth.identity_mapper import FakeIdentityMapper


async def test_known_subject_maps_to_internal_identity() -> None:
    mapper = FakeIdentityMapper()
    mapper.add_mapping("gotrue-sub-1", user_id="user-1", tenant_id="tenant-1")
    identity = await mapper.map_identity(provider_subject="gotrue-sub-1", email="a@b.c")
    assert identity.user_id == "user-1"
    assert identity.tenant_id == "tenant-1"


async def test_unknown_subject_raises_when_provisioning_disallowed() -> None:
    mapper = FakeIdentityMapper(allow_provision=False)
    with pytest.raises(IdentityMappingError) as exc_info:
        await mapper.map_identity(provider_subject="stranger", email=None)
    assert exc_info.value.http_status == 500


async def test_provisioning_mints_stable_identity() -> None:
    mapper = FakeIdentityMapper(allow_provision=True)
    first = await mapper.map_identity(provider_subject="new-user", email="n@e.w")
    second = await mapper.map_identity(provider_subject="new-user", email="n@e.w")
    assert first == second
    assert first.user_id and first.tenant_id
