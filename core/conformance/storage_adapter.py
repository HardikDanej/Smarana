"""
StorageAdapter conformance suite (Plan Step 99).

The plan's own gap list (docs/UNIVERSAL_MEMORY_OS_PLAN.md, "What's not
in these four files") names this directly: "No adapter certification or
versioning contract... Matters the moment anyone outside your team
writes an adapter." This module is that contract, made runnable: any
StorageAdapter -- SQLiteAdapter, PostgresAdapter, or a future third-
party one -- proves itself compatible by passing every check here
against a factory that builds a fresh instance. Not a claim that two
adapters behave the same; a test suite that actually checks.

Lives in its own top-level package, not memory_os (this is a tool for
people AUTHORING adapters, the same relationship memory_evals/ has to
benchmarking, not engine code) and not adapters/ (it imports no vendor
technology of its own -- it is generic over whichever StorageAdapter a
caller hands it).
"""

from __future__ import annotations

from typing import Callable

from memory_os.models import MemoryObject, MemoryScope, SemanticType, SourceType
from memory_os.storage import StorageAdapter

AdapterFactory = Callable[[], StorageAdapter]


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def assert_satisfies_storage_adapter_protocol(make_adapter: AdapterFactory) -> None:
    adapter = make_adapter()
    assert isinstance(adapter, StorageAdapter), (
        f"{type(adapter).__name__} does not satisfy memory_os.storage.StorageAdapter"
    )


def assert_store_and_get_round_trips(make_adapter: AdapterFactory) -> None:
    adapter = make_adapter()
    memory = _memory("Project Alpha uses PostgreSQL.")
    adapter.store(memory)
    fetched = adapter.get(memory.id)
    assert fetched is not None, "get() returned None for a just-stored memory"
    assert fetched.id == memory.id
    assert fetched.content == memory.content


def assert_get_missing_returns_none(make_adapter: AdapterFactory) -> None:
    adapter = make_adapter()
    assert adapter.get("does-not-exist") is None


def assert_update_overwrites_stored_content(make_adapter: AdapterFactory) -> None:
    adapter = make_adapter()
    memory = _memory("Project Alpha uses AWS.")
    adapter.store(memory)
    revised = memory.new_version(content="Project Alpha uses GCP.")
    adapter.update(revised)
    fetched = adapter.get(memory.id)
    assert fetched.content == "Project Alpha uses GCP."
    assert fetched.version == 2


def assert_delete_removes_from_storage_and_search(make_adapter: AdapterFactory) -> None:
    adapter = make_adapter()
    memory = _memory("Project Alpha uses PostgreSQL.")
    adapter.store(memory)
    adapter.delete(memory.id)
    assert adapter.get(memory.id) is None
    assert adapter.search("PostgreSQL") == []


def assert_search_finds_matching_keyword(make_adapter: AdapterFactory) -> None:
    adapter = make_adapter()
    match = _memory("Project Alpha uses PostgreSQL.")
    other = _memory("Project Beta uses MongoDB.")
    adapter.store(match)
    adapter.store(other)
    results = adapter.search("PostgreSQL")
    assert [m.id for m in results] == [match.id]


def assert_search_with_no_matches_returns_empty_list(make_adapter: AdapterFactory) -> None:
    adapter = make_adapter()
    adapter.store(_memory("Project Alpha uses PostgreSQL."))
    assert adapter.search("nonexistent-keyword-zzz") == []


def assert_list_all_returns_every_stored_memory(make_adapter: AdapterFactory) -> None:
    adapter = make_adapter()
    adapter.store(_memory("first memory"))
    adapter.store(_memory("second memory"))
    assert len(adapter.list_all()) == 2


CONFORMANCE_CHECKS: list[Callable[[AdapterFactory], None]] = [
    assert_satisfies_storage_adapter_protocol,
    assert_store_and_get_round_trips,
    assert_get_missing_returns_none,
    assert_update_overwrites_stored_content,
    assert_delete_removes_from_storage_and_search,
    assert_search_finds_matching_keyword,
    assert_search_with_no_matches_returns_empty_list,
    assert_list_all_returns_every_stored_memory,
]


def certify(make_adapter: AdapterFactory) -> None:
    """Runs every conformance check against a fresh adapter instance --
    `make_adapter` is called once per check, not once total, so one
    check's mutations can never leak into the next. Raises the first
    AssertionError hit; a caller wanting all failures at once should
    call CONFORMANCE_CHECKS' entries individually (see
    tests/test_adapter_conformance.py's parametrization)."""
    for check in CONFORMANCE_CHECKS:
        check(make_adapter)
