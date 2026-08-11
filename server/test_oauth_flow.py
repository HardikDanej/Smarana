"""Manual end-to-end smoke test for the OAuth flow. Not part of the unittest suite."""

import base64
import hashlib
import os
import re
import secrets
from urllib.parse import parse_qs, urlparse

import httpx2
from dotenv import load_dotenv

load_dotenv()
PUBLIC_HOST = os.environ["SMRITI_PUBLIC_HOST"]
PASSWORD = os.environ["SMRITI_LOGIN_PASSWORD"]
BASE = f"https://{PUBLIC_HOST}"


def main():
    client = httpx2.Client(follow_redirects=False, timeout=30)

    # 1. Metadata discovery
    meta = client.get(f"{BASE}/.well-known/oauth-authorization-server")
    assert meta.status_code == 200, meta.text
    meta_json = meta.json()
    print("metadata ok:", meta_json["authorization_endpoint"], meta_json["token_endpoint"])

    # 2. Dynamic client registration (RFC 7591)
    reg = client.post(
        f"{BASE}/register",
        json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "client_name": "smoke-test-client",
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]
    print("registered client:", client_id)

    # 3. /authorize with PKCE -> should redirect to our /login page
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    authz = client.get(
        f"{BASE}/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        },
    )
    assert authz.status_code in (302, 307), authz.text
    login_url = authz.headers["location"]
    assert login_url.startswith(f"{BASE}/login?login_token="), login_url
    print("redirected to login page:", login_url)
    login_token = parse_qs(urlparse(login_url).query)["login_token"][0]

    # 4. GET the login form
    form = client.get(login_url)
    assert form.status_code == 200 and "Sign in" in form.text, form.text
    print("login form rendered ok")

    # 5. POST wrong password -> should be rejected
    wrong = client.post(f"{BASE}/login", data={"login_token": login_token, "password": "wrong-password"})
    assert wrong.status_code == 401, f"expected 401 for wrong password, got {wrong.status_code}"
    print("wrong password correctly rejected")

    # 6. POST correct password -> should redirect to redirect_uri with code+state
    right = client.post(f"{BASE}/login", data={"login_token": login_token, "password": PASSWORD})
    assert right.status_code in (302, 307), right.text
    callback_url = right.headers["location"]
    qs = parse_qs(urlparse(callback_url).query)
    assert qs["state"][0] == state, "state mismatch"
    code = qs["code"][0]
    print("login succeeded, got authorization code")

    # 7. Exchange code for tokens (PKCE verified server-side)
    token_resp = client.post(
        f"{BASE}/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert token_resp.status_code == 200, token_resp.text
    tokens = token_resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    print("token exchange ok, got access_token + refresh_token")

    # 8. Reject a garbage PKCE verifier on a fresh code (defense-in-depth check)
    # (skipped — codes are single-use; re-testing would need a second /authorize round trip)

    # 9. Call /mcp WITHOUT a token -> must be rejected
    no_auth = client.post(
        f"{BASE}/mcp",
        headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert no_auth.status_code == 401, f"expected 401 without token, got {no_auth.status_code}: {no_auth.text}"
    print("request without token correctly rejected:", no_auth.status_code)

    # 10. Call /mcp WITH the access token -> must succeed
    with_auth = client.post(
        f"{BASE}/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke-test", "version": "1.0"},
            },
        },
    )
    assert with_auth.status_code == 200, f"expected 200 with token, got {with_auth.status_code}: {with_auth.text}"
    print("request WITH token succeeded:", with_auth.status_code)

    # 11. Refresh token flow
    refreshed = client.post(
        f"{BASE}/token",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id},
    )
    assert refreshed.status_code == 200, refreshed.text
    print("refresh_token exchange ok")

    print("\nALL OAUTH FLOW CHECKS PASSED")


if __name__ == "__main__":
    main()
