"""PKCE (RFC 7636) + OAuth state primitives. Pure: no FastAPI, no I/O.

The verifier and state survive the authorize round-trip inside a short-lived
HttpOnly cookie (`pack_state_payload`/`unpack_state_payload`); there is no
session yet at that point in the flow. The payload is opaque to the client —
tampering only breaks the tamperer's own login, and `state` is additionally
matched against the value GoTrue echoes back.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets


def generate_code_verifier() -> str:
    """43–128 chars of URL-safe randomness (RFC 7636 §4.1)."""
    return secrets.token_urlsafe(64)


def code_challenge_s256(verifier: str) -> str:
    """S256 challenge: BASE64URL(SHA256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def pack_state_payload(*, state: str, verifier: str) -> str:
    """Encode state+verifier for the HttpOnly PKCE cookie."""
    payload = json.dumps({"state": state, "verifier": verifier}).encode()
    return base64.urlsafe_b64encode(payload).decode("ascii")


def unpack_state_payload(raw: str | None) -> tuple[str, str] | None:
    """Decode the PKCE cookie -> (state, verifier); None when absent/corrupt."""
    if not raw:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
        state, verifier = payload["state"], payload["verifier"]
    except (ValueError, KeyError, TypeError, binascii.Error):
        return None
    if not isinstance(state, str) or not isinstance(verifier, str):
        return None
    return state, verifier


def states_match(expected: str, received: str | None) -> bool:
    """Constant-time state comparison for the OAuth callback."""
    if not received:
        return False
    return hmac.compare_digest(expected.encode(), received.encode())
