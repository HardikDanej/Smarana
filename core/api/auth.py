"""
API authentication (Plan Step 96, closing docs/THREAT_MODEL.md's named
gap: "no authentication... exists because there is no API yet to
enforce it on"). Deliberately minimal: an API key maps to exactly the
two identifiers the rest of the engine already understands --
principal_id (Phase 13's AccessPolicy) and tenant_id (Phase 16's hard
tenant wall) -- so authenticating a request is also how it gets scoped,
not a separate concern layered on top.

In-memory only, same honesty as reliability.py's failure injector: a
single-process API key store is right for this phase's scope (closing
"no auth exists at all"), not a claim that this is a production identity
provider. A real deployment swaps this for a real one (a database table,
an OAuth/OIDC integration) behind the same two methods.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class Principal:
    principal_id: str
    tenant_id: "str | None"


class APIKeyStore:
    def __init__(self):
        self._keys: dict[str, Principal] = {}

    def issue_key(self, principal_id: str, tenant_id: "str | None" = None) -> str:
        key = secrets.token_urlsafe(32)
        self._keys[key] = Principal(principal_id=principal_id, tenant_id=tenant_id)
        return key

    def resolve(self, key: str) -> "Principal | None":
        # Constant-time comparison per candidate -- a key is a bearer
        # credential, and a naive `in`/`==` scan leaks timing
        # information proportional to how much of the key matched.
        for stored_key, principal in self._keys.items():
            if hmac.compare_digest(stored_key, key):
                return principal
        return None

    def revoke_key(self, key: str) -> None:
        self._keys.pop(key, None)


def make_authenticate_dependency(api_keys: APIKeyStore):
    """Returns a FastAPI dependency bound to one APIKeyStore instance --
    the app wires its own store in via create_app(), never a module-level
    global one test run could bleed into another."""

    def authenticate(authorization: "str | None" = Header(default=None)) -> Principal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing or malformed Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        key = authorization.removeprefix("Bearer ")
        principal = api_keys.resolve(key)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return principal

    return authenticate
