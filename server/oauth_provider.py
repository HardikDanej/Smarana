"""
Minimal single-resource-owner OAuth 2.1 authorization server for the Smriti
memory server.

Implements just enough of RFC 7591 (dynamic client registration), RFC 7636
(PKCE) and the authorization_code + refresh_token grants for claude.ai's
Connector flow to authenticate against a real login (password-gated) instead
of the tunnel URL being the only secret. PKCE code_verifier validation is
done by the SDK's own /token handler, not here.

There is exactly one resource owner: whoever knows SMRITI_LOGIN_PASSWORD.
Registered clients and refresh tokens persist to a local JSON file so a
server restart doesn't force reconnecting the claude.ai Connector, as long
as the tunnel URL (and therefore the issuer URL) hasn't also changed.
"""

import json
import secrets
import time
from pathlib import Path

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

ACCESS_TOKEN_TTL_SECONDS = 3600
AUTH_CODE_TTL_SECONDS = 600
LOGIN_TTL_SECONDS = 600


class SmritiOAuthProvider(OAuthAuthorizationServerProvider):
    def __init__(self, store_path: Path, login_password: str, public_host: str):
        self._store_path = store_path
        self._login_password = login_password
        self._public_host = public_host
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}  # short-lived, memory-only
        # login_token -> (client, params, expires_at) — memory-only, short-lived
        self._pending_logins: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams, float]] = {}
        self._load()

    # ---- persistence: clients + refresh tokens only (everything else is short-lived) ----

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        data = json.loads(self._store_path.read_text(encoding="utf-8"))
        for client_id, client_data in data.get("clients", {}).items():
            self._clients[client_id] = OAuthClientInformationFull.model_validate(client_data)
        for token, rt_data in data.get("refresh_tokens", {}).items():
            self._refresh_tokens[token] = RefreshToken.model_validate(rt_data)

    def _save(self) -> None:
        data = {
            "clients": {cid: c.model_dump(mode="json") for cid, c in self._clients.items()},
            "refresh_tokens": {t: rt.model_dump(mode="json") for t, rt in self._refresh_tokens.items()},
        }
        self._store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ---- OAuthAuthorizationServerProvider ----

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info
        self._save()

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        login_token = secrets.token_urlsafe(32)
        self._pending_logins[login_token] = (client, params, time.time() + LOGIN_TTL_SECONDS)
        return f"https://{self._public_host}/login?login_token={login_token}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self._auth_codes.get(authorization_code)
        if code is None or code.client_id != client.client_id or time.time() > code.expires_at:
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self._auth_codes.pop(authorization_code.code, None)
        return self._issue_tokens(client, authorization_code.scopes)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        token = self._refresh_tokens.get(refresh_token)
        if token is None or token.client_id != client.client_id:
            return None
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        self._refresh_tokens.pop(refresh_token.token, None)
        return self._issue_tokens(client, scopes or refresh_token.scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        access = self._access_tokens.get(token)
        if access is None:
            return None
        if access.expires_at is not None and time.time() > access.expires_at:
            self._access_tokens.pop(token, None)
            return None
        return access

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self._access_tokens.pop(getattr(token, "token", None), None)
        self._refresh_tokens.pop(getattr(token, "token", None), None)
        self._save()

    def _issue_tokens(self, client: OAuthClientInformationFull, scopes: list[str]) -> OAuthToken:
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        self._access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=int(time.time() + ACCESS_TOKEN_TTL_SECONDS),
        )
        self._refresh_tokens[refresh_token] = RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=scopes,
        )
        self._save()
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=refresh_token,
            scope=" ".join(scopes) if scopes else None,
        )

    # ---- login page support (not part of the OAuthAuthorizationServerProvider protocol) ----

    def get_pending_login(self, login_token: str) -> tuple[OAuthClientInformationFull, AuthorizationParams] | None:
        """Peek without consuming — safe to call from the GET that renders the form."""
        entry = self._pending_logins.get(login_token)
        if entry is None:
            return None
        client, params, expires_at = entry
        if time.time() > expires_at:
            self._pending_logins.pop(login_token, None)
            return None
        return client, params

    def check_password(self, password: str) -> bool:
        return secrets.compare_digest(password, self._login_password)

    def complete_login(self, login_token: str) -> str | None:
        """Consumes the pending login, mints an authorization code, returns the redirect URL."""
        entry = self._pending_logins.pop(login_token, None)
        if entry is None:
            return None
        client, params, expires_at = entry
        if time.time() > expires_at:
            return None
        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + AUTH_CODE_TTL_SECONDS,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)
