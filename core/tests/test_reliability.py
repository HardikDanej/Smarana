"""Phase 18 (Plan Step 94): failure injection."""

import pytest

from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import (
    FailureInjectingStorageAdapter,
    MemoryScope,
    SemanticType,
    SourceType,
    StorageAdapter,
    StorageFailure,
)
from memory_os.models import MemoryObject
from memory_os.retrieval import RetrievalEngine


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def test_satisfies_the_storage_adapter_protocol():
    assert isinstance(FailureInjectingStorageAdapter(SQLiteAdapter()), StorageAdapter)


def test_no_failure_armed_behaves_like_the_wrapped_adapter():
    db = FailureInjectingStorageAdapter(SQLiteAdapter())
    memory = _memory("Project Alpha uses PostgreSQL.")

    db.store(memory)

    assert db.get(memory.id).content == memory.content


def test_armed_failure_raises_instead_of_delegating():
    db = FailureInjectingStorageAdapter(SQLiteAdapter())
    db.inject_failure("store")

    with pytest.raises(StorageFailure):
        db.store(_memory("Project Alpha uses PostgreSQL."))


def test_a_failed_store_never_reaches_the_real_adapter():
    # The point of the injector: a failed call leaves the underlying
    # data exactly as it was before the call -- no partial write.
    db = FailureInjectingStorageAdapter(SQLiteAdapter())
    memory = _memory("Project Alpha uses PostgreSQL.")
    db.inject_failure("store")

    with pytest.raises(StorageFailure):
        db.store(memory)

    db.clear_failure()
    assert db.get(memory.id) is None


def test_fail_after_lets_n_calls_succeed_first():
    db = FailureInjectingStorageAdapter(SQLiteAdapter())
    db.inject_failure("get", fail_after=2)

    db.get("x")
    db.get("x")
    with pytest.raises(StorageFailure):
        db.get("x")


def test_fail_count_bounds_a_transient_outage_then_recovers():
    db = FailureInjectingStorageAdapter(SQLiteAdapter())
    db.inject_failure("search", fail_count=2)

    with pytest.raises(StorageFailure):
        db.search("x")
    with pytest.raises(StorageFailure):
        db.search("x")
    # Third call: the outage window has passed, back to normal.
    assert db.search("x") == []


def test_clear_failure_disarms_immediately():
    db = FailureInjectingStorageAdapter(SQLiteAdapter())
    db.inject_failure("list_all")
    db.clear_failure()

    assert db.list_all() == []


def test_retrieval_engine_propagates_a_storage_failure_rather_than_swallowing_it():
    # "Reliability" proven the other direction: the rest of the system
    # doesn't mask a real storage outage as an empty/wrong result.
    db = FailureInjectingStorageAdapter(SQLiteAdapter())
    db.store(_memory("Project Alpha uses PostgreSQL."))
    db.inject_failure("search")

    with pytest.raises(StorageFailure):
        RetrievalEngine(db).retrieve("PostgreSQL")
