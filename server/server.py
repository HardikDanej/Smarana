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

Auth: claude.ai's Custom Connector dialog only supports OAuth or no auth,
not a static bearer-token header, so this server does not gate requests by
token. Protection instead comes from the tunnel URL being a long random
secret — never share it, and restart the tunnel (which mints a new URL) if
you suspect it leaked.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

load_dotenv()

DATA_ROOT = Path(os.environ.get("SMRITI_DATA_ROOT") or (Path(__file__).parent / "data")).resolve()
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

mcp = MCPServer("smriti-memory")


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


def build_app():
    return mcp.streamable_http_app(transport_security=TRANSPORT_SECURITY)


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SMRITI_HOST", "127.0.0.1")
    port = int(os.environ.get("SMRITI_PORT", "8787"))
    uvicorn.run(build_app(), host=host, port=port)
