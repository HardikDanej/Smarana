from memory_os import MemoryScope, SemanticType, SourceType
from memory_os.models import MemoryObject

from adapters.sqlite_adapter import SQLiteAdapter


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def test_store_and_get_roundtrips():
    db = SQLiteAdapter()
    memory = _memory("Project Alpha uses PostgreSQL.")
    db.store(memory)

    fetched = db.get(memory.id)

    assert fetched is not None
    assert fetched.id == memory.id
    assert fetched.content == memory.content


def test_get_missing_returns_none():
    db = SQLiteAdapter()
    assert db.get("does-not-exist") is None


def test_update_overwrites_stored_content():
    db = SQLiteAdapter()
    memory = _memory("Project Alpha uses AWS.")
    db.store(memory)

    revised = memory.new_version(content="Project Alpha uses GCP.")
    db.update(revised)

    fetched = db.get(memory.id)
    assert fetched.content == "Project Alpha uses GCP."
    assert fetched.version == 2


def test_delete_removes_from_storage_and_search():
    db = SQLiteAdapter()
    memory = _memory("Project Alpha uses PostgreSQL.")
    db.store(memory)

    db.delete(memory.id)

    assert db.get(memory.id) is None
    assert db.search("PostgreSQL") == []


def test_list_all_returns_every_stored_memory():
    db = SQLiteAdapter()
    db.store(_memory("first memory"))
    db.store(_memory("second memory"))

    all_memories = db.list_all()

    assert len(all_memories) == 2


def test_search_finds_matching_keyword():
    # Plan Step 41's own example: search "PostgreSQL" and retrieve it.
    db = SQLiteAdapter()
    match = _memory("Project Alpha uses PostgreSQL.")
    other = _memory("Project Beta uses MongoDB.")
    db.store(match)
    db.store(other)

    results = db.search("PostgreSQL")

    assert [m.id for m in results] == [match.id]


def test_search_query_with_punctuation_does_not_raise():
    # Natural-language queries contain characters FTS5's query syntax
    # would otherwise choke on ('?', ':', etc.) -- must not crash.
    db = SQLiteAdapter()
    db.store(_memory("What database are we using?"))

    results = db.search("What database are we using?")

    assert len(results) == 1


def test_search_with_no_matches_returns_empty_list():
    db = SQLiteAdapter()
    db.store(_memory("Project Alpha uses PostgreSQL."))

    assert db.search("nonexistent-keyword-zzz") == []
