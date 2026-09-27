"""
Smarana remote memory server. MCP over streamable-HTTP for Claude, plus a
plain JSON REST surface (see the /projects routes near the bottom of this
file) for any caller that doesn't speak MCP: a CRM webhook, an ERP script,
a codebase with no LLM in front of it. Same tools, same enforcement, same
auth, reached over ordinary HTTP instead.

Tools: read_file / write_file / list_files / list_projects, so a claude.ai
Connector (or any MCP client) can persist MEMORY.md per project without
the user re-uploading anything. write_file now enforces
schemas/memory-schema.json and the 120-line/~800-token hard cap
server-side, via engine.py, on every write, for every caller, not only
when Claude happened to follow SKILL.md's prose correctly — see
_write_file_impl. search_memory is semantic search over each project's
aged-out history (superseded ADRs, Compressed Changelog entries); see
memory_index.py. classify_fact wraps scripts/tier_screen.py's local Laya
classifier as a first-class operation: a real tier/contradiction/duplicate
decision on a raw fact, callable with no LLM in the loop at all.

Tool names deliberately match what smarana's workflows/mcp-handshake.md
already expects under the mcp__filesystem__* namespace.

Every project gets its own subfolder under DATA_ROOT, keyed by a
`project` argument the client passes on each call. Paths are confined to
DATA_ROOT — no traversal outside it is possible.

Auth: when SMARANA_PUBLIC_HOST and SMARANA_LOGIN_PASSWORD are both set, this
runs a real (minimal) OAuth 2.1 authorization server — see
oauth_provider.py — so claude.ai's Connector flow ends at an actual login,
not just possession of the tunnel URL. Without both set, it falls back to
no auth at all (tunnel URL is the only protection); see server/README.md.
The REST routes reuse the same SMARANA_LOGIN_PASSWORD via a plain
`Authorization: Bearer <password>` header — see _rest_auth_error — not a
second, separate auth scheme.
"""

import datetime as dt
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response

import engine
import memory_index

# scripts/ holds tier_screen.py (the Laya classifier classify_fact wraps).
# It's a sibling directory to server/, not a package, same bare-import
# pattern engine.py and memory_index.py already use for this module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

load_dotenv()


def _resolve_data_root() -> Path:
    """SMARANA_DATA_ROOT falls back to server/data — including when the env
    var is present but set to an empty string, which `os.environ.get(key,
    default)` alone does NOT catch (that only applies the default when the
    key is absent). A prior version of this function had exactly that bug:
    an empty .env value silently resolved DATA_ROOT to server/ itself
    instead of server/data/. See TestDataRootEnvHandling in test_server.py.
    """
    raw = os.environ.get("SMARANA_DATA_ROOT")
    return Path(raw or (Path(__file__).parent / "data")).resolve()


DATA_ROOT = _resolve_data_root()
DATA_ROOT.mkdir(parents=True, exist_ok=True)

# The SDK's DNS-rebinding protection only allow-lists localhost Host headers
# by default, which rejects every request arriving through a tunnel (the
# Host header is the tunnel's public hostname, not "localhost"). Extend the
# allow-list with SMARANA_PUBLIC_HOST — set it to your current tunnel domain,
# no scheme, e.g. "random-words-here.trycloudflare.com".
_public_host = os.environ.get("SMARANA_PUBLIC_HOST", "").strip()
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

_login_password = os.environ.get("SMARANA_LOGIN_PASSWORD", "").strip()
oauth_provider = None
_auth_settings = None

