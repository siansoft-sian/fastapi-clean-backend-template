"""Public envelope helpers: every response body is `{success, data, error, meta}`."""

from __future__ import annotations

from typing import Any

from app.core.errors.error_envelope import build_envelope, redact_sensitive


def api_success(data: Any = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Standard success envelope."""
    return build_envelope(success=True, data=data, error=None, meta=meta)


def api_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard error envelope. Credential-like keys in `details` are always redacted."""
    error = {"code": code, "message": message, "details": redact_sensitive(details or {})}
    return build_envelope(success=False, data=None, error=error, meta=meta)
