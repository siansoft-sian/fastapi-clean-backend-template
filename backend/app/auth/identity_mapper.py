"""GoTrue identity -> internal (user_id, tenant_id) mapping — M2 repository pattern.

The mapping itself lives in the database (`app.map_identity`, see
database/postgres/functions/README.md); whether unknown identities are
auto-provisioned is a product decision made at the database-designer stage.
Raises IdentityMappingError when no mapping exists and provisioning is
disallowed.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Protocol

import asyncpg

from app.auth.exceptions import IdentityMappingError
from app.core.errors.core_errors import DatabaseResultError
from app.db.dto_base import RepositoryDTO
from app.db.errors import map_asyncpg_error

IDENTITY_NOT_FOUND = "IDENTITY_NOT_FOUND"


class InternalIdentity(RepositoryDTO):
    user_id: str
    tenant_id: str


class IdentityMapperProtocol(Protocol):
    async def map_identity(
        self, *, provider_subject: str, email: str | None
    ) -> InternalIdentity: ...


class AsyncpgIdentityMapper:
    """Calls app.map_identity (envelope-returning)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def map_identity(self, *, provider_subject: str, email: str | None) -> InternalIdentity:
        try:
            raw = await self._pool.fetchval(
                "SELECT app.map_identity($1, $2)", provider_subject, email
            )
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc
        envelope = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(envelope, dict):
            raise DatabaseResultError("map_identity returned a non-envelope result")
        if envelope.get("success"):
            data: dict[str, Any] = (envelope.get("data") or {}).get("identity") or {}
            if "user_id" not in data or "tenant_id" not in data:
                raise DatabaseResultError("map_identity envelope missing identity fields")
            return InternalIdentity(user_id=str(data["user_id"]), tenant_id=str(data["tenant_id"]))
        error = envelope.get("error") or {}
        if error.get("code") == IDENTITY_NOT_FOUND:
            raise IdentityMappingError(details={"provider_subject_known": False})
        raise DatabaseResultError(
            "map_identity reported an error", details={"code": error.get("code")}
        )


class FakeIdentityMapper:
    """In-memory mapping for tests. `allow_provision=True` mints ids on demand."""

    def __init__(self, *, allow_provision: bool = False) -> None:
        self._allow_provision = allow_provision
        self._mappings: dict[str, InternalIdentity] = {}

    def add_mapping(self, provider_subject: str, *, user_id: str, tenant_id: str) -> None:
        self._mappings[provider_subject] = InternalIdentity(user_id=user_id, tenant_id=tenant_id)

    async def map_identity(self, *, provider_subject: str, email: str | None) -> InternalIdentity:
        existing = self._mappings.get(provider_subject)
        if existing is not None:
            return existing
        if not self._allow_provision:
            raise IdentityMappingError(details={"provider_subject_known": False})
        identity = InternalIdentity(user_id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()))
        self._mappings[provider_subject] = identity
        return identity


if TYPE_CHECKING:
    _proof_pg: IdentityMapperProtocol = AsyncpgIdentityMapper(None)
    _proof_fake: IdentityMapperProtocol = FakeIdentityMapper()
