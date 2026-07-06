"""Offset pagination primitives shared by list endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


class PageParams(BaseModel):
    """Query-side pagination input."""

    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)


class PageMeta(BaseModel):
    """Pagination block carried in the `meta` of paginated success envelopes."""

    limit: int
    offset: int
    total: int


def page_meta(params: PageParams, total: int) -> dict[str, Any]:
    """Meta fragment for `api_success(items, meta=page_meta(params, total))`."""
    return {
        "pagination": PageMeta(limit=params.limit, offset=params.offset, total=total).model_dump()
    }
