"""JwtVerifier against a real RSA test key: valid passes, everything else rejected."""

import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.exceptions import TokenVerificationError
from app.auth.jwt_verifier import JwtVerifier

ISSUER = "https://project.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key-1"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_other_pem = _other_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)


def public_jwk() -> dict[str, Any]:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_private_key.public_key()))
    jwk["kid"] = KID
    jwk["alg"] = "RS256"
    return jwk


class StubJwksClient:
    """Serves the test JWK without any network."""

    def __init__(self, keys: dict[str, dict[str, Any]]) -> None:
        self._keys = keys

    async def get_key(self, kid: str) -> dict[str, Any]:
        key = self._keys.get(kid)
        if key is None:
            raise TokenVerificationError("Unknown signing key", details={"kid": kid})
        return key


def make_verifier() -> JwtVerifier:
    return JwtVerifier(
        jwks_client=StubJwksClient({KID: public_jwk()}),  # type: ignore[arg-type]
        issuer=ISSUER,
        audience=AUDIENCE,
    )


def make_token(*, key: bytes = _private_pem, kid: str = KID, **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "sub": "gotrue-user-123",
        "email": "user@example.com",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


async def test_valid_token_returns_verified_claims() -> None:
    verified = await make_verifier().verify(make_token())
    assert verified.sub == "gotrue-user-123"
    assert verified.email == "user@example.com"
    assert verified.claims["aud"] == AUDIENCE


async def test_expired_token_rejected() -> None:
    token = make_token(exp=int(time.time()) - 10)
    with pytest.raises(TokenVerificationError) as exc_info:
        await make_verifier().verify(token)
    assert exc_info.value.details["reason"] == "ExpiredSignatureError"


async def test_not_yet_valid_token_rejected() -> None:
    token = make_token(nbf=int(time.time()) + 300)
    with pytest.raises(TokenVerificationError):
        await make_verifier().verify(token)


async def test_wrong_audience_rejected() -> None:
    token = make_token(aud="somebody-else")
    with pytest.raises(TokenVerificationError):
        await make_verifier().verify(token)


async def test_wrong_issuer_rejected() -> None:
    token = make_token(iss="https://evil.example")
    with pytest.raises(TokenVerificationError):
        await make_verifier().verify(token)


async def test_token_signed_by_another_key_rejected() -> None:
    token = make_token(key=_other_pem)  # same kid, wrong key -> bad signature
    with pytest.raises(TokenVerificationError):
        await make_verifier().verify(token)


async def test_tampered_payload_rejected() -> None:
    header, payload, signature = make_token().split(".")
    tampered = ".".join(
        [header, payload[:-2] + ("AA" if payload[-2:] != "AA" else "BB"), signature]
    )
    with pytest.raises(TokenVerificationError):
        await make_verifier().verify(tampered)


async def test_hmac_algorithm_rejected_before_key_lookup() -> None:
    token = jwt.encode({"sub": "x", "exp": int(time.time()) + 300}, "s" * 32, algorithm="HS256")
    with pytest.raises(TokenVerificationError) as exc_info:
        await make_verifier().verify(token)
    assert exc_info.value.details.get("alg") == "HS256"


async def test_missing_kid_rejected() -> None:
    token = jwt.encode(
        {"sub": "x", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300},
        _private_pem,
        algorithm="RS256",
    )
    with pytest.raises(TokenVerificationError):
        await make_verifier().verify(token)


async def test_garbage_token_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        await make_verifier().verify("not.a.jwt")
