"""GoTrue JWT verification: signature (via JWKS), iss, aud, exp/nbf.

Pure except for the injected JwksClient. Only asymmetric algorithms are
accepted (RS256/ES256) — `none`/HMAC are rejected before any key lookup.
This verifies the SERVER-HELD access token; browsers never send Bearer tokens
in the BFF model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import jwt

from app.auth.exceptions import TokenVerificationError
from app.auth.jwks_client import JwksClient

_ALLOWED_ALGORITHMS = ("RS256", "ES256")


@dataclass(frozen=True)
class VerifiedToken:
    sub: str
    email: str | None
    claims: Mapping[str, Any]


class JwtVerifier:
    def __init__(self, *, jwks_client: JwksClient, issuer: str, audience: str) -> None:
        self._jwks_client = jwks_client
        self._issuer = issuer
        self._audience = audience

    async def verify(self, token: str) -> VerifiedToken:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise TokenVerificationError("Malformed token") from exc

        algorithm = header.get("alg")
        if algorithm not in _ALLOWED_ALGORITHMS:
            raise TokenVerificationError(
                "Disallowed signing algorithm", details={"alg": str(algorithm)}
            )
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenVerificationError("Token has no key id")

        signing_key = jwt.PyJWK(await self._jwks_client.get_key(kid)).key
        try:
            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=list(_ALLOWED_ALGORITHMS),
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "sub"]},
            )
        except jwt.InvalidTokenError as exc:
            # exp/nbf/iss/aud/signature failures all land here; the reason is
            # safe to expose (no token material).
            raise TokenVerificationError(
                "Token verification failed", details={"reason": type(exc).__name__}
            ) from exc

        email = claims.get("email")
        return VerifiedToken(
            sub=claims["sub"],
            email=email if isinstance(email, str) else None,
            claims=claims,
        )