if _public_host and _login_password:
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    from pydantic import AnyHttpUrl

    from oauth_provider import SmaranaOAuthProvider

    _issuer_url = AnyHttpUrl(f"https://{_public_host}")
    oauth_provider = SmaranaOAuthProvider(
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

mcp = MCPServer("smarana-memory", auth_server_provider=oauth_provider, auth=_auth_settings)


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


def _read_file_impl(project: str, filename: str = "MEMORY.md") -> str:
    path = _resolve(project, filename)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_file_impl(project: str, content: str, filename: str = "MEMORY.md") -> str:
    """Enforces schemas/memory-schema.json and the hard cap server-side for
    MEMORY.md writes, via engine.py, so this holds for every caller, MCP or
    REST, not only a Claude session that happened to follow SKILL.md's
    prose correctly.

    If `content` parses as a JSON object, it's treated as schema-shaped
    state: validated, auto-consolidated via engine.consolidate if it's over
    the hard cap, then rendered to the canonical Markdown template before
    being persisted. That's the path that gets full enforcement.

    Otherwise `content` is treated as pre-rendered Markdown (the original,
    Claude-artifact behavior). It's still checked against the hard cap by
    line/token count and rejected if over — engine.py has no Markdown
    parser back to schema-shaped state yet, so auto-consolidation isn't
    possible on this path. Pass structured JSON instead, or run
    workflows/consolidate-memory.md and retry.

    Raises ValueError on rejection. Any filename other than MEMORY.md is
    stored as-is, unvalidated, exactly as before this existed.
    """
    if filename == "MEMORY.md":
        state = None
        try:
            candidate = json.loads(content)
        except (ValueError, TypeError):
            candidate = None
        if isinstance(candidate, dict):
            state = candidate

        if state is not None:
            try:
                engine.validate(state)
            except Exception as exc:
                # jsonschema.ValidationError's str(exc) dumps the entire
                # schema for context; .message is the actual one-line
                # reason and is what a caller trying to fix its request
                # needs, not a page of schema JSON echoed back.
                reason = getattr(exc, "message", None) or str(exc)
                raise ValueError(f"rejected: does not conform to memory-schema.json: {reason}") from exc
            if engine.over_cap(state):
                state = engine.consolidate(state, dt.date.today().isoformat())
                if engine.over_cap(state):
                    raise ValueError(
                        "rejected: still over the 120-line/~800-token hard cap even "
                        "after server-side consolidation"
                    )
            content = engine.render_markdown(state)
        elif (
            engine.line_count(content) > engine.HARD_CAP_LINES
            or engine.approx_token_count(content) > engine.HARD_CAP_TOKENS
        ):
            raise ValueError(
                "rejected: over the 120-line/~800-token hard cap. Pass structured "
                "JSON state instead of pre-rendered Markdown for automatic "
                "server-side consolidation, or run workflows/consolidate-memory.md "
                "and retry."
            )

    path = _resolve(project, filename)
    path.write_text(content, encoding="utf-8")

    index_note = ""
    if filename == "MEMORY.md":
        try:
            indexed = memory_index.index_content(path.parent, content)
            if indexed:
                index_note = f", indexed {indexed} aged-out line(s) for search_memory"
        except Exception as exc:  # noqa: BLE001 - indexing must never break the core write
            index_note = f", search index update failed: {exc}"

    return f"wrote {len(content)} chars to {project}/{filename}{index_note}"


def _list_files_impl(project: str) -> list[str]:
    project_dir = (DATA_ROOT / project).resolve()
    if project_dir.parent != DATA_ROOT or not project_dir.exists():
        return []
    return sorted(p.name for p in project_dir.iterdir() if p.is_file())


def _list_projects_impl() -> list[str]:
    return sorted(p.name for p in DATA_ROOT.iterdir() if p.is_dir())


def _search_memory_impl(project: str, query: str, top_k: int = 5) -> list[str]:
    project_dir = (DATA_ROOT / project).resolve()
    if project_dir.parent != DATA_ROOT:
        raise ValueError(f"invalid project name: {project!r}")
    return memory_index.search(project_dir, query, top_k=top_k)


def _classify_fact_impl(project: str, candidate_text: str, existing_context: str = "") -> dict:
    """Local Laya-based tier/contradiction/duplicate classification for a
    raw candidate fact — no LLM required to call it. This wraps the same
    classifier Claude's own Phase 2 optionally cross-checks against (see
    scripts/tier_screen.py), exposed here as a first-class operation so a
    caller with no LLM in front of it (a CRM webhook, an ERP script, a
    plain codebase) can still get a real tier decision on a fact, not just
    an unstructured write. Degrades to a clean {"error": ...} if `laya`
    isn't installed; never raises, never fabricates a result — the exact
    contract tier_screen.py already guarantees for Claude's own use of it.
    `project` is accepted for a consistent call shape with the other tools
    and is reserved for future per-project classifier tuning; it isn't
    used yet.
    """
    import tier_screen  # sys.path already extended to scripts/ at module load

    return tier_screen.run_screen(
        {"candidate_text": candidate_text, "existing_context": existing_context}
    )


@mcp.tool()
def read_file(project: str, filename: str = "MEMORY.md") -> str:
    """Read a memory file for the given project. Returns '' if it doesn't exist yet."""
    return _read_file_impl(project, filename)


@mcp.tool()
def write_file(project: str, content: str, filename: str = "MEMORY.md") -> str:
    """Write (overwrite) a memory file for the given project. See
    _write_file_impl for the schema/hard-cap enforcement this now applies."""
    return _write_file_impl(project, content, filename)


@mcp.tool()
def list_files(project: str) -> list[str]:
    """List files currently stored for the given project."""
    return _list_files_impl(project)


@mcp.tool()
def list_projects() -> list[str]:
    """List every project that currently has stored memory."""
    return _list_projects_impl()


@mcp.tool()
def search_memory(project: str, query: str, top_k: int = 5) -> list[str]:
    """Semantic search over this project's AGED-OUT memory only: superseded/
    deprecated Tier 2 ADRs and Compressed Changelog entries — the detail
    that's already been compressed out of the live MEMORY.md to stay under
    the hard cap. For anything still in the live file, use read_file
    instead; this only helps find history that read_file can no longer
    surface in full. Returns an empty list if nothing has been indexed yet
    (e.g. write_file was never called, or nothing indexable was found)."""
    return _search_memory_impl(project, query, top_k)


@mcp.tool()
def classify_fact(project: str, candidate_text: str, existing_context: str = "") -> dict:
    """Local Laya-based tier/contradiction/duplicate classification for a
    raw candidate fact. See _classify_fact_impl for the full contract."""
    return _classify_fact_impl(project, candidate_text, existing_context)


_LOGIN_FORM = """<!doctype html>
<html><head><title>Smarana Memory Server</title></head>
<body style="font-family:sans-serif;max-width:360px;margin:80px auto">
<h2>Smarana Memory Server</h2>
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


def _rest_auth_error(request: Request) -> Response | None:
    """None if the request may proceed, else the 401 to return.

    Reuses the same SMARANA_LOGIN_PASSWORD already configured for the MCP
    Connector flow (oauth_provider.check_password) — this is not a new
    auth scheme, just the existing password gate applied to the plain REST
    surface too, via `Authorization: Bearer <password>`. When no password
    is configured, REST falls back to no auth, exactly like the MCP tools
    already do without SMARANA_PUBLIC_HOST/SMARANA_LOGIN_PASSWORD set.
    """
    if oauth_provider is None:
        return None
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not token or not oauth_provider.check_password(token):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


@mcp.custom_route("/projects", methods=["GET"])
async def rest_list_projects(request: Request) -> Response:
    """Plain REST mirror of the list_projects MCP tool, for callers with
    no MCP client (a CRM, an ERP, a plain script) — same DATA_ROOT, same
    auth, same logic, just reached over ordinary JSON HTTP instead."""
    if (err := _rest_auth_error(request)) is not None:
        return err
    return JSONResponse(_list_projects_impl())


@mcp.custom_route("/projects/{project}/memory", methods=["GET"])
async def rest_read_memory(request: Request) -> Response:
    if (err := _rest_auth_error(request)) is not None:
        return err
    project = request.path_params["project"]
    filename = request.query_params.get("filename", "MEMORY.md")
    try:
        content = _read_file_impl(project, filename)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return PlainTextResponse(content)


@mcp.custom_route("/projects/{project}/memory", methods=["PUT"])
async def rest_write_memory(request: Request) -> Response:
    """Body is the raw content to write — either pre-rendered Markdown or a
    JSON object matching memory-schema.json (see _write_file_impl). Content
    type is read as plain text either way; a JSON body still arrives as
    text and gets json.loads'd internally, exactly like the MCP tool."""
    if (err := _rest_auth_error(request)) is not None:
        return err
    project = request.path_params["project"]
    filename = request.query_params.get("filename", "MEMORY.md")
    try:
        content = (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse({"error": "request body must be UTF-8 text"}, status_code=400)
    try:
        result = _write_file_impl(project, content, filename)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"result": result})


