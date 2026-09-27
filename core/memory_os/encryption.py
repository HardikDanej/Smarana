"""
Encryption interface (Plan Step 85): "at rest, in transit, key management,
per-tenant and per-field -- built on established libraries, never custom
cryptography."

Encryptor is a Protocol, the same shape as LLMProvider and Embedder: the
engine names the capability it needs (turn plaintext into ciphertext and
back) without ever importing a concrete crypto library itself. The actual
implementation -- built on `cryptography.fernet`, per the plan's own
instruction not to invent a cipher -- lives in core/adapters, the one
place concrete vendor tech is allowed (enforced by the same
adapter-isolation gate that covers ClaudeProvider and SQLiteAdapter).

This module is deliberately NOT wired into StorageAdapter or MemoryObject
automatically. Per-field encryption is a caller's decision about which
fields of which memories need it -- forcing it on unconditionally would
mean every read pays a decrypt cost and every query loses the ability to
search encrypted fields, neither of which this phase is positioned to
resolve. Opt-in infrastructure, matching how PolicyEngine's audit_log
param works (Step 84): present and usable, not a hidden requirement.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Encryptor(Protocol):
    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str: ...
