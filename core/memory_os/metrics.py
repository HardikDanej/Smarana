"""
Memory-specific metrics (Plan Step 92): Recall@K, precision@K,
contradiction rate, and friends, as real numbers.

`tests/test_evaluation_framework.py` (Phase 9) already answers "does
retrieval find the right memory" as pass/fail. This module answers "what
fraction of the time, and how well ranked" as an actual float a
benchmark can report and a dashboard can track over time -- Step 92's
own framing: "here are the numbers," not "I think it works."

Every function here is a pure function over data a caller already has
(a set of relevant IDs, a list of retrieved IDs, a list of
MemoryObjects) -- no dependency on StorageAdapter, RetrievalEngine, or
any adapter, and no import of Telemetry either. `memory_evals/` (Step
93) is what runs the real engine end to end and reports these through
Step 91's Telemetry; this module only computes them.
"""

from __future__ import annotations

from .models import MemoryObject, TruthStatus
from .relationships import STALE_LIFECYCLE_STATES


def recall_at_k(relevant_ids: set[str], retrieved_ids: list[str], k: "int | None" = None) -> float:
    """Fraction of relevant items found in the top k retrieved. Step 49's
    "Recall" dimension, as a number instead of a boolean. Undefined
    ground truth (nothing relevant to find) returns 0.0, not a
    ZeroDivisionError -- an empty relevant set isn't a system failure to
    divide by."""
    if not relevant_ids:
        return 0.0
    considered = retrieved_ids[:k] if k is not None else retrieved_ids
    found = relevant_ids & set(considered)
    return len(found) / len(relevant_ids)


def precision_at_k(relevant_ids: set[str], retrieved_ids: list[str], k: "int | None" = None) -> float:
    """Fraction of the top k retrieved items that are actually relevant.
    An empty top-k (nothing retrieved) returns 0.0 -- no evidence of
    precision either way, but not an error."""
    considered = retrieved_ids[:k] if k is not None else retrieved_ids
    if not considered:
        return 0.0
    found = relevant_ids & set(considered)
    return len(found) / len(considered)


def contradiction_rate(memories: list[MemoryObject]) -> float:
    """What fraction of a memory set is currently marked CONTRADICTED
    (Step 34's truth_status). Not a verdict that a rate is good or bad on
    its own -- a rising rate over time is the actual signal Step 92's
    "here are the numbers" is meant to surface to a dashboard."""
    if not memories:
        return 0.0
    contradicted = sum(1 for m in memories if m.truth_status == TruthStatus.CONTRADICTED)
    return contradicted / len(memories)


def staleness_rate(memories: list[MemoryObject]) -> float:
    """Fraction of a memory set that is no longer live (SUPERSEDED/
    FORGOTTEN/ARCHIVED) -- the same definition relationships.py's
    belief-maintenance primitive already uses (Step 55), reused here
    rather than redefined."""
    if not memories:
        return 0.0
    stale = sum(1 for m in memories if m.lifecycle_state in STALE_LIFECYCLE_STATES)
    return stale / len(memories)


def provenance_coverage(memories: list[MemoryObject]) -> float:
    """Step 49's Provenance dimension as a number: fraction of memories
    that carry a `source_id` -- can actually answer "where specifically
    did this come from," not just a source_type category."""
    if not memories:
        return 0.0
    with_provenance = sum(1 for m in memories if m.source_id is not None)
    return with_provenance / len(memories)


def mean_reciprocal_rank(relevant_ids: set[str], retrieved_ids: list[str]) -> float:
    """1/rank of the first relevant result, 0.0 if none of the retrieved
    items are relevant at all. A ranking-quality complement to recall/
    precision: recall@k asks "is it in there somewhere," MRR asks "how
    far did you have to look."""
    for rank, memory_id in enumerate(retrieved_ids, start=1):
        if memory_id in relevant_ids:
            return 1.0 / rank
    return 0.0
