"""
Fernet adapter (Plan Step 85): the first concrete Encryptor.

"Built on established libraries, never custom cryptography" -- this
wraps `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256,
authenticated symmetric encryption) rather than implementing a cipher.
This is the ONLY file in this codebase allowed to import `cryptography`,
the same rule ClaudeProvider follows for `anthropic`: nothing in
core/memory_os imports this module either, enforced by the
adapter-isolation gate.

Key management here is deliberately minimal -- a single key, passed in or
generated. Per-tenant key derivation/rotation/a real key management
service (KMS) is real Step 85 scope this adapter does not claim to
close; `generate_key()` exists so a caller can create and store one
themselves, not so this module can be mistaken for a KMS.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class DecryptionError(Exception):
    """Raised when ciphertext can't be authenticated against the key --
    wrong key, or the ciphertext was corrupted/tampered with. Wraps
    InvalidToken so callers depend on this adapter's own exception type,
    not `cryptography`'s, the same reason core/memory_os never imports
    `cryptography` directly."""


class FernetEncryptor:
    """Implements memory_os.encryption.Encryptor."""

    def __init__(self, key: bytes | str | None = None):
        if key is None:
            key = Fernet.generate_key()
        elif isinstance(key, str):
            key = key.encode()
        self._fernet = Fernet(key)

    @staticmethod
    def generate_key() -> str:
        """A fresh key, as a string suitable for storing in a secrets
        manager/env var and passing back in as `key=` later."""
        return Fernet.generate_key().decode()

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("ciphertext failed authentication for this key") from exc
