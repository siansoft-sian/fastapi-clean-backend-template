"""Opaque session-token primitives. Pure: no FastAPI, no I/O.

The cookie carries a high-entropy random token — deliberately NOT a UUID and
NOT time-ordered: unpredictability is the security property. The database
stores and looks up only `sha256(token)`; the raw token never reaches SQL
(see database/postgres/DESIGN-sessions-identity.md).
"""

import hashlib
import secrets


def generate_session_token() -> str:
    """High-entropy opaque token for the session cookie (~43 url-safe chars)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> bytes:
    """The 32-byte sha256 digest that is the database's ONLY lookup key."""
    return hashlib.sha256(token.encode("utf-8")).digest()
