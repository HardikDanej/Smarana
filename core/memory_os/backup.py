"""
Backup and recovery (Plan Step 95): export/import as plain functions
over the StorageAdapter Protocol and RelationshipGraph -- vendor-neutral
on purpose, the same reasoning reliability.py's failure injector
follows. A concrete backup destination (a file on disk, object storage,
...) is an adapter's job (see core/adapters/file_backup.py); this module
only knows how to turn a live store into portable data and back, not
where that data ends up. Because the portable shape is just
MemoryObject's own JSON, per-storage-technology round-tripping is free:
exporting from SQLiteAdapter and importing into PostgresAdapter (or the
reverse) is exactly what test_backup.py proves, not a hypothetical.
"""

from __future__ import annotations

from .models import MemoryObject
from .relationships import RelationshipGraph, RelationshipType
from .storage import StorageAdapter


def export_memories(storage: StorageAdapter) -> list[dict]:
    """Every memory currently in `storage`, as plain JSON-serializable
    dicts. `model_dump(mode="json")`, not the bare `model_dump()` -- the
    latter leaves datetimes/enums as live Python objects a real
    serializer downstream (json.dumps, a message queue, ...) would choke
    on; the former is exactly what `model_validate()` expects back."""
    return [m.model_dump(mode="json") for m in storage.list_all()]


def import_memories(storage: StorageAdapter, records: list[dict]) -> int:
    """Restores every record into `storage` via its own `store()` --
    not a bulk/raw insert, so the same validation every other write goes
    through (Pydantic's, and whatever the adapter itself enforces, e.g.
    Postgres's RLS policy) applies to a restore too. Returns how many
    records were restored."""
    count = 0
    for record in records:
        storage.store(MemoryObject.model_validate(record))
        count += 1
    return count


def export_relationships(graph: RelationshipGraph) -> list[dict]:
    """Every edge in `graph`, as plain JSON-serializable dicts --
    Step 89's PostgresAdapter.sync_relationship_graph() persists a
    RelationshipGraph into a database; this is the same idea for a
    portable file/message instead of a live table."""
    return [
        {
            "source_id": edge.source_id,
            "relationship_type": edge.relationship_type.value,
            "target_id": edge.target_id,
            "metadata": edge.metadata,
        }
        for edge in graph.edges()
    ]


def import_relationships(records: list[dict]) -> RelationshipGraph:
    """The reverse: rebuilds a fresh in-memory RelationshipGraph from
    exported edge records."""
    graph = RelationshipGraph()
    for record in records:
        graph.add(
            record["source_id"],
            RelationshipType(record["relationship_type"]),
            record["target_id"],
            **record.get("metadata", {}),
        )
    return graph
