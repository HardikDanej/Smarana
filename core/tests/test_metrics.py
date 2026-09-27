"""Phase 18 (Plan Step 92): memory-specific metrics as real numbers."""

from memory_os import (
    LifecycleState,
    MemoryScope,
    SemanticType,
    SourceType,
    TruthStatus,
    contradiction_rate,
    mean_reciprocal_rank,
    precision_at_k,
    provenance_coverage,
    recall_at_k,
    staleness_rate,
)
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


# --- recall_at_k ---


def test_recall_at_k_perfect_match():
    assert recall_at_k({"a", "b"}, ["a", "b", "c"]) == 1.0


def test_recall_at_k_partial_match():
    assert recall_at_k({"a", "b"}, ["a", "c"]) == 0.5


def test_recall_at_k_no_match():
    assert recall_at_k({"a"}, ["x", "y"]) == 0.0


def test_recall_at_k_respects_k():
    # Relevant item is retrieved, but outside the top k.
    assert recall_at_k({"a"}, ["x", "y", "a"], k=2) == 0.0
    assert recall_at_k({"a"}, ["x", "y", "a"], k=3) == 1.0


def test_recall_at_k_empty_ground_truth_is_zero_not_a_crash():
    assert recall_at_k(set(), ["a", "b"]) == 0.0


# --- precision_at_k ---


def test_precision_at_k_all_relevant():
    assert precision_at_k({"a", "b"}, ["a", "b"]) == 1.0


def test_precision_at_k_half_relevant():
    assert precision_at_k({"a"}, ["a", "b"]) == 0.5


def test_precision_at_k_respects_k():
    assert precision_at_k({"a"}, ["a", "b", "c"], k=1) == 1.0
    assert precision_at_k({"a"}, ["b", "a", "c"], k=1) == 0.0


def test_precision_at_k_empty_retrieved_is_zero_not_a_crash():
    assert precision_at_k({"a"}, []) == 0.0


# --- mean_reciprocal_rank ---


def test_mrr_first_result_is_relevant():
    assert mean_reciprocal_rank({"a"}, ["a", "b"]) == 1.0


def test_mrr_second_result_is_relevant():
    assert mean_reciprocal_rank({"a"}, ["b", "a"]) == 0.5


def test_mrr_nothing_relevant_retrieved():
    assert mean_reciprocal_rank({"a"}, ["x", "y"]) == 0.0


# --- contradiction_rate ---


def test_contradiction_rate_counts_only_contradicted_status():
    memories = [
        _memory("a", truth_status=TruthStatus.CONTRADICTED),
        _memory("b", truth_status=TruthStatus.BELIEVED),
        _memory("c", truth_status=TruthStatus.CONFIRMED),
        _memory("d", truth_status=TruthStatus.CONTRADICTED),
    ]
    assert contradiction_rate(memories) == 0.5


def test_contradiction_rate_empty_set_is_zero():
    assert contradiction_rate([]) == 0.0


# --- staleness_rate ---


def test_staleness_rate_counts_superseded_forgotten_archived():
    memories = [
        _memory("a", lifecycle_state=LifecycleState.SUPERSEDED),
        _memory("b", lifecycle_state=LifecycleState.FORGOTTEN),
        _memory("c", lifecycle_state=LifecycleState.ARCHIVED),
        _memory("d", lifecycle_state=LifecycleState.VALIDATED),
    ]
    assert staleness_rate(memories) == 0.75


def test_staleness_rate_empty_set_is_zero():
    assert staleness_rate([]) == 0.0


# --- provenance_coverage ---


def test_provenance_coverage_counts_source_id_present():
    memories = [
        _memory("a", source_id="conversation-1"),
        _memory("b", source_id=None),
        _memory("c", source_id="conversation-2"),
    ]
    assert provenance_coverage(memories) == 2 / 3


def test_provenance_coverage_empty_set_is_zero():
    assert provenance_coverage([]) == 0.0
