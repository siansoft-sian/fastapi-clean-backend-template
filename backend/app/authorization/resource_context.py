"""ResourceContext — every input a fine-grained authorization decision needs. Pure.

The USE CASE populates this from the resource it already loaded (owner,
assignees, resource tenant) plus the principal; the authorization layer never
fetches data itself. `tenant_id` is the actor's active tenant and is always
required — cross-tenant resources are denied (surfaced as 404 upstream).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResourceContext:
    actor_user_id: str
    tenant_id: str
    roles: frozenset[str]
    action: str  # from permission_actions
    resource_type: str  # from permission_actions
    resource_id: str | None = None
    resource_owner_id: str | None = None  # ownership rules (rule 4)
    assigned_user_ids: frozenset[str] = field(default_factory=frozenset)  # rule 3
    resource_tenant_id: str | None = None  # must equal tenant_id when present
