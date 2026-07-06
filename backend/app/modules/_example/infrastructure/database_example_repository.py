"""asyncpg adapter for the ExampleRepository port.

Throwaway-module shortcuts, called out so real modules don't copy them:
- `ensure_schema()` runs CREATE TABLE IF NOT EXISTS inline. Real modules get
  their schema from migrations under `database/postgres/migrations/` (applied
  via sqitch — see the sqitch-migration-engineer skill), and their
  repositories call the DB functions those migrations create.
- ids are TEXT uuid4 hexes generated in Python, to keep the demo type-free.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import asyncpg

from app.core.errors.core_errors import DatabaseResultError
from app.db.dto_base import record_to_dict
from app.db.errors import map_asyncpg_error
from app.modules._example.ports.example_repository import ExampleItemDTO

if TYPE_CHECKING:
    from app.modules._example.ports.example_repository import ExampleRepositoryProtocol


class DatabaseExampleRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_schema(self) -> None:
        try:
            await self._pool.execute(
                """
                CREATE TABLE IF NOT EXISTS _example_items (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL
                )
                """
            )
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc

    async def create(self, *, tenant_id: str, name: str) -> ExampleItemDTO:
        item_id = uuid.uuid4().hex
        try:
            record = await self._pool.fetchrow(
                """
                INSERT INTO _example_items (id, tenant_id, name)
                VALUES ($1, $2, $3)
                RETURNING id, tenant_id, name
                """,
                item_id,
                tenant_id,
                name,
            )
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc
        if record is None:
            raise DatabaseResultError("INSERT ... RETURNING produced no row")
        return ExampleItemDTO(**record_to_dict(record))

    async def get(self, *, tenant_id: str, item_id: str) -> ExampleItemDTO | None:
        try:
            record = await self._pool.fetchrow(
                """
                SELECT id, tenant_id, name
                FROM _example_items
                WHERE tenant_id = $1 AND id = $2
                """,
                tenant_id,
                item_id,
            )
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc
        if record is None:
            return None
        return ExampleItemDTO(**record_to_dict(record))

    async def list_for_tenant(self, *, tenant_id: str) -> list[ExampleItemDTO]:
        try:
            records = await self._pool.fetch(
                """
                SELECT id, tenant_id, name
                FROM _example_items
                WHERE tenant_id = $1
                ORDER BY name
                """,
                tenant_id,
            )
        except asyncpg.PostgresError as exc:
            raise map_asyncpg_error(exc) from exc
        return [ExampleItemDTO(**record_to_dict(record)) for record in records]


# mypy-only structural proof that the adapter satisfies the port.
def _static_protocol_check(repo: DatabaseExampleRepository) -> ExampleRepositoryProtocol:
    return repo
