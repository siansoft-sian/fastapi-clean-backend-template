"""CSRF double-submit primitives. Pure: no FastAPI, no I/O.

The CSRF cookie is readable by the frontend (NOT HttpOnly); the frontend
echoes its value back in a header on every state-changing request. The server
compares header vs cookie in constant time — an attacker's cross-site request
can send the cookie but cannot read it to forge the header.
"""

import hmac
import secrets

_TOKEN_BYTES = 32


def generate_csrf_token() -> str:
    """Cryptographically random, URL-safe token."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def verify_csrf(header_value: str | None, cookie_value: str | None) -> bool:
    """True only when both values are present and identical (constant time)."""
    if not header_value or not cookie_value:
        return False
    return hmac.compare_digest(header_value.encode(), cookie_value.encode())
