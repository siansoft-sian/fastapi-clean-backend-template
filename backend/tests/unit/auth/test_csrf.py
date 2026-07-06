"""CSRF primitives: randomness, and strict constant-time double-submit checks."""

from app.auth.csrf import generate_csrf_token, verify_csrf


def test_tokens_are_nonempty_and_unique() -> None:
    tokens = {generate_csrf_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(token) >= 32 for token in tokens)


def test_verify_accepts_exact_match_only() -> None:
    token = generate_csrf_token()
    assert verify_csrf(token, token) is True
    assert verify_csrf(token, token + "x") is False
    assert verify_csrf(token.upper(), token) is False


def test_verify_rejects_missing_or_empty_values() -> None:
    token = generate_csrf_token()
    assert verify_csrf(None, token) is False
    assert verify_csrf(token, None) is False
    assert verify_csrf("", token) is False
    assert verify_csrf(token, "") is False
    assert verify_csrf(None, None) is False
    assert verify_csrf("", "") is False
