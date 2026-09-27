"""
SQLite storage adapter (Plan Step 41): "Before embeddings: SQLite + full-
text search... This gives us a completely local, free baseline."

Like claude_provider.py, this is the ONLY file allowed to import sqlite3
directly -- core/memory_os never touches a concrete storage technology,
enforced by the same adapter-isolation gate that covers the Claude
adapter.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from memory_os.models import MemoryObject

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "we", "you", "i", "it", "this", "that", "of", "to", "in", "on", "for",
    "and", "or", "what", "how", "why",
}


class SQLiteAdapter:
    def __init__(self, path: "str | Path" = ":memory:", *, check_same_thread: bool = True):
        # check_same_thread=False (Phase 19, Step 96): FastAPI's default
        # sync-endpoint execution runs each request in a worker thread
        # from anyio's thread pool, not the thread that constructed this
        # adapter -- sqlite3's own default refuses that outright. False
        # is an explicit opt-in a caller reaches for (e.g.
        # api/app.py's create_app), not a new default for every existing
        # caller: SQLite still serializes access to one connection
        # internally, which is correct but not concurrent, exactly the
        # dev-only tradeoff this adapter has always made.
        self._conn = sqlite3.connect(str(path), check_same_thread=check_same_thread)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(id UNINDEXED, content)"
        )
        self._conn.commit()

    def store(self, memory: MemoryObject) -> None:
        self._upsert(memory)

    def update(self, memory: MemoryObject) -> None:
        self._upsert(memory)

    def _upsert(self, memory: MemoryObject) -> None:
        self._conn.execute(
            "INSERT INTO memories (id, data) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (memory.id, memory.model_dump_json()),
        )
        self._conn.execute("DELETE FROM memories_fts WHERE id = ?", (memory.id,))
        self._conn.execute(
            "INSERT INTO memories_fts (id, content) VALUES (?, ?)",
            (memory.id, memory.content),
        )
        self._conn.commit()

    def get(self, memory_id: str) -> "MemoryObject | None":
        row = self._conn.execute(
            "SELECT data FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return None if row is None else MemoryObject.model_validate_json(row["data"])

    def delete(self, memory_id: str) -> None:
        self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.execute("DELETE FROM memories_fts WHERE id = ?", (memory_id,))
        self._conn.commit()

    def search(self, query: str, top_k: int = 10) -> list[MemoryObject]:
        match_expr = self._fts_match_expression(query)
        if not match_expr:
            return []
        rows = self._conn.execute(
            "SELECT m.data FROM memories_fts f "
            "JOIN memories m ON m.id = f.id "
            "WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
            (match_expr, top_k),
        ).fetchall()
        return [MemoryObject.model_validate_json(row["data"]) for row in rows]

    def list_all(self) -> list[MemoryObject]:
        rows = self._conn.execute("SELECT data FROM memories").fetchall()
        return [MemoryObject.model_validate_json(row["data"]) for row in rows]

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _fts_match_expression(query: str) -> str:
        """Turns free-form text into a safe FTS5 MATCH expression: every
        token quoted (so punctuation in the query can't be read as FTS5
        query syntax) and OR'd together. Stopwords are dropped unless
        they're all the query has, so a query of only common words still
        matches something rather than silently returning nothing."""
        tokens = re.findall(r"\w+", query.lower())
        significant = [t for t in tokens if t not in _STOPWORDS]
        chosen = significant or tokens
        if not chosen:
            return ""
        return " OR ".join(f'"{t}"' for t in chosen)
