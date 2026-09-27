"""
The first evaluation framework (Plan Step 49): "Create automated tests
for" nine named dimensions, "before making the system complicated."

Each test below is named after the dimension it evaluates, so this file
IS the benchmark suite Step 49 asks for -- not a metaphor for one.
Isolation was originally deferred here as a known gap ("nothing built
through Phase 9 enforces [scope]... revisit this comment when Phase 13
is built, not before") -- Phase 13's access_control.py now makes it
real, so test_isolation below replaces that deferral with an actual
passing assertion. All nine dimensions are covered.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from adapters.claude_provider import ClaudeProvider
from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import (
    LifecycleState,
    MemoryScope,
    SemanticType,
    SourceType,
    TruthStatus,
    mark_superseded,
)
from memory_os.compression import MemoryCompressor
from memory_os.extraction import ExtractionPipeline
from memory_os.models import MemoryObject
from memory_os.reflection import build_reflection
from memory_os.retrieval import RetrievalEngine

from .fakes import FakeLLMProvider


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


# --- 1. Recall: can it find the correct memory among decoys? ---

def test_recall():
    db = SQLiteAdapter()
    target = _memory("Project Alpha uses PostgreSQL for its primary datastore.")
    db.store(target)
    for i in range(20):
        db.store(_memory(f"unrelated decoy memory number {i} about the weather"))

    results = RetrievalEngine(db).retrieve("What database does Project Alpha use?")

    assert any(r.memory.id == target.id for r in results)


# --- 2. Precision: does it avoid irrelevant memories at the top? ---

def test_precision():
    db = SQLiteAdapter()
    target = _memory("Project Alpha uses PostgreSQL for its primary datastore.")
    db.store(target)
    for i in range(20):
        db.store(_memory(f"unrelated decoy memory number {i} about the weather"))

    results = RetrievalEngine(db).retrieve("What database does Project Alpha use?", top_k=3)

    assert results[0].memory.id == target.id


# --- 3. Temporal correctness: retrieves what was true AT the requested time ---

def test_temporal_correctness():
    db = SQLiteAdapter()
    old, new = (
        _memory("Project Alpha uses AWS.", valid_from=_dt("2026-01-01"), valid_until=_dt("2026-03-01")),
        _memory("Project Alpha uses GCP.", valid_from=_dt("2026-03-01"), valid_until=None),
    )
    db.store(old)
    db.store(new)

    # Both docs share "Project Alpha" vocabulary, so keyword/vector retrieval
    # finds both candidates -- the point of this test is that the `as_of`
    # filter then correctly narrows to whichever one was valid at that time.
    as_of_february = RetrievalEngine(db).retrieve("Project Alpha", as_of=_dt("2026-02-01"), top_k=10)
    as_of_june = RetrievalEngine(db).retrieve("Project Alpha", as_of=_dt("2026-06-01"), top_k=10)

    assert {r.memory.id for r in as_of_february} == {old.id}
    assert {r.memory.id for r in as_of_june} == {new.id}


# --- 4. Conflict handling: distinguishes old and new via supersession ---

def test_conflict_handling():
    db = SQLiteAdapter()
    old = _memory("Project Alpha uses AWS.")
    new = _memory("Project Alpha uses GCP.")
    updated_old, updated_new = mark_superseded(old, new)
    db.store(updated_old)
    db.store(updated_new)

    stored_old = db.get(updated_old.id)
    stored_new = db.get(updated_new.id)

    assert stored_old.lifecycle_state == LifecycleState.SUPERSEDED
    assert stored_old.truth_status == TruthStatus.SUPERSEDED
    assert stored_old.superseded_by == stored_new.id
    assert stored_new.supersedes == stored_old.id


# --- 5. Provenance: can it explain where a memory came from? ---

def test_provenance():
    db = SQLiteAdapter()
    memory = _memory(
        "Project Alpha uses PostgreSQL.",
        source_type=SourceType.USER_STATEMENT,
        source_id="conversation-42",
    )
    db.store(memory)

    fetched = db.get(memory.id)

    assert fetched.source_type == SourceType.USER_STATEMENT
    assert fetched.source_id == "conversation-42"

    # A derived (reflective) memory must trace back to its evidence too.
    episode = _memory("Deployment failed due to a missing variable.", semantic_type=SemanticType.FAILURE)
    reflection = build_reflection([episode], FakeLLMProvider(), scope=MemoryScope.PROJECT)
    assert reflection.evidence == [episode.id]


# --- 6. Isolation: can Agent A accidentally retrieve Agent B's private memory? ---

def test_isolation():
    db = SQLiteAdapter()
    agent_a_private = _memory("Agent A's private plan.", owner_id="agent-A")
    agent_b_private = _memory("Agent B's private plan.", owner_id="agent-B")
    db.store(agent_a_private)
    db.store(agent_b_private)

    results_as_a = RetrievalEngine(db).retrieve("plan", principal_id="agent-A")

    assert {r.memory.id for r in results_as_a} == {agent_a_private.id}


# --- 7. Consolidation: does repeated information become useful abstraction? ---

def test_consolidation():
    repeated = [
        _memory("Deployment failed: missing env variable.", semantic_type=SemanticType.FAILURE),
        _memory("Deployment failed again: missing env variable.", semantic_type=SemanticType.FAILURE),
        _memory("Deployment failed: missing env variable, third time.", semantic_type=SemanticType.FAILURE),
    ]

    reflection = build_reflection(repeated, FakeLLMProvider(), scope=MemoryScope.PROJECT)

    assert reflection.semantic_type == SemanticType.REFLECTIVE
    assert len(reflection.evidence) == 3

    # Compression's dedup independently proves the same "many -> fewer" shape.
    duplicated = [_memory("Project Alpha uses PostgreSQL.") for _ in range(5)]
    compressed = MemoryCompressor(provider=None).compress(duplicated)
    assert len(compressed) == 1


# --- 8. Forgetting: can obsolete information stop appearing? ---

def test_forgetting():
    db = SQLiteAdapter()
    memory = _memory("Project Alpha uses PostgreSQL.")
    db.store(memory)
    assert db.search("PostgreSQL") != []

    db.delete(memory.id)

    assert db.search("PostgreSQL") == []
    assert db.get(memory.id) is None


# --- 9. Hallucination resistance: does the system refuse to invent memories? ---

def test_hallucination_resistance():
    # The extraction pipeline never invents an entity the provider didn't
    # actually return -- absence stays absence, not a fabricated value.
    provider = FakeLLMProvider(extraction_result={})  # no entity supplied

    memory = ExtractionPipeline(provider=provider).extract_memory(
        "Some ambiguous statement.", source_type=SourceType.USER_STATEMENT, scope=MemoryScope.PROJECT
    )
    assert memory.entities == []

    # The Claude adapter refuses to fabricate structured data from
    # unparseable model output -- it raises rather than guessing.
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="not json at all")]
    )
    claude = ClaudeProvider(client=client)
    with pytest.raises(ValueError):
        claude.extract("some text", schema={"entity": "..."})
