"""Canonical envelope construction and redaction. Framework-free.

This module is the single source of truth for the `{success, data, error, meta}`
shape. `app/core/responses.py` exposes the public helpers built on top of it.
"""

from __future__ import annotations

from typing import Any

from app.core.context import get_request_id

REDACTED = "[REDACTED]"
_SENSITIVE_KEY_FRAGMENTS = ("token", "password", "secret", "authorization")


def redact_sensitive(details: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `details` with credential-like keys masked, recursively."""
    safe: dict[str, Any] = {}
    for key, value in details.items():
        if any(fragment in key.lower() for fragment in _SENSITIVE_KEY_FRAGMENTS):
            safe[key] = REDACTED
        else:
            safe[key] = _redact_value(value)
    return safe


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact_sensitive(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def build_meta(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Meta block common to every envelope; `request_id` is always present."""
    meta: dict[str, Any] = {"request_id": get_request_id()}
    if extra:
        meta.update(extra)
    return meta


def build_envelope(
    *,
    success: bool,
    data: Any,
    error: dict[str, Any] | None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The one place that knows the envelope keys. Do not hand-build envelopes."""
    return {"success": success, "data": data, "error": error, "meta": build_meta(meta)}
