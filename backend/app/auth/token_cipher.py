"""App-level encryption for GoTrue tokens at rest — Decision A (locked).

FastAPI encrypts with a Fernet key from the environment/KMS
(`SESSION_TOKEN_ENCRYPTION_KEY`) before storing and decrypts after fetch. The
database stores/returns opaque bytea and never sees plaintext or the key.
Pure module: no FastAPI, no I/O; failures raise RuntimeError (server
misconfiguration, surfaced as a generic 500 — never a 401).
"""

from cryptography.fernet import Fernet, InvalidToken


class TokenCipher:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                "SESSION_TOKEN_ENCRYPTION_KEY is not a valid Fernet key. Generate one "
                'with: python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            ) from exc

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError(
                "Stored token ciphertext failed to decrypt — was "
                "SESSION_TOKEN_ENCRYPTION_KEY rotated without re-encrypting sessions?"
            ) from exc

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("ascii")
