"""PKCE math: RFC 7636 verifier/challenge, state cookie pack/unpack round-trip."""

import base64
import hashlib

from app.auth.pkce import (
    code_challenge_s256,
    generate_code_verifier,
    generate_state,
    pack_state_payload,
    states_match,
    unpack_state_payload,
)


def test_verifier_length_within_rfc_bounds() -> None:
    verifier = generate_code_verifier()
    assert 43 <= len(verifier) <= 128


def test_challenge_is_unpadded_base64url_sha256() -> None:
    verifier = "test-verifier-value"
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert code_challenge_s256(verifier) == expected
    assert "=" not in code_challenge_s256(verifier)


def test_state_payload_round_trips() -> None:
    state, verifier = generate_state(), generate_code_verifier()
    packed = pack_state_payload(state=state, verifier=verifier)
    assert unpack_state_payload(packed) == (state, verifier)


def test_unpack_rejects_garbage() -> None:
    assert unpack_state_payload(None) is None
    assert unpack_state_payload("") is None
    assert unpack_state_payload("not-base64!!") is None
    assert unpack_state_payload("aGVsbG8=") is None  # valid b64, not our JSON


def test_states_match_is_strict() -> None:
    assert states_match("abc", "abc") is True
    assert states_match("abc", "abd") is False
    assert states_match("abc", None) is False
    assert states_match("abc", "") is False
