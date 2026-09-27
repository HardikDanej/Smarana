"""
File-based backup adapter (Plan Step 95): the first concrete backup
destination. Writes memory_os.backup's export functions' output to a
single JSON file on disk.

The filesystem is itself a concrete storage choice -- the same reasoning
FilesystemObjectStore follows -- so this lives in adapters even though it
needs no vendor library at all, just stdlib `json`/`pathlib`. A future
destination (S3, a backup service) is a drop-in swap with the same two
functions' shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from memory_os.backup import export_memories, export_relationships, import_memories, import_relationships
from memory_os.relationships import RelationshipGraph
from memory_os.storage import StorageAdapter


def save_backup(path: "str | Path", storage: StorageAdapter, graph: "RelationshipGraph | None" = None) -> None:
    payload = {
        "memories": export_memories(storage),
        "relationships": export_relationships(graph) if graph is not None else [],
    }
    Path(path).write_text(json.dumps(payload, indent=2))


def load_backup(path: "str | Path", storage: StorageAdapter) -> RelationshipGraph:
    """Restores every memory in the backup into `storage`, returns the
    relationship graph reloaded from it (empty if the backup carried
    none)."""
    payload = json.loads(Path(path).read_text())
    import_memories(storage, payload["memories"])
    return import_relationships(payload.get("relationships", []))
