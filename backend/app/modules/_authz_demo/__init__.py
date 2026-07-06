"""_authz_demo — throwaway proof of two-layer authorization (D5).

NOT a business module (like M2's _example): it exists so the first real
module can copy the pattern —

    Layer 1: Depends(require_scope(scopes.X)) on the route (coarse pre-filter)
    Layer 2: the use case builds ResourceContext from the loaded resource and
             calls AuthorizationService.enforce(...) — AUTHORITATIVE
             (ownership, assignment, tenant; cross-tenant surfaces as 404)

Kept as a documented reference; delete once the first real module lands.
"""
