"""Server-side session storage over the sqitch DB contract (M2 repository pattern).

Contract: database/postgres/DESIGN-sessions-identity.md. The cookie carries a
high-entropy opaque token; this adapter passes ONLY sha256(token) to the
database. GoTrue tokens are encrypted app-side (Decision A, injected
TokenCipher) before storage and decrypted after fetch; ciphertext travels
hex-encoded inside the jsonb envelope.

VALIDITY is decided by the database: `get`/`touch`/`rotate` raise the typed
auth exceptions mapped from the DB error codes (SESSION_NOT_FOUND /
SESSION_REVOKED -> InvalidSessionError, SESSION_EXPIRED ->
SessionExpiredError). `revoke` is idempotent and never raises for missing or
already-revoked sessions.
"""

from __future__ import annotations

import ipaddress
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, NoReturn, Protocol

import asyncpg
from pydantic import SecretStr

from app.auth.exceptions import (
    IdentityMappingError,
    InvalidSessionError,
    SessionExpiredError,
)
from app.auth.session_tokens import hash_session_token
from app.auth.token_cipher import TokenCipher
from app.core.errors.core_errors import DatabaseResultError
from app.db.dto_base import RepositoryDTO
from app.db.errors import map_asyncpg_error


class ActiveSessionDTO(RepositoryDTO):
    session_internal_id: str
    user_id: str
    tenant_id: str
    email: str | None = None
    gotrue_access_token: SecretStr
    gotrue_refresh_token: SecretStr
    gotrue_expires_at: datetime | None = None
    absolute_expires_at: datetime
    idle_expires_at: datetime


class CreatedSessionDTO(RepositoryDTO):
    session_internal_id: str
    absolute_expires_at: datetime
    idle_expires_at: datetime