@mcp.custom_route("/projects/{project}/files", methods=["GET"])
async def rest_list_files(request: Request) -> Response:
    if (err := _rest_auth_error(request)) is not None:
        return err
    return JSONResponse(_list_files_impl(request.path_params["project"]))


@mcp.custom_route("/projects/{project}/search", methods=["GET"])
async def rest_search_memory(request: Request) -> Response:
    if (err := _rest_auth_error(request)) is not None:
        return err
    project = request.path_params["project"]
    query = request.query_params.get("query", "")
    top_k = int(request.query_params.get("top_k", "5"))
    try:
        results = _search_memory_impl(project, query, top_k)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(results)


@mcp.custom_route("/projects/{project}/classify", methods=["POST"])
async def rest_classify_fact(request: Request) -> Response:
    """Body: {"candidate_text": "...", "existing_context": "..."}. This is
    the route a non-LLM caller actually wants: a real tier/contradiction/
    duplicate classification on a raw fact, with no LLM in the loop."""
    if (err := _rest_auth_error(request)) is not None:
        return err
    project = request.path_params["project"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    candidate_text = str(body.get("candidate_text", ""))
    existing_context = str(body.get("existing_context", ""))
    result = _classify_fact_impl(project, candidate_text, existing_context)
    return JSONResponse(result)


def build_app():
    return mcp.streamable_http_app(transport_security=TRANSPORT_SECURITY)


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SMARANA_HOST", "127.0.0.1")
    port = int(os.environ.get("SMARANA_PORT", "8787"))
    if oauth_provider is None:
        print("SMARANA_PUBLIC_HOST/SMARANA_LOGIN_PASSWORD not both set — running with NO AUTH.")
    uvicorn.run(build_app(), host=host, port=port)
