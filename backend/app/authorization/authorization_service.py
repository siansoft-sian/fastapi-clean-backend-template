"""AuthorizationService — the two enforcement layers (D5). Pure: no FastAPI.

- `enforce(ctx)` is Layer 2 and AUTHORITATIVE: ownership, assignment, tenant
  scoping, and deny rules all live in one Casbin call. It raises ForbiddenError
  on denial — never returns a bool a caller could forget to check.
- `has_scope(...)` backs only the Layer-1 route gate (a coarse pre-filter).
- `compute_scopes(...)` derives the coarse scope cache FROM THE SAME POLICY,
  so the gate can never grant something the fine check would structure
  differently (a stale-but-broader scope set is always backstopped by Layer 2).
"""

from __future__ import annotations

from typing import Protocol

import structlog

from app.authorization import permission_actions
from app.authorization.casbin_enforcer import (
    CasbinEnforcer,
    EnforcerResource,
    EnforcerSubject,
)
from app.authorization.resource_context import ResourceContext
from app.core.errors.core_errors import ForbiddenError

logger = structlog.get_logger(__name__)

CROSS_TENANT_REASON = "cross_tenant"


class HasScopes(Protocol):
    """Structural view of a principal — avoids importing the auth package."""

    @property
    def scopes(self) -> frozenset[str]: ...


class AuthorizationService:
    def __init__(self, enforcer: CasbinEnforcer) -> None:
        self._enforcer = enforcer

    def enforce(self, ctx: ResourceContext) -> None:
        """Authoritative fine-grained check; raises ForbiddenError on denial.

        Cross-tenant resources are rejected before the matcher ever runs; the
        caller maps that ForbiddenError (details.reason == "cross_tenant") to
        a 404 wherever resource existence must be hidden.
        """
        if ctx.resource_tenant_id is not None and ctx.resource_tenant_id != ctx.tenant_id:
            logger.warning(
                "authorization_cross_tenant_denied",
                module="authorization",
                operation="enforce",
                resource_type=ctx.resource_type,
                action=ctx.action,
            )
            raise ForbiddenError("Resource not accessible", details={"reason": CROSS_TENANT_REASON})

        allowed = self._enforcer.enforce(
            EnforcerSubject(id=ctx.actor_user_id, roles=tuple(sorted(ctx.roles))),
            ctx.tenant_id,
            EnforcerResource(
                type=ctx.resource_type,
                owner_id=ctx.resource_owner_id or "",
                assigned=tuple(sorted(ctx.assigned_user_ids)),
                tenant=ctx.resource_tenant_id or "",
            ),
            ctx.action,
        )
        if not allowed:
            logger.warning(
                "authorization_denied",
                module="authorization",
                operation="enforce",
                resource_type=ctx.resource_type,
                action=ctx.action,
            )
            raise ForbiddenError(details={"resource_type": ctx.resource_type, "action": ctx.action})

    def has_scope(self, principal: HasScopes, scope: str) -> bool:
        """Layer-1 coarse check only — never sufficient for instance decisions."""
        return scope in principal.scopes

    def compute_scopes(self, roles: frozenset[str], tenant_id: str) -> frozenset[str]:
        """Coarse `object.action` set the roles grant, ignoring instance conditions.

        Used at session creation/refresh (M3) to cache scopes on AuthContext.
        `tenant_id` is accepted for future tenant-specific policies; the
        current policy set is tenant-uniform.
        """
        scopes: set[str] = set()
        for rule in self._enforcer.policy_rules():
            role, obj_type, act, _cond, effect = (rule + [""] * 5)[:5]
            if effect != "allow":
                continue
            if role != "*" and role not in roles:
                continue
            resource_types = (
                permission_actions.ALL_RESOURCE_TYPES if obj_type == "*" else {obj_type}
            )
            for resource_type in resource_types:
                actions = (
                    permission_actions.ACTIONS_BY_RESOURCE.get(resource_type, frozenset())
                    if act == "*"
                    else {act}
                )
                for action in actions:
                    scopes.add(permission_actions.scope_for(resource_type, action))
        return frozenset(scopes)
