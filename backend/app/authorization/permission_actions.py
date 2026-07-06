"""Action + object-type constants and the canonical scope format. Pure.

A scope is ``f"{object_type}.{action}"`` — `scope_for` is the ONLY place that
format lives. `ACTIONS_BY_RESOURCE` is the registry `compute_scopes` uses to
expand policy wildcards into concrete scopes.
"""

from typing import Final

# --- actions ---
CREATE: Final = "create"
READ: Final = "read"
UPDATE: Final = "update"
DELETE: Final = "delete"
APPROVE: Final = "approve"
CANCEL: Final = "cancel"
REFUND: Final = "refund"

# --- object types ---
BOOKING: Final = "booking"
EVENT: Final = "event"
PROFILE: Final = "profile"
PAYMENT: Final = "payment"

ACTIONS_BY_RESOURCE: Final[dict[str, frozenset[str]]] = {
    BOOKING: frozenset({CREATE, READ, UPDATE, DELETE, APPROVE, CANCEL}),
    EVENT: frozenset({CREATE, READ, UPDATE, DELETE}),
    PROFILE: frozenset({READ, UPDATE}),
    PAYMENT: frozenset({READ, REFUND}),
}

ALL_RESOURCE_TYPES: Final = frozenset(ACTIONS_BY_RESOURCE)


def scope_for(resource_type: str, action: str) -> str:
    """The canonical `object.action` scope string."""
    return f"{resource_type}.{action}"
