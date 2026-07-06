"""Opaque session-token primitives: entropy and the sha256 lookup key."""

from app.auth.session_tokens import generate_session_token, hash_session_token


def test_tokens_are_high_entropy_and_unique() -> None:
    tokens = {generate_session_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)  # 32 bytes urlsafe-b64


def test_hash_is_32_byte_sha256_and_deterministic() -> None:
    token = generate_session_token()
    digest = hash_session_token(token)
    assert isinstance(digest, bytes)
    assert len(digest) == 32  # matches the DB CHECK octet_length(token_hash) = 32
    assert digest == hash_session_token(token)
    assert digest != hash_session_token(token + "x")