class SessionRepositoryProtocol(Protocol):
    async def create(
        self,
        *,
        session_token: str,
        user_id: str,
        tenant_id: str,
        access_token: str,
        refresh_token: str,
        gotrue_expires_at: datetime | None,
        absolute_ttl_seconds: int,
        idle_ttl_seconds: int,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> CreatedSessionDTO: ...

    async def get(self, *, session_token: str) -> ActiveSessionDTO: ...

    async def touch(self, *, session_token: str, idle_ttl_seconds: int) -> datetime: ...

    async def rotate(
        self,
        *,
        old_session_token: str,
        new_session_token: str,
        access_token: str,
        refresh_token: str,
        gotrue_expires_at: datetime | None,
        idle_ttl_seconds: int,
    ) -> CreatedSessionDTO: ...

    async def revoke(self, *, session_token: str) -> None: ...

    async def revoke_all(self, *, user_id: str, tenant_id: str) -> int: ...


def raise_for_db_code(code: str | None) -> NoReturn:
    """Translate a DB envelope error code into the auth exception taxonomy."""
    if code in ("SESSION_NOT_FOUND", "SESSION_REVOKED"):
        raise InvalidSessionError(details={"db_code": code})
    if code == "SESSION_EXPIRED":
        raise SessionExpiredError()
    if code in ("TENANT_NOT_FOUND", "USER_NOT_IN_TENANT"):
        raise IdentityMappingError(details={"db_code": code})
    raise DatabaseResultError(
        "Session function reported an unexpected error", details={"code": code}
    )


def _parse_ip(ip: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if ip is None:
        return None
    try:
        return ipaddress.ip_address(ip)
    except ValueError:
        return None  # audit-only field; never fail a login over a weird ip string


class AsyncpgSessionRepository:
    """Calls the app.*_user_session functions from the sqitch contract."""

    def __init__(self, pool: asyncpg.Pool, cipher: TokenCipher) -> None:
        self._pool = pool
        self._cipher = cipher

    async def create(
        self,
        *,
        session_token: str,
        user_id: str,
        tenant_id: str,
        access_token: str,
        refresh_token: str,
        gotrue_expires_at: datetime | None,
        absolute_ttl_seconds: int,
        idle_ttl_seconds: int,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> CreatedSessionDTO:
        data = await self._call(
            "SELECT app.create_user_session($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            hash_session_token(session_token),
            uuid.UUID(user_id),
            uuid.UUID(tenant_id),
            self._cipher.encrypt(access_token),
            self._cipher.encrypt(refresh_token),
            gotrue_expires_at,
            timedelta(seconds=absolute_ttl_seconds),
            timedelta(seconds=idle_ttl_seconds),
            user_agent,
            _parse_ip(ip),
        )
        return CreatedSessionDTO(**data)

    async def get(self, *, session_token: str) -> ActiveSessionDTO:
        data = await self._call(
            "SELECT app.get_user_session($1)", hash_session_token(session_token)
        )
        return ActiveSessionDTO(
            session_internal_id=data["session_internal_id"],
            user_id=data["user_id"],
            tenant_id=data["tenant_id"],
            email=data.get("email"),
            gotrue_access_token=SecretStr(
                self._cipher.decrypt(bytes.fromhex(data["gotrue_access_token"]))
            ),
            gotrue_refresh_token=SecretStr(
                self._cipher.decrypt(bytes.fromhex(data["gotrue_refresh_token"]))
            ),
            gotrue_expires_at=data.get("gotrue_expires_at"),
            absolute_expires_at=data["absolute_expires_at"],
            idle_expires_at=data["idle_expires_at"],
        )

    async def touch(self, *, session_token: str, idle_ttl_seconds: int) -> datetime:
        data = await self._call(
            "SELECT app.touch_user_session($1, $2)",
            hash_session_token(session_token),
            timedelta(seconds=idle_ttl_seconds),
        )
        return datetime.fromisoformat(data["idle_expires_at"])

    async def rotate(
        self,
        *,
        old_session_token: str,
        new_session_token: str,
        access_token: str,
        refresh_token: str,
        gotrue_expires_at: datetime | None,
        idle_ttl_seconds: int,
    ) -> CreatedSessionDTO:
        data = await self._call(
            "SELECT app.rotate_user_session($1, $2, $3, $4, $5, $6)",
            hash_session_token(old_session_token),
            hash_session_token(new_session_token),
            self._cipher.encrypt(access_token),
            self._cipher.encrypt(refresh_token),
            gotrue_expires_at,
            timedelta(seconds=idle_ttl_seconds),
        )
        return CreatedSessionDTO(**data)

    async def revoke(self, *, session_token: str) -> None:
        await self._call("SELECT app.revoke_user_session($1)", hash_session_token(session_token))

    async def revoke_all(self, *, user_id: str, tenant_id: str) -> int:
        data = await self._call(
            "SELECT app.revoke_all_user_sessions($1, $2)",
            uuid.UUID(user_id),
            uuid.UUID(tenant_id),
        )
        return int(data["revoked_count"])

    async def _call(self, query: str, *args: Any) -> dict[str, Any]:
        """Run an envelope function; return `data` or raise the mapped exception."""
        try:
            raw = await self._pool.fetchval(query, *args)
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc
        envelope = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(envelope, dict):
            raise DatabaseResultError("Session function returned a non-envelope result")
        if envelope.get("success"):
            data = envelope.get("data")
            return data if isinstance(data, dict) else {}
        raise_for_db_code((envelope.get("error") or {}).get("code"))


@dataclass
class _StoredSession:
    internal_id: str
    user_id: str
    tenant_id: str
    access_token: str
    refresh_token: str
    gotrue_expires_at: datetime | None
    absolute_expires_at: datetime
    idle_expires_at: datetime
    revoked_at: datetime | None = None


@dataclass
class FakeSessionRepository:
    """In-memory implementation with identical raise semantics; clock injectable.

    Email is joined from app.users in the real contract; the fake resolves it
    via `set_user_email` seeding.
    """

    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _sessions: dict[str, _StoredSession] = field(default_factory=dict)
    _emails: dict[str, str] = field(default_factory=dict)

    def set_user_email(self, user_id: str, email: str) -> None:
        self._emails[user_id] = email

    async def create(
        self,
        *,
        session_token: str,
        user_id: str,
        tenant_id: str,
        access_token: str,
        refresh_token: str,
        gotrue_expires_at: datetime | None,
        absolute_ttl_seconds: int,
        idle_ttl_seconds: int,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> CreatedSessionDTO:
        now = self.clock()
        absolute = now + timedelta(seconds=absolute_ttl_seconds)
        stored = _StoredSession(
            internal_id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            access_token=access_token,
            refresh_token=refresh_token,
            gotrue_expires_at=gotrue_expires_at,
            absolute_expires_at=absolute,
            idle_expires_at=min(now + timedelta(seconds=idle_ttl_seconds), absolute),
        )
        self._sessions[session_token] = stored
        return CreatedSessionDTO(
            session_internal_id=stored.internal_id,
            absolute_expires_at=stored.absolute_expires_at,
            idle_expires_at=stored.idle_expires_at,
        )

    def _active(self, session_token: str) -> _StoredSession:
        stored = self._sessions.get(session_token)
        if stored is None:
            raise InvalidSessionError(details={"db_code": "SESSION_NOT_FOUND"})
        if stored.revoked_at is not None:
            raise InvalidSessionError(details={"db_code": "SESSION_REVOKED"})
        now = self.clock()
        if stored.absolute_expires_at <= now or stored.idle_expires_at <= now:
            raise SessionExpiredError()
        return stored

    async def get(self, *, session_token: str) -> ActiveSessionDTO:
        stored = self._active(session_token)
        return ActiveSessionDTO(
            session_internal_id=stored.internal_id,
            user_id=stored.user_id,
            tenant_id=stored.tenant_id,
            email=self._emails.get(stored.user_id),
            gotrue_access_token=SecretStr(stored.access_token),
            gotrue_refresh_token=SecretStr(stored.refresh_token),
            gotrue_expires_at=stored.gotrue_expires_at,
            absolute_expires_at=stored.absolute_expires_at,
            idle_expires_at=stored.idle_expires_at,
        )

    async def touch(self, *, session_token: str, idle_ttl_seconds: int) -> datetime:
        stored = self._active(session_token)
        stored.idle_expires_at = min(
            self.clock() + timedelta(seconds=idle_ttl_seconds), stored.absolute_expires_at
        )
        return stored.idle_expires_at

    async def rotate(
        self,
        *,
        old_session_token: str,
        new_session_token: str,
        access_token: str,
        refresh_token: str,
        gotrue_expires_at: datetime | None,
        idle_ttl_seconds: int,
    ) -> CreatedSessionDTO:
        old = self._active(old_session_token)
        now = self.clock()
        new = _StoredSession(
            internal_id=str(uuid.uuid4()),
            user_id=old.user_id,
            tenant_id=old.tenant_id,
            access_token=access_token,
            refresh_token=refresh_token,
            gotrue_expires_at=gotrue_expires_at,
            absolute_expires_at=old.absolute_expires_at,  # never extended
            idle_expires_at=min(now + timedelta(seconds=idle_ttl_seconds), old.absolute_expires_at),
        )
        old.revoked_at = now
        self._sessions[new_session_token] = new
        return CreatedSessionDTO(
            session_internal_id=new.internal_id,
            absolute_expires_at=new.absolute_expires_at,
            idle_expires_at=new.idle_expires_at,
        )

    async def revoke(self, *, session_token: str) -> None:
        stored = self._sessions.get(session_token)
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = self.clock()

    async def revoke_all(self, *, user_id: str, tenant_id: str) -> int:
        now = self.clock()
        count = 0
        for stored in self._sessions.values():
            if (
                stored.user_id == user_id
                and stored.tenant_id == tenant_id
                and stored.revoked_at is None
                and stored.absolute_expires_at > now
                and stored.idle_expires_at > now
            ):
                stored.revoked_at = now
                count += 1
        return count


if TYPE_CHECKING:
    # mypy-only structural proof that both implementations satisfy the port.
    _proof_pg: SessionRepositoryProtocol = AsyncpgSessionRepository(None, None)  # type: ignore[arg-type]
    _proof_fake: SessionRepositoryProtocol = FakeSessionRepository()
