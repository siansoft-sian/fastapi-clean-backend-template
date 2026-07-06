"""ExampleRepository port: the ONLY thing application code may depend on.

Conventions every real module must copy:
- methods are keyword-only and take `tenant_id` explicitly — repositories never
  read a contextvar/global themselves; the caller passes tenancy in
- every method returns a typed DTO (RepositoryDTO), never dict/Record
"""

from typing import Protocol

from app.db.dto_base import RepositoryDTO


class ExampleItemDTO(RepositoryDTO):
    id: str
    name: str
    tenant_id: str


class ExampleRepositoryProtocol(Protocol):
    async def create(self, *, tenant_id: str, name: str) -> ExampleItemDTO: ...

    async def get(self, *, tenant_id: str, item_id: str) -> ExampleItemDTO | None: ...

    async def list_for_tenant(self, *, tenant_id: str) -> list[ExampleItemDTO]: ...
