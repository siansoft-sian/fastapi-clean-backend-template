"""GoTrue identity -> internal (user_id, tenant_id, email) via app.map_identity.

Contract: database/postgres/DESIGN-sessions-identity.md. Whether an unknown
identity may be auto-provisioned is the caller's per-call `provision` flag
(wired from settings.identity_auto_provision); the tenancy model behind
provisioning is an open question (D8) owned by the identity milestone.
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

_IDENTITY_ERROR_CODES = ("IDENTITY_NOT_FOUND", "PROVISIONING_DISABLED", "NO_ACTIVE_TENANT")


class InternalIdentity(RepositoryDTO):
    user_id: str
    tenant_id: str
    email: str | None = None


class IdentityMapperProtocol(Protocol):
    async def map_identity(
        self, *, provider: str, subject: str, email: str | None, provision: bool
    ) -> InternalIdentity: ...


class AsyncpgIdentityMapper:
    """Calls app.map_identity (envelope-returning)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def map_identity(
        self, *, provider: str, subject: str, email: str | None, provision: bool
    ) -> InternalIdentity:
        try:
            raw = await self._pool.fetchval(
                "SELECT app.map_identity($1, $2, $3, $4)", provider, subject, email, provision
            )
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc
        envelope = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(envelope, dict):
            raise DatabaseResultError("map_identity returned a non-envelope result")
        if envelope.get("success"):
            data: dict[str, Any] = envelope.get("data") or {}
            return InternalIdentity(
                user_id=str(data["user_id"]),
                tenant_id=str(data["tenant_id"]),
                email=data.get("email"),
            )
        code = (envelope.get("error") or {}).get("code")
        if code in _IDENTITY_ERROR_CODES:
            raise IdentityMappingError(details={"db_code": code})
        raise DatabaseResultError("map_identity reported an error", details={"code": code})


class FakeIdentityMapper:
    """In-memory mapping honoring the per-call `provision` flag."""

    def __init__(self) -> None:
        self._mappings: dict[tuple[str, str], InternalIdentity] = {}

    def add_mapping(
        self,
        provider: str,
        subject: str,
        *,
        user_id: str,
        tenant_id: str,
        email: str | None = None,
    ) -> None:
        self._mappings[(provider, subject)] = InternalIdentity(
            user_id=user_id, tenant_id=tenant_id, email=email
        )

    async def map_identity(
        self, *, provider: str, subject: str, email: str | None, provision: bool
    ) -> InternalIdentity:
        existing = self._mappings.get((provider, subject))
        if existing is not None:
            return existing
        if not provision:
            raise IdentityMappingError(details={"db_code": "IDENTITY_NOT_FOUND"})
        identity = InternalIdentity(
            user_id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()), email=email
        )
        self._mappings[(provider, subject)] = identity
        return identity


if TYPE_CHECKING:
    _proof_pg: IdentityMapperProtocol = AsyncpgIdentityMapper(None)
    _proof_fake: IdentityMapperProtocol = FakeIdentityMapper()
