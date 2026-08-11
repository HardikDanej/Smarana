"""
Smriti remote memory MCP server.

Exposes filesystem-style tools (read_file / write_file / list_files) over
streamable-HTTP, so a claude.ai Connector can persist MEMORY.md per project
without the user re-uploading anything.

Tool names deliberately match what smriti's workflows/mcp-handshake.md
already expects under the mcp__filesystem__* namespace.

Every project gets its own subfolder under DATA_ROOT, keyed by a
`project` argument the client passes on each call. Paths are confined to
DATA_ROOT — no traversal outside it is possible.

Auth: when SMRITI_PUBLIC_HOST and SMRITI_LOGIN_PASSWORD are both set, this
runs a real (minimal) OAuth 2.1 authorization server — see
oauth_provider.py — so claude.ai's Connector flow ends at an actual login,
not just possession of the tunnel URL. Without both set, it falls back to
no auth at all (tunnel URL is the only protection); see server/README.md.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

load_dotenv()


def _resolve_data_root() -> Path:
    """SMRITI_DATA_ROOT falls back to server/data — including when the env
    var is present but set to an empty string, which `os.environ.get(key,
    default)` alone does NOT catch (that only applies the default when the
    key is absent). A prior version of this function had exactly that bug:
    an empty .env value silently resolved DATA_ROOT to server/ itself
    instead of server/data/. See TestDataRootEnvHandling in test_server.py.
    """
    raw = os.environ.get("SMRITI_DATA_ROOT")
    return Path(raw or (Path(__file__).parent / "data")).resolve()


DATA_ROOT = _resolve_data_root()
DATA_ROOT.mkdir(parents=True, exist_ok=True)

# The SDK's DNS-rebinding protection only allow-lists localhost Host headers
# by default, which rejects every request arriving through a tunnel (the
# Host header is the tunnel's public hostname, not "localhost"). Extend the
# allow-list with SMRITI_PUBLIC_HOST — set it to your current tunnel domain,
# no scheme, e.g. "random-words-here.trycloudflare.com".
_public_host = os.environ.get("SMRITI_PUBLIC_HOST", "").strip()
_allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_allowed_origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
if _public_host:
    _allowed_hosts.append(_public_host)
    _allowed_origins.append(f"https://{_public_host}")
TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=_allowed_hosts,
    allowed_origins=_allowed_origins,
)

_login_password = os.environ.get("SMRITI_LOGIN_PASSWORD", "").strip()
oauth_provider = None
_auth_settings = None

if _public_host and _login_password:
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    from pydantic import AnyHttpUrl

    from oauth_provider import SmritiOAuthProvider

    _issuer_url = AnyHttpUrl(f"https://{_public_host}")
    oauth_provider = SmritiOAuthProvider(
        store_path=Path(__file__).parent / "oauth_store.json",
        login_password=_login_password,
        public_host=_public_host,
    )
    _auth_settings = AuthSettings(
        issuer_url=_issuer_url,
        resource_server_url=_issuer_url,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, default_scopes=["mcp"], valid_scopes=["mcp"]
        ),
        revocation_options=RevocationOptions(enabled=True),
    )

mcp = MCPServer("smriti-memory", auth_server_provider=oauth_provider, auth=_auth_settings)


def _resolve(project: str, filename: str) -> Path:
    """Confine every path to DATA_ROOT/<project>/<filename>. Rejects traversal."""
    if not project or "/" in project or "\\" in project or ".." in project:
        raise ValueError(f"invalid project name: {project!r}")
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"invalid filename: {filename!r}")

    project_dir = (DATA_ROOT / project).resolve()
    if project_dir.parent != DATA_ROOT:
        raise ValueError(f"invalid project name: {project!r}")

    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir / filename


@mcp.tool()
def read_file(project: str, filename: str = "MEMORY.md") -> str:
    """Read a memory file for the given project. Returns '' if it doesn't exist yet."""
    path = _resolve(project, filename)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


@mcp.tool()
def write_file(project: str, content: str, filename: str = "MEMORY.md") -> str:
    """Write (overwrite) a memory file for the given project."""
    path = _resolve(project, filename)
    path.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {project}/{filename}"


@mcp.tool()
def list_files(project: str) -> list[str]:
    """List files currently stored for the given project."""
    project_dir = (DATA_ROOT / project).resolve()
    if project_dir.parent != DATA_ROOT or not project_dir.exists():
        return []
    return sorted(p.name for p in project_dir.iterdir() if p.is_file())


@mcp.tool()
def list_projects() -> list[str]:
    """List every project that currently has stored memory."""
    return sorted(p.name for p in DATA_ROOT.iterdir() if p.is_dir())


_LOGIN_FORM = """<!doctype html>
<html><head><title>Smriti Memory Server</title></head>
<body style="font-family:sans-serif;max-width:360px;margin:80px auto">
<h2>Smriti Memory Server</h2>
<p>Sign in to authorize this connector.</p>
<form method="post">
<input type="hidden" name="login_token" value="{login_token}">
<input type="password" name="password" placeholder="Password" autofocus
       style="width:100%;padding:8px;margin:8px 0;box-sizing:border-box">
<button type="submit" style="width:100%;padding:8px">Sign in</button>
{error}
</form>
</body></html>"""

_LOGIN_INVALID = "<p>This login link is invalid or has expired. Go back to claude.ai and try connecting again.</p>"


@mcp.custom_route("/login", methods=["GET"])
async def login_form(request: Request) -> Response:
    login_token = request.query_params.get("login_token", "")
    if oauth_provider is None or not oauth_provider.get_pending_login(login_token):
        return HTMLResponse(_LOGIN_INVALID, status_code=400)
    return HTMLResponse(_LOGIN_FORM.format(login_token=login_token, error=""))


@mcp.custom_route("/login", methods=["POST"])
async def login_submit(request: Request) -> Response:
    form = await request.form()
    login_token = str(form.get("login_token", ""))
    password = str(form.get("password", ""))

    if oauth_provider is None or not oauth_provider.get_pending_login(login_token):
        return HTMLResponse(_LOGIN_INVALID, status_code=400)

    if not oauth_provider.check_password(password):
        error = "<p style='color:#c00'>Wrong password.</p>"
        return HTMLResponse(_LOGIN_FORM.format(login_token=login_token, error=error), status_code=401)

    redirect_url = oauth_provider.complete_login(login_token)
    if redirect_url is None:
        return HTMLResponse(_LOGIN_INVALID, status_code=400)
    return RedirectResponse(redirect_url, status_code=302)


def build_app():
    return mcp.streamable_http_app(transport_security=TRANSPORT_SECURITY)


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SMRITI_HOST", "127.0.0.1")
    port = int(os.environ.get("SMRITI_PORT", "8787"))
    if oauth_provider is None:
        print("SMRITI_PUBLIC_HOST/SMRITI_LOGIN_PASSWORD not both set — running with NO AUTH.")
    uvicorn.run(build_app(), host=host, port=port)
