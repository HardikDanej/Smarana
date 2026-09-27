from datetime import datetime, timezone

import pytest

from memory_os import (
    ConflictResolver,
    LifecycleState,
    MemoryScope,
    SemanticType,
    SourceType,
    TruthStatus,
    apply_correction,
    resolve_uncertain,
)
from memory_os.models import MemoryObject


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


# --- Step 58: ConflictResolver -- clear time ordering, a state transition ---


def test_resolve_closes_earlier_validity_window_at_later_event_time():
    earlier = _memory("Project Alpha uses AWS.", observed_at=_dt("2026-01-05"))
    later = _memory(
        "Project Alpha uses GCP.",
        observed_at=_dt("2026-03-01"),
        valid_from=_dt("2026-03-01"),
    )

    updated_earlier, updated_later = ConflictResolver().resolve(earlier, later)

    assert updated_earlier.valid_until == _dt("2026-03-01")
    assert updated_earlier.lifecycle_state == LifecycleState.SUPERSEDED
    assert updated_later.supersedes == updated_earlier.id


def test_resolve_does_not_overwrite_an_already_closed_validity_window():
    earlier = _memory(
        "Project Alpha uses AWS.",
        observed_at=_dt("2026-01-05"),
        valid_until=_dt("2026-02-01"),  # already closed by something else
    )
    later = _memory("Project Alpha uses GCP.", observed_at=_dt("2026-03-01"))

    updated_earlier, _ = ConflictResolver().resolve(earlier, later)

    assert updated_earlier.valid_until == _dt("2026-02-01")


def test_resolve_rejects_reversed_knowledge_time_ordering():
    a = _memory("Project Alpha uses AWS.", observed_at=_dt("2026-03-01"))
    b = _memory("Project Alpha uses GCP.", observed_at=_dt("2026-01-01"))

    with pytest.raises(ValueError):
        ConflictResolver().resolve(a, b)


# --- Step 59: genuine uncertainty -- no forced winner ---


def test_resolve_uncertain_normalizes_confidence_into_a_probability_distribution():
    # Plan's own example: PostgreSQL 0.54-ish, MySQL 0.46-ish.
    a = _memory("Customer uses PostgreSQL.", confidence=0.54)
    b = _memory("Customer uses MySQL.", confidence=0.46)

    belief = resolve_uncertain([a, b])

    assert belief.status == "uncertain"
    probs = {memory.content: prob for memory, prob in belief.candidates}
    assert abs(probs["Customer uses PostgreSQL."] - 0.54) < 1e-9
    assert abs(probs["Customer uses MySQL."] - 0.46) < 1e-9
    assert abs(sum(probs.values()) - 1.0) < 1e-9


def test_resolve_uncertain_handles_all_zero_confidence_without_dividing_by_zero():
    a = _memory("Candidate A", confidence=0.0)
    b = _memory("Candidate B", confidence=0.0)

    belief = resolve_uncertain([a, b])

    probs = [prob for _, prob in belief.candidates]
    assert probs == [0.5, 0.5]


def test_resolve_uncertain_requires_at_least_one_candidate():
    with pytest.raises(ValueError):
        resolve_uncertain([])


# --- Step 60: correction chain ---


def test_apply_correction_creates_old_correction_new_chain():
    old = _memory("Project Alpha uses AWS.")

    updated_old, correction = apply_correction(old, "Project Alpha actually uses GCP.")

    assert updated_old.lifecycle_state == LifecycleState.SUPERSEDED
    assert updated_old.truth_status == TruthStatus.SUPERSEDED
    assert correction.content == "Project Alpha actually uses GCP."
    assert correction.supersedes == updated_old.id
    assert correction.metadata["is_correction"] is True
    assert correction.metadata["corrects"] == updated_old.id


def test_apply_correction_preserves_the_old_memory_rather_than_deleting_it():
    old = _memory("Project Alpha uses AWS.")
    updated_old, _ = apply_correction(old, "Project Alpha uses GCP.")

    # Still inspectable -- corrected, not erased.
    assert updated_old.content == "Project Alpha uses AWS."


def test_apply_correction_default_source_is_user_statement():
    old = _memory("Project Alpha uses AWS.")
    _, correction = apply_correction(old, "Project Alpha uses GCP.")
    assert correction.source_type == SourceType.USER_STATEMENT
