"""
Benchmark scenarios (Plan Step 93): ground-truth cases for the
memory-evals runner. Each RetrievalScenario names, up front, which
memories are actually relevant to its query -- the runner never guesses
at ground truth, it's handed one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from memory_os import MemoryScope, SemanticType, SourceType
from memory_os.models import MemoryObject


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


@dataclass(frozen=True)
class RetrievalScenario:
    name: str
    query: str
    memories: list[MemoryObject]
    relevant_ids: frozenset
    top_k: int = 10


def _needle_in_decoys() -> RetrievalScenario:
    # Phase 9's own Recall/Precision worked example, as a scenario.
    target = _memory("Project Alpha uses PostgreSQL for its primary datastore.")
    decoys = [_memory(f"unrelated decoy memory number {i} about the weather") for i in range(20)]
    return RetrievalScenario(
        name="needle_in_decoys",
        query="What database does Project Alpha use?",
        memories=[target, *decoys],
        relevant_ids=frozenset({target.id}),
    )


def _temporal_disambiguation() -> RetrievalScenario:
    # Phase 9's temporal-correctness worked example: two memories share
    # vocabulary, only one is current, no as_of means "give me now."
    old = _memory("Project Alpha uses AWS.", valid_from=_dt("2026-01-01"), valid_until=_dt("2026-03-01"))
    new = _memory("Project Alpha uses GCP.", valid_from=_dt("2026-03-01"), valid_until=None)
    return RetrievalScenario(
        name="temporal_disambiguation",
        query="Project Alpha",
        memories=[old, new],
        relevant_ids=frozenset({new.id}),
    )


def _multiple_relevant_memories() -> RetrievalScenario:
    # Ground truth isn't always a single memory -- recall/precision have
    # to hold up when more than one retrieved item is genuinely correct.
    a = _memory("Project Alpha's database is PostgreSQL 16.")
    b = _memory("Project Alpha's database runs on managed cloud infrastructure.")
    decoys = [_memory(f"irrelevant note number {i}") for i in range(10)]
    return RetrievalScenario(
        name="multiple_relevant_memories",
        query="Tell me about Project Alpha's database.",
        memories=[a, b, *decoys],
        relevant_ids=frozenset({a.id, b.id}),
    )


def _no_relevant_memory_exists() -> RetrievalScenario:
    # The honest negative case: nothing in the store answers the query.
    # A benchmark that only ever scores scenarios with a right answer
    # can't distinguish "found it" from "always guesses something."
    decoys = [_memory(f"unrelated note number {i} about office supplies") for i in range(10)]
    return RetrievalScenario(
        name="no_relevant_memory_exists",
        query="What is Project Zeta's deployment region?",
        memories=decoys,
        relevant_ids=frozenset(),
    )


SCENARIOS: list[RetrievalScenario] = [
    _needle_in_decoys(),
    _temporal_disambiguation(),
    _multiple_relevant_memories(),
    _no_relevant_memory_exists(),
]
