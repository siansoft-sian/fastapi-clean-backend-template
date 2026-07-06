"""In-memory fake for the ExampleRepository port — the template's fast-test path.

No I/O of any kind. Unit tests of services depending on this port inject the
fake; the asyncpg adapter is exercised only by integration-marked tests.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.modules._example.ports.example_repository import ExampleItemDTO

if TYPE_CHECKING:
    from app.modules._example.ports.example_repository import ExampleRepositoryProtocol


class FakeExampleRepository:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ExampleItemDTO] = {}

    async def create(self, *, tenant_id: str, name: str) -> ExampleItemDTO:
        item = ExampleItemDTO(id=uuid.uuid4().hex, tenant_id=tenant_id, name=name)
        self._items[(tenant_id, item.id)] = item
        return item

    async def get(self, *, tenant_id: str, item_id: str) -> ExampleItemDTO | None:
        return self._items.get((tenant_id, item_id))

    async def list_for_tenant(self, *, tenant_id: str) -> list[ExampleItemDTO]:
        items = [item for (t, _), item in self._items.items() if t == tenant_id]
        return sorted(items, key=lambda item: item.name)


# mypy-only structural proof that the fake satisfies the same port.
def _static_protocol_check(repo: FakeExampleRepository) -> ExampleRepositoryProtocol:
    return repo
