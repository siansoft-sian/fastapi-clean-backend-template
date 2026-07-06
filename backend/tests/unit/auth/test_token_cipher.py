"""TokenCipher (Decision A): Fernet round-trip, misconfiguration failures."""

import pytest

from app.auth.token_cipher import TokenCipher


def test_encrypt_decrypt_round_trip() -> None:
    cipher = TokenCipher(TokenCipher.generate_key())
    ciphertext = cipher.encrypt("gotrue-access-token-value")
    assert isinstance(ciphertext, bytes)
    assert b"gotrue-access-token-value" not in ciphertext
    assert cipher.decrypt(ciphertext) == "gotrue-access-token-value"


def test_ciphertexts_are_nondeterministic() -> None:
    cipher = TokenCipher(TokenCipher.generate_key())
    assert cipher.encrypt("same") != cipher.encrypt("same")


def test_invalid_key_raises_configuration_error() -> None:
    with pytest.raises(RuntimeError, match="Fernet key"):
        TokenCipher("not-a-fernet-key")


def test_wrong_key_decrypt_raises_configuration_error() -> None:
    ciphertext = TokenCipher(TokenCipher.generate_key()).encrypt("secret")
    other = TokenCipher(TokenCipher.generate_key())
    with pytest.raises(RuntimeError, match="decrypt"):
        other.decrypt(ciphertext)
