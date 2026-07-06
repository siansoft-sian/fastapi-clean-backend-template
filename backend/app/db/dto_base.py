"""Repository DTO conventions.

Every repository method returns a typed DTO — a subclass of `RepositoryDTO`
below (preferred) or a `@dataclass(frozen=True)`. Never a `dict`, never an
`asyncpg.Record`: rows are mapped to DTOs *inside* the repository, so the
engine's row type cannot leak past the infrastructure boundary.

`record_to_dict` may be used by repositories to flatten a Record before
constructing their DTO. It lives here (in `app/db/`) precisely because it is
allowed to know about asyncpg's row shape; application code never calls it.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict


class RepositoryDTO(BaseModel):
    """Base class for repository return types: immutable, tolerant of extra
    row columns so adding a column is not a breaking change."""

    model_config = ConfigDict(frozen=True, extra="ignore")


def record_to_dict(record: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten an asyncpg.Record (any Mapping) into a plain dict of primitives,
    for use immediately before DTO construction — never as a return value."""
    return dict(record)
