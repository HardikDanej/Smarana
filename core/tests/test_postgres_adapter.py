"""
Phase 17 (Plan Steps 86-89): PostgresAdapter over a real local Postgres+
pgvector instance. Every test here skips cleanly (see conftest.py) when
that instance isn't reachable -- it never falls back to a mock, which
would prove nothing about the actual database behavior these steps are
about (especially Step 82's RLS policy, which only means something when
a real Postgres enforces it).
"""

import psycopg2
import pytest

from memory_os import MemoryScope, SemanticType, SourceType
from memory_os.models import MemoryObject
from memory_os.relationships import RelationshipType


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


# --- Step 86: StorageAdapter contract, same coverage as SQLiteAdapter's ---


def test_store_and_get_roundtrips(postgres_adapter):
    memory = _memory("Project Alpha uses PostgreSQL.")
    postgres_adapter.store(memory)

    fetched = postgres_adapter.get(memory.id)

    assert fetched is not None
    assert fetched.id == memory.id
    assert fetched.content == memory.content


def test_get_missing_returns_none(postgres_adapter):
    assert postgres_adapter.get("does-not-exist") is None


def test_update_overwrites_stored_content(postgres_adapter):
    memory = _memory("Project Alpha uses AWS.")
    postgres_adapter.store(memory)

    revised = memory.new_version(content="Project Alpha uses GCP.")
    postgres_adapter.update(revised)

    fetched = postgres_adapter.get(memory.id)
    assert fetched.content == "Project Alpha uses GCP."
    assert fetched.version == 2


def test_delete_removes_from_storage_and_search(postgres_adapter):
    memory = _memory("Project Alpha uses PostgreSQL.")
    postgres_adapter.store(memory)

    postgres_adapter.delete(memory.id)

    assert postgres_adapter.get(memory.id) is None
    assert postgres_adapter.search("PostgreSQL") == []


def test_list_all_returns_every_stored_memory(postgres_adapter):
    postgres_adapter.store(_memory("first memory"))
    postgres_adapter.store(_memory("second memory"))

    assert len(postgres_adapter.list_all()) == 2


def test_search_finds_matching_keyword(postgres_adapter):
    match = _memory("Project Alpha uses PostgreSQL.")
    other = _memory("Project Beta uses MongoDB.")
    postgres_adapter.store(match)
    postgres_adapter.store(other)

    results = postgres_adapter.search("PostgreSQL")

    assert [m.id for m in results] == [match.id]


def test_search_uses_websearch_syntax_so_punctuation_never_raises(postgres_adapter):
    # websearch_to_tsquery is built for raw user text -- unlike SQLite's
    # FTS5 adapter, nothing here needs to hand-quote every token first.
    postgres_adapter.store(_memory("What database are we using?"))

    results = postgres_adapter.search("What database are we using?")

    assert len(results) == 1


def test_search_with_no_matches_returns_empty_list(postgres_adapter):
    postgres_adapter.store(_memory("Project Alpha uses PostgreSQL."))
    assert postgres_adapter.search("nonexistent-keyword-zzz") == []


# --- Step 87: pgvector similarity search ---


def test_vector_search_ranks_the_closer_meaning_first(postgres_adapter):
    database_note = _memory("Project Alpha uses PostgreSQL for storage.")
    unrelated_note = _memory("The office coffee machine is broken again.")
    postgres_adapter.store(database_note)
    postgres_adapter.store(unrelated_note)

    results = postgres_adapter.vector_search("postgres database storage", top_k=2)

    assert results[0].id == database_note.id


def test_vector_search_respects_top_k(postgres_adapter):
    for i in range(5):
        postgres_adapter.store(_memory(f"Note number {i} about databases."))

    assert len(postgres_adapter.vector_search("databases", top_k=3)) == 3


# --- Step 88: hybrid full-text + vector search, one query ---


def test_hybrid_search_finds_the_lexical_match(postgres_adapter):
    exact = _memory("Project Alpha uses PostgreSQL for storage.")
    other = _memory("Project Beta uses a different stack entirely.")
    postgres_adapter.store(exact)
    postgres_adapter.store(other)

    results = postgres_adapter.hybrid_search("PostgreSQL storage")

    assert results[0].id == exact.id


def test_hybrid_search_alpha_zero_is_pure_vector_and_one_is_pure_text(postgres_adapter):
    lexical_match_semantic_mismatch = _memory("PostgreSQL PostgreSQL PostgreSQL database engine.")
    semantic_match_no_exact_words = _memory("A relational database system for storing structured records.")
    postgres_adapter.store(lexical_match_semantic_mismatch)
    postgres_adapter.store(semantic_match_no_exact_words)

    text_heavy = postgres_adapter.hybrid_search("PostgreSQL", alpha=1.0, top_k=1)
    assert text_heavy[0].id == lexical_match_semantic_mismatch.id


# --- Step 82 (closed for real): tenant isolation enforced at the DB layer ---


