"""
Optional semantic search over a project's AGED-OUT memory: superseded or
deprecated Tier 2 ADRs, and every Compressed Changelog entry. Live Tier 1/2/3
content in the current MEMORY.md stays a plain read_file — this only helps
find detail that's already been compressed away, which is the actual gap:
the changelog format intentionally throws away specifics to stay under the
120-line cap, and this makes those specifics findable again by meaning
instead of exact keyword.

Uses a local Chroma vector store per project (server/data/<project>/
vector_index/) with Chroma's default local embedding model
(all-MiniLM-L6-v2 via onnxruntime) — no API key, no per-query cost. The
embedding model itself (~80-90MB) downloads once from Hugging Face's CDN on
first use and is cached under Chroma's own cache directory afterward; after
that first download, indexing and search both run fully offline.

Extraction is deliberately simple, section-scoped plain-text parsing, not a
full markdown AST — matching the rest of this server's philosophy of
staying lightweight rather than reaching for a markdown parser dependency.
"""

import hashlib
import re
from pathlib import Path

import chromadb

_TIER2_HEADING_RE = re.compile(r"^##\s+Tier 2", re.IGNORECASE)
_CHANGELOG_HEADING_RE = re.compile(r"^##\s+Compressed Changelog", re.IGNORECASE)
_HEADING_RE = re.compile(r"^##\s+")
_SUPERSEDED_MARK_RE = re.compile(r"status:\s*(superseded|deprecated)", re.IGNORECASE)


def extract_indexable_lines(content: str) -> list[str]:
    """Pull superseded/deprecated Tier 2 ADR lines and every Compressed
    Changelog bullet out of a rendered MEMORY.md. Active Tier 2 entries,
    all of Tier 1 and Tier 3, and anything outside these two sections are
    deliberately excluded — they're already fully visible in a plain read."""
    lines = content.splitlines()
    section: str | None = None
    out: list[str] = []

    for line in lines:
        if _TIER2_HEADING_RE.match(line):
            section = "tier2"
            continue
        if _CHANGELOG_HEADING_RE.match(line):
            section = "changelog"
            continue
        if _HEADING_RE.match(line):
            section = None
            continue

        stripped = line.strip()
        if not stripped.startswith("-"):
            continue

        if section == "changelog":
            out.append(stripped)
        elif section == "tier2" and _SUPERSEDED_MARK_RE.search(stripped):
            out.append(stripped)

    return out


def _collection(project_dir: Path):
    index_dir = project_dir / "vector_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(index_dir))
    return client.get_or_create_collection("memory")


def index_content(project_dir: Path, content: str) -> int:
    """(Re-)index the aged-out portions of `content`. Upserts by an id
    derived from the line text itself, so re-writing unchanged content is a
    no-op and an edited line replaces its old vector rather than
    duplicating. Returns how many lines were (re-)indexed."""
    lines = extract_indexable_lines(content)
    if not lines:
        return 0

    ids = [hashlib.sha1(line.encode("utf-8")).hexdigest()[:16] for line in lines]
    _collection(project_dir).upsert(ids=ids, documents=lines)
    return len(lines)


def search(project_dir: Path, query: str, top_k: int = 5) -> list[str]:
    """Semantic search over this project's indexed aged-out memory.
    Returns an empty list if nothing has been indexed yet — never raises
    for an empty or missing index."""
    index_dir = project_dir / "vector_index"
    if not index_dir.exists():
        return []

    collection = _collection(project_dir)
    count = collection.count()
    if count == 0:
        return []

    result = collection.query(query_texts=[query], n_results=min(top_k, count))
    documents = result.get("documents") or [[]]
    return documents[0]
