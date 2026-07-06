"""Typed scope constants.

Scope POPULATION (how a principal earns scopes) arrives with the M4
authorization milestone (Casbin); routes may already guard with
`require_scope(SCOPE_...)` using these constants.
"""

from typing import Final

SCOPE_TENANT_READ: Final = "tenant:read"
SCOPE_TENANT_WRITE: Final = "tenant:write"
SCOPE_TENANT_ADMIN: Final = "tenant:admin"

ALL_SCOPES: Final = frozenset({SCOPE_TENANT_READ, SCOPE_TENANT_WRITE, SCOPE_TENANT_ADMIN})
