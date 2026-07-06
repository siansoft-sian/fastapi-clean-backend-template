"""Server-side session storage — M2 repository pattern.

Port (`SessionRepositoryProtocol`) + asyncpg adapter calling the Postgres
functions documented in `database/postgres/functions/README.md` + in-memory
fake for fast tests. Sessions carry the GoTrue tokens (SecretStr in Python,
pgcrypto-encrypted at rest in Postgres); the browser only ever sees the
opaque `id`.

`get` returns revoked/expired sessions as data — VALIDITY decisions belong to
the dependency layer, which can then distinguish 'invalid' from 'expired'.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

import asyncpg
from pydantic import SecretStr

from app.core.errors.core_errors import DatabaseResultError
from app.db.dto_base import RepositoryDTO
from app.db.errors import map_asyncpg_error

SESSION_NOT_FOUND = "SESSION_NOT_FOUND"


class SessionDTO(RepositoryDTO):
    id: str
    user_id: str
    tenant_id: str
    email: str | None = None
    gotrue_access_token: SecretStr
    gotrue_refresh_token: SecretStr
    absolute_expires_at: datetime
    idle_expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None


class SessionRepositoryProtocol(Protocol):
    async def create(
        self,
        *,
        user_id: str,
        tenant_id: str,
        access_token: str,
        refresh_token: str,
        absolute_ttl_seconds: int,
        idle_ttl_seconds: int,
        email: str | None = None,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> SessionDTO: ...

    async def get(self, *, session_id: str) -> SessionDTO | None: ...

    async def touch(self, *, session_id: str, idle_ttl_seconds: int) -> SessionDTO | None: ...

    async def rotate(
        self,
        *,
        session_id: str,
        access_token: str,
        refresh_token: str,
        idle_ttl_seconds: int,
    ) -> SessionDTO | None: ...

    async def revoke(self, *, session_id: str) -> None: ...


def _is_uuid(value: str) -> bool:
    """Cookie values are attacker-controlled; reject non-uuids before SQL."""
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


class AsyncpgSessionRepository:
    """Calls the app.*_user_session Postgres functions (envelope-returning)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        *,
        user_id: str,
        tenant_id: str,
        access_token: str,
        refresh_token: str,
        absolute_ttl_seconds: int,
        idle_ttl_seconds: int,
        email: str | None = None,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> SessionDTO:
        data = await self._call(
            "SELECT app.create_user_session($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            uuid.UUID(user_id),
            uuid.UUID(tenant_id),
            email,
            access_token,
            refresh_token,
            absolute_ttl_seconds,
            idle_ttl_seconds,
            user_agent,
            ip,
        )
        if data is None:
            raise DatabaseResultError("create_user_session returned no session")
        return SessionDTO(**data)

    async def get(self, *, session_id: str) -> SessionDTO | None:
        if not _is_uuid(session_id):
            return None
        data = await self._call("SELECT app.get_user_session($1)", uuid.UUID(session_id))
        return SessionDTO(**data) if data is not None else None

    async def touch(self, *, session_id: str, idle_ttl_seconds: int) -> SessionDTO | None:
        if not _is_uuid(session_id):
            return None
        data = await self._call(
            "SELECT app.touch_user_session($1, $2)", uuid.UUID(session_id), idle_ttl_seconds
        )
        return SessionDTO(**data) if data is not None else None

    async def rotate(
        self,
        *,
        session_id: str,
        access_token: str,
        refresh_token: str,
        idle_ttl_seconds: int,
    ) -> SessionDTO | None:
        if not _is_uuid(session_id):
            return None
        data = await self._call(
            "SELECT app.rotate_user_session($1, $2, $3, $4)",
            uuid.UUID(session_id),
            access_token,
            refresh_token,
            idle_ttl_seconds,
        )
        return SessionDTO(**data) if data is not None else None

    async def revoke(self, *, session_id: str) -> None:
        if not _is_uuid(session_id):
            return
        await self._call("SELECT app.revoke_user_session($1)", uuid.UUID(session_id))

    async def _call(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Run an envelope-returning function; None on SESSION_NOT_FOUND."""
        try:
            raw = await self._pool.fetchval(query, *args)
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc
        envelope = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(envelope, dict):
            raise DatabaseResultError("Session function returned a non-envelope result")
        if envelope.get("success"):
            data = envelope.get("data") or {}
            session = data.get("session")
            return session if isinstance(session, dict) else None
        error = envelope.get("error") or {}
        if error.get("code") == SESSION_NOT_FOUND:
            return None
        raise DatabaseResultError(
            "Session function reported an error",
            details={"code": error.get("code")},
        )


class FakeSessionRepository:
    """In-memory sessions for fast tests. Same contract, injectable clock."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sessions: dict[str, SessionDTO] = {}

    async def create(
        self,
        *,
        user_id: str,
        tenant_id: str,
        access_token: str,
        refresh_token: str,
        absolute_ttl_seconds: int,
        idle_ttl_seconds: int,
        email: str | None = None,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> SessionDTO:
        now = self._clock()
        absolute = now + timedelta(seconds=absolute_ttl_seconds)
        session = SessionDTO(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            email=email,
            gotrue_access_token=SecretStr(access_token),
            gotrue_refresh_token=SecretStr(refresh_token),
            absolute_expires_at=absolute,
            idle_expires_at=min(now + timedelta(seconds=idle_ttl_seconds), absolute),
            created_at=now,
            revoked_at=None,
        )
        self._sessions[session.id] = session
        return session

    async def get(self, *, session_id: str) -> SessionDTO | None:
        return self._sessions.get(session_id)

    async def touch(self, *, session_id: str, idle_ttl_seconds: int) -> SessionDTO | None:
        session = self._sessions.get(session_id)
        if session is None or session.revoked_at is not None:
            return None
        now = self._clock()
        updated = session.model_copy(
            update={
                "idle_expires_at": min(
                    now + timedelta(seconds=idle_ttl_seconds), session.absolute_expires_at
                )
            }
        )
        self._sessions[session_id] = updated
        return updated

    async def rotate(
        self,
        *,
        session_id: str,
        access_token: str,
        refresh_token: str,
        idle_ttl_seconds: int,
    ) -> SessionDTO | None:
        old = self._sessions.get(session_id)
        if old is None or old.revoked_at is not None:
            return None
        now = self._clock()
        self._sessions[session_id] = old.model_copy(update={"revoked_at": now})
        new = SessionDTO(
            id=str(uuid.uuid4()),
            user_id=old.user_id,
            tenant_id=old.tenant_id,
            email=old.email,
            gotrue_access_token=SecretStr(access_token),
            gotrue_refresh_token=SecretStr(refresh_token),
            absolute_expires_at=old.absolute_expires_at,
            idle_expires_at=min(now + timedelta(seconds=idle_ttl_seconds), old.absolute_expires_at),
            created_at=now,
            revoked_at=None,
        )
        self._sessions[new.id] = new
        return new

    async def revoke(self, *, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None and session.revoked_at is None:
            self._sessions[session_id] = session.model_copy(update={"revoked_at": self._clock()})


if TYPE_CHECKING:
    # mypy-only structural proof that both implementations satisfy the port.
    _proof_pg: SessionRepositoryProtocol = AsyncpgSessionRepository(None)
    _proof_fake: SessionRepositoryProtocol = FakeSessionRepository()