def test_unscoped_connection_sees_every_tenant_by_default(postgres_adapter):
    postgres_adapter.store(_memory("Tenant A's note.", tenant_id="tenant-a"))
    postgres_adapter.store(_memory("Tenant B's note.", tenant_id="tenant-b"))
    postgres_adapter.store(_memory("Nobody's tenant."))

    assert len(postgres_adapter.list_all()) == 3


def test_tenant_context_hides_every_other_tenants_rows(postgres_adapter):
    a = _memory("Tenant A's note.", tenant_id="tenant-a")
    b = _memory("Tenant B's note.", tenant_id="tenant-b")
    postgres_adapter.store(a)
    postgres_adapter.store(b)

    postgres_adapter.set_tenant_context("tenant-a")
    assert {m.id for m in postgres_adapter.list_all()} == {a.id}

    postgres_adapter.set_tenant_context("tenant-b")
    assert {m.id for m in postgres_adapter.list_all()} == {b.id}


def test_tenant_context_hides_untenanted_rows_too(postgres_adapter):
    # can_access_tenant's own rule, re-proven at the database layer: no
    # tenant_id means belongs to no tenant, not to every tenant.
    postgres_adapter.store(_memory("Tenant A's note.", tenant_id="tenant-a"))
    postgres_adapter.store(_memory("Nobody's tenant."))

    postgres_adapter.set_tenant_context("tenant-a")

    assert all(m.tenant_id == "tenant-a" for m in postgres_adapter.list_all())


def test_get_by_id_is_blocked_across_tenants_not_just_list_all(postgres_adapter):
    # The point of RLS over an app-side filter: every query path is
    # covered, not just the ones a caller remembered to filter.
    other_tenant = _memory("Tenant B's secret.", tenant_id="tenant-b")
    postgres_adapter.store(other_tenant)

    postgres_adapter.set_tenant_context("tenant-a")

    assert postgres_adapter.get(other_tenant.id) is None


def test_clearing_tenant_context_restores_the_unscoped_default(postgres_adapter):
    a = _memory("Tenant A's note.", tenant_id="tenant-a")
    b = _memory("Tenant B's note.", tenant_id="tenant-b")
    postgres_adapter.store(a)
    postgres_adapter.store(b)

    postgres_adapter.set_tenant_context("tenant-a")
    postgres_adapter.set_tenant_context(None)

    assert {m.id for m in postgres_adapter.list_all()} == {a.id, b.id}


def test_rls_holds_even_for_a_raw_query_that_bypasses_the_adapters_own_code(postgres_adapter):
    # The real proof this is a database wall, not an application filter:
    # a plain SELECT issued directly on the same connection, going
    # through none of PostgresAdapter's own Python methods, is still
    # bound by the tenant_isolation policy.
    other_tenant = _memory("Tenant B's secret.", tenant_id="tenant-b")
    postgres_adapter.store(other_tenant)

    postgres_adapter.set_tenant_context("tenant-a")
    with postgres_adapter._conn.cursor() as cur:
        cur.execute("SELECT id FROM memories WHERE id = %s", (other_tenant.id,))
        row = cur.fetchone()

    assert row is None


# --- Step 89: persisted relationship graph ---


def test_add_and_query_relationships(postgres_adapter):
    postgres_adapter.add_relationship("m1", RelationshipType.DERIVED_FROM, "m2")
    postgres_adapter.add_relationship("m1", RelationshipType.SUPPORTS, "m3")

    outgoing = postgres_adapter.relationships_from("m1")
    assert {(e.relationship_type, e.target_id) for e in outgoing} == {
        (RelationshipType.DERIVED_FROM, "m2"),
        (RelationshipType.SUPPORTS, "m3"),
    }

    incoming = postgres_adapter.relationships_to("m2")
    assert [e.source_id for e in incoming] == ["m1"]


def test_relationship_type_filter_narrows_the_query(postgres_adapter):
    postgres_adapter.add_relationship("m1", RelationshipType.DERIVED_FROM, "m2")
    postgres_adapter.add_relationship("m1", RelationshipType.SUPPORTS, "m3")

    only_derived = postgres_adapter.relationships_from("m1", RelationshipType.DERIVED_FROM)

    assert [e.target_id for e in only_derived] == ["m2"]


def test_sync_and_load_relationship_graph_round_trips(postgres_adapter):
    from memory_os.relationships import RelationshipGraph

    graph = RelationshipGraph()
    graph.add("m1", RelationshipType.DERIVED_FROM, "m2", note="original")
    graph.add("m2", RelationshipType.SUPPORTS, "m3")

    postgres_adapter.sync_relationship_graph(graph)
    reloaded = postgres_adapter.load_relationship_graph()

    assert [e.target_id for e in reloaded.outgoing("m1")] == ["m2"]
    assert reloaded.outgoing("m1")[0].metadata == {"note": "original"}
    assert [e.target_id for e in reloaded.outgoing("m2")] == ["m3"]


def test_delete_memory_also_removes_its_relationships(postgres_adapter):
    memory = _memory("A memory with lineage.")
    postgres_adapter.store(memory)
    postgres_adapter.add_relationship(memory.id, RelationshipType.DERIVED_FROM, "some-episode")

    postgres_adapter.delete(memory.id)

    assert postgres_adapter.relationships_from(memory.id) == []
