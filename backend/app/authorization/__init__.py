"""Authorization — Casbin two-layer enforcement (locked decision D5).

Layer 1 (coarse): `require_scope(...)` route dependency rejects early when the
actor's roles can't perform that object.action at all.
Layer 2 (fine, AUTHORITATIVE): use cases build a ResourceContext and call
AuthorizationService.enforce(...) — ownership, assignment, tenant scoping, and
deny rules live here, and it also covers non-HTTP paths (jobs).

Pure package: no FastAPI imports (enforced by import-linter). The model and
policy files are authored by the casbin-policy-engineer skill; role data comes
from the database (identity/RBAC milestone) via AuthContext.
"""
