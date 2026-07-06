"""Two demo routes, one per enforcement layer.

`/approve` shows the coarse gate; `/{item_id}/edit` shows the authoritative
service check with ownership + tenant (cross-tenant → 404, hiding existence).
The in-memory DEMO_ITEMS stand in for a repository load — a real use case
builds ResourceContext from the resource it already fetched.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth import scopes
from app.auth.auth_context import AuthContext
from app.auth.dependencies import (
    AuthorizationServiceDep,
    require_authenticated,
    require_scope,
    verify_csrf,
)
from app.authorization import permission_actions as pa
from app.authorization.authorization_service import CROSS_TENANT_REASON
from app.authorization.resource_context import ResourceContext
from app.core.errors.core_errors import ForbiddenError, NotFoundError
from app.core.responses import api_success
from app.rate_limiting.dependency import rate_limit

router = APIRouter(prefix="/_authz-demo", tags=["_authz-demo"])


@dataclass(frozen=True)
class _DemoItem:
    owner_id: str
    tenant_id: str


DEMO_ITEMS = {
    "item-owned": _DemoItem(owner_id="user-owner", tenant_id="tenant-1"),
    "item-other": _DemoItem(owner_id="someone-else", tenant_id="tenant-1"),
    "item-foreign": _DemoItem(owner_id="user-owner", tenant_id="tenant-2"),
}


@router.post("/approve", dependencies=[Depends(verify_csrf)])
async def approve(
    principal: Annotated[AuthContext, Depends(require_scope(scopes.BOOKING_APPROVE))],
) -> dict[str, Any]:
    """LAYER 1 proof: the coarse scope gate rejects before any service logic runs."""
    return api_success({"approved": True, "by": principal.user_id})


@router.post(
    "/limited",
    dependencies=[Depends(verify_csrf), Depends(rate_limit("booking.create"))],
)
async def limited(
    principal: Annotated[AuthContext, Depends(require_authenticated)],
) -> dict[str, Any]:
    """M5 proof: per-USER rate limit as a post-auth dependency."""
    return api_success({"ok": True, "by": principal.user_id})


@router.post("/{item_id}/edit", dependencies=[Depends(verify_csrf)])
async def edit(
    item_id: str,
    principal: Annotated[AuthContext, Depends(require_authenticated)],
    authorization: AuthorizationServiceDep,
) -> dict[str, Any]:
    """LAYER 2 proof: ownership + tenant through the authoritative enforce()."""
    item = DEMO_ITEMS.get(item_id)
    if item is None:
        raise NotFoundError()

    ctx = ResourceContext(
        actor_user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        roles=principal.roles,
        action=pa.UPDATE,
        resource_type=pa.PROFILE,
        resource_id=item_id,
        resource_owner_id=item.owner_id,
        resource_tenant_id=item.tenant_id,
    )
    try:
        authorization.enforce(ctx)
    except ForbiddenError as exc:
        if exc.details.get("reason") == CROSS_TENANT_REASON:
            # Hide the existence of resources in other tenants.
            raise NotFoundError() from None
        raise
    return api_success({"edited": item_id, "by": principal.user_id})
