"""Phase 18 (Plan Step 95): backup and recovery."""

from adapters.file_backup import load_backup, save_backup
from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import (
    MemoryScope,
    SemanticType,
    SourceType,
    export_memories,
    export_relationships,
    import_memories,
    import_relationships,
)
from memory_os.models import MemoryObject
from memory_os.relationships import RelationshipGraph, RelationshipType


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


# --- pure export/import functions ---


def test_export_memories_returns_json_serializable_dicts():
    db = SQLiteAdapter()
    memory = _memory("Project Alpha uses PostgreSQL.")
    db.store(memory)

    records = export_memories(db)

    import json

    json.dumps(records)  # must not raise
    assert records[0]["id"] == memory.id


def test_import_memories_restores_into_a_fresh_store():
    source = SQLiteAdapter()
    source.store(_memory("Project Alpha uses PostgreSQL."))
    source.store(_memory("Project Beta uses MongoDB."))
    records = export_memories(source)

    destination = SQLiteAdapter()
    restored_count = import_memories(destination, records)

    assert restored_count == 2
    assert len(destination.list_all()) == 2


def test_export_and_import_relationships_round_trip():
    graph = RelationshipGraph()
    graph.add("m1", RelationshipType.DERIVED_FROM, "m2", note="original")

    reloaded = import_relationships(export_relationships(graph))

    assert [e.target_id for e in reloaded.outgoing("m1")] == ["m2"]
    assert reloaded.outgoing("m1")[0].metadata == {"note": "original"}


# --- file-based backup adapter ---


def test_save_and_load_backup_round_trips_through_a_real_file(tmp_path):
    source = SQLiteAdapter()
    memory = _memory("Project Alpha uses PostgreSQL.")
    source.store(memory)
    graph = RelationshipGraph()
    graph.add(memory.id, RelationshipType.DERIVED_FROM, "some-episode")

    backup_path = tmp_path / "backup.json"
    save_backup(backup_path, source, graph)

    destination = SQLiteAdapter()
    reloaded_graph = load_backup(backup_path, destination)

    restored = destination.get(memory.id)
    assert restored is not None
    assert restored.content == memory.content
    assert [e.target_id for e in reloaded_graph.outgoing(memory.id)] == ["some-episode"]


def test_load_backup_with_no_relationships_gives_an_empty_graph(tmp_path):
    source = SQLiteAdapter()
    source.store(_memory("A memory with no relationships."))

    backup_path = tmp_path / "backup.json"
    save_backup(backup_path, source)  # no graph argument

    destination = SQLiteAdapter()
    reloaded_graph = load_backup(backup_path, destination)

    assert reloaded_graph.edges() == []


# --- the real proof: backup format is portable across storage technologies ---


def test_backup_round_trips_from_sqlite_to_postgres(postgres_adapter, tmp_path):
    source = SQLiteAdapter()
    memory = _memory("Project Alpha uses PostgreSQL for storage.")
    source.store(memory)
    graph = RelationshipGraph()
    graph.add(memory.id, RelationshipType.SUPPORTS, "some-other-memory")

    backup_path = tmp_path / "backup.json"
    save_backup(backup_path, source, graph)

    reloaded_graph = load_backup(backup_path, postgres_adapter)

    restored = postgres_adapter.get(memory.id)
    assert restored is not None
    assert restored.content == memory.content
    assert [e.target_id for e in reloaded_graph.outgoing(memory.id)] == ["some-other-memory"]
