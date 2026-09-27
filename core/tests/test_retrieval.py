from datetime import datetime, timezone

from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import LifecycleState, MemoryScope, SemanticType, SourceType, mark_superseded
from memory_os.models import MemoryObject
from memory_os.retrieval import (
    KeywordRetriever,
    RelationshipRetriever,
    RetrievalEngine,
    TemporalRetriever,
    VectorRetriever,
)


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_keyword_retriever_finds_exact_match():
    db = SQLiteAdapter()
    match = _memory("Project Alpha uses PostgreSQL.")
    db.store(match)
    db.store(_memory("Project Beta uses MongoDB."))

    results = KeywordRetriever(db).retrieve("PostgreSQL")

    assert [r.memory.id for r in results] == [match.id]
    assert results[0].matched_by == {"keyword"}


def test_vector_retriever_finds_shared_vocabulary_without_exact_substring():
    db = SQLiteAdapter()
    match = _memory("Project Alpha migrated its database off MongoDB")
    db.store(match)
    db.store(_memory("The weather today is sunny and warm"))

    results = VectorRetriever(db).retrieve("Which project moved away from MongoDB?")

    assert results
    assert results[0].memory.id == match.id
    assert results[0].matched_by == {"vector"}


def test_temporal_retriever_filters_by_validity_window():
    db = SQLiteAdapter()
    aws_era = _memory(
        "Project Alpha uses AWS.",
        valid_from=_dt("2026-01-01"),
        valid_until=_dt("2026-03-01"),
    )
    gcp_era = _memory(
        "Project Alpha uses GCP.",
        valid_from=_dt("2026-03-01"),
        valid_until=None,
    )
    db.store(aws_era)
    db.store(gcp_era)

    valid_in_february = TemporalRetriever(db).valid_as_of(_dt("2026-02-01"))
    valid_in_june = TemporalRetriever(db).valid_as_of(_dt("2026-06-01"))

    assert [m.memory.id for m in valid_in_february] == [aws_era.id]
    assert [m.memory.id for m in valid_in_june] == [gcp_era.id]


def test_relationship_retriever_finds_shared_entities():
    db = SQLiteAdapter()
    anchor = _memory("Project Alpha uses PostgreSQL.", entities=["Project Alpha"])
    related = _memory("Project Alpha deploys to GCP.", entities=["Project Alpha"])
    unrelated = _memory("Project Beta uses MongoDB.", entities=["Project Beta"])
    db.store(anchor)
    db.store(related)
    db.store(unrelated)

    results = RelationshipRetriever(db).related(anchor.id)

    assert [r.memory.id for r in results] == [related.id]


def test_relationship_retriever_returns_empty_for_entityless_anchor():
    db = SQLiteAdapter()
    anchor = _memory("A memory with no entities.")
    db.store(anchor)

    assert RelationshipRetriever(db).related(anchor.id) == []


def test_retrieval_engine_fuses_keyword_and_vector_hits():
    db = SQLiteAdapter()
    match = _memory("Project Alpha uses PostgreSQL.")
    db.store(match)
    db.store(_memory("Completely unrelated memory about weather."))

    results = RetrievalEngine(db).retrieve("PostgreSQL")

    assert results
    top = results[0]
    assert top.memory.id == match.id
    # Found by both retrievers -- keyword (exact) and vector (shared vocab
    # with itself) -- so both should be recorded and the score should
    # reflect both contributions, not just one.
    assert "keyword" in top.matched_by
    assert "vector" in top.matched_by


def test_retrieval_engine_respects_as_of_temporal_filter():
    db = SQLiteAdapter()
    aws_era = _memory(
        "Project Alpha uses AWS.",
        valid_from=_dt("2026-01-01"),
        valid_until=_dt("2026-03-01"),
    )
    db.store(aws_era)

    results_within_window = RetrievalEngine(db).retrieve("AWS", as_of=_dt("2026-02-01"))
    results_outside_window = RetrievalEngine(db).retrieve("AWS", as_of=_dt("2026-06-01"))

    assert any(r.memory.id == aws_era.id for r in results_within_window)
    assert not any(r.memory.id == aws_era.id for r in results_outside_window)


def test_default_retrieval_prefers_current_over_superseded():
    # Step 53, Rule G: "Current context should normally prefer currently
    # valid information." Both memories share the same content (so they
    # score identically on keyword+vector alone); only lifecycle_state
    # distinguishes them, and that alone should decide the ranking.
    db = SQLiteAdapter()
    old = _memory("Project Alpha uses AWS.")
    new = _memory("Project Alpha uses AWS.")
    updated_old, updated_new = mark_superseded(old, new)
    db.store(updated_old)
    db.store(updated_new)

    results = RetrievalEngine(db).retrieve("Project Alpha")

    assert results[0].memory.id == updated_new.id


def test_historical_as_of_query_still_surfaces_superseded_memory_undamped():
    # Step 53, Rule F: a superseded fact remains fully retrievable when
    # the query is explicitly about its own historical validity window --
    # no ranking penalty should apply there.
    db = SQLiteAdapter()
    old = _memory(
        "Project Alpha uses AWS.",
        valid_from=_dt("2026-01-01"),
        valid_until=_dt("2026-03-01"),
    )
    new = _memory("Project Alpha uses GCP.", valid_from=_dt("2026-03-01"), valid_until=None)
    updated_old, updated_new = mark_superseded(old, new)
    # mark_superseded doesn't touch validity windows -- set them to match
    # the historical scenario being tested.
    db.store(updated_old.new_version(valid_from=old.valid_from, valid_until=old.valid_until))
    db.store(updated_new.new_version(valid_from=new.valid_from, valid_until=new.valid_until))

    results = RetrievalEngine(db).retrieve("Project Alpha", as_of=_dt("2026-02-01"))

    assert len(results) == 1
    assert results[0].memory.lifecycle_state == LifecycleState.SUPERSEDED


def test_default_retrieval_pulls_in_entity_linked_neighbors():
    # Step 64: hybrid retrieval -- a memory reachable only through a
    # SHARED ENTITY with a keyword/vector hit should still surface.
    db = SQLiteAdapter()
    anchor = _memory("Project Alpha uses PostgreSQL.", entities=["Project Alpha"])
    linked = _memory(
        "Deploy Project Alpha with the standard pipeline.", entities=["Project Alpha"]
    )
    unrelated = _memory("Completely unrelated memory about weather.")
    db.store(anchor)
    db.store(linked)
    db.store(unrelated)

    results = RetrievalEngine(db).retrieve("PostgreSQL")

    ids = {r.memory.id for r in results}
    assert anchor.id in ids
    assert linked.id in ids
    assert unrelated.id not in ids
    linked_result = next(r for r in results if r.memory.id == linked.id)
    assert "relationship" in linked_result.matched_by


def test_include_relationships_false_disables_hybrid_expansion():
    db = SQLiteAdapter()
    anchor = _memory("Project Alpha uses PostgreSQL.", entities=["Project Alpha"])
    linked = _memory(
        "Deploy Project Alpha with the standard pipeline.", entities=["Project Alpha"]
    )
    db.store(anchor)
    db.store(linked)

    results = RetrievalEngine(db).retrieve("PostgreSQL", include_relationships=False)

    ids = {r.memory.id for r in results}
    assert linked.id not in ids
