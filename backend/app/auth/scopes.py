"""Canonical scope constants — the Layer-1 route-gate currency (final, M4).

A scope is `object.action`; the format lives in
`app.authorization.permission_actions.scope_for` and these constants are
derived from the same registry, so gate strings can never drift from the
policy vocabulary. Scopes are computed from the actor's roles against the
policy (`AuthorizationService.compute_scopes`) at session creation/refresh
and cached on AuthContext; the service-layer check remains authoritative.
"""

from typing import Final

from app.authorization import permission_actions as pa

BOOKING_CREATE: Final = pa.scope_for(pa.BOOKING, pa.CREATE)
BOOKING_READ: Final = pa.scope_for(pa.BOOKING, pa.READ)
BOOKING_UPDATE: Final = pa.scope_for(pa.BOOKING, pa.UPDATE)
BOOKING_DELETE: Final = pa.scope_for(pa.BOOKING, pa.DELETE)
BOOKING_APPROVE: Final = pa.scope_for(pa.BOOKING, pa.APPROVE)
BOOKING_CANCEL: Final = pa.scope_for(pa.BOOKING, pa.CANCEL)

EVENT_CREATE: Final = pa.scope_for(pa.EVENT, pa.CREATE)
EVENT_READ: Final = pa.scope_for(pa.EVENT, pa.READ)
EVENT_UPDATE: Final = pa.scope_for(pa.EVENT, pa.UPDATE)
EVENT_DELETE: Final = pa.scope_for(pa.EVENT, pa.DELETE)

PROFILE_READ: Final = pa.scope_for(pa.PROFILE, pa.READ)
PROFILE_UPDATE: Final = pa.scope_for(pa.PROFILE, pa.UPDATE)

PAYMENT_READ: Final = pa.scope_for(pa.PAYMENT, pa.READ)
PAYMENT_REFUND: Final = pa.scope_for(pa.PAYMENT, pa.REFUND)
