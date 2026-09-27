import pytest
from pydantic import ValidationError

from memory_os import (
    LifecycleState,
    MemoryObject,
    MemoryScope,
    SemanticType,
    SourceType,
    TruthStatus,
    mark_superseded,
)


def make_memory(**overrides) -> MemoryObject:
    defaults = dict(
        content="Project Alpha uses PostgreSQL.",
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def test_minimal_construction_applies_defaults():
    memory = make_memory()

    assert memory.version == 1
    assert memory.modality.value == "text"
    assert memory.lifecycle_state == LifecycleState.OBSERVED
    assert memory.truth_status == TruthStatus.BELIEVED
    assert 0.0 <= memory.confidence <= 1.0
    assert memory.supersedes is None
    assert memory.superseded_by is None


def test_confidence_and_truth_status_are_independent():
    # A memory can be reported with high confidence yet already be
    # contradicted -- Step 34: confidence != truth.
    memory = make_memory(confidence=0.9, truth_status=TruthStatus.CONTRADICTED)

    assert memory.confidence == 0.9
    assert memory.truth_status == TruthStatus.CONTRADICTED


@pytest.mark.parametrize("bad_confidence", [-0.1, 1.1])
def test_confidence_out_of_range_is_rejected(bad_confidence):
    with pytest.raises(ValidationError):
        make_memory(confidence=bad_confidence)


def test_invalid_semantic_type_is_rejected():
    with pytest.raises(ValidationError):
        make_memory(semantic_type="not_a_real_type")


def test_new_version_increments_and_preserves_identity():
    original = make_memory()
    revised = original.new_version(content="Project Alpha uses GCP.")

    assert revised.id == original.id
    assert revised.version == original.version + 1
    assert revised.created_at == original.created_at
    assert revised.updated_at >= original.updated_at
    assert revised.content == "Project Alpha uses GCP."
    # The original object itself is untouched -- Step 32: never overwritten in place.
    assert original.content == "Project Alpha uses PostgreSQL."


def test_memory_cannot_supersede_itself():
    memory = make_memory()
    # model_copy(update=...) skips validation by design in Pydantic v2, so
    # exercise the rule the way real code would trigger it: constructing a
    # new, validated object with the offending field set.
    with pytest.raises(ValidationError):
        MemoryObject(**{**memory.model_dump(), "supersedes": memory.id})


def test_mark_superseded_links_both_sides():
    old = make_memory(content="Project Alpha uses AWS.")
    new = make_memory(content="Project Alpha uses GCP.")

    updated_old, updated_new = mark_superseded(old, new)

    assert updated_old.id == old.id
    assert updated_old.superseded_by == new.id
    assert updated_old.lifecycle_state == LifecycleState.SUPERSEDED
    assert updated_old.truth_status == TruthStatus.SUPERSEDED
    assert updated_old.version == old.version + 1

    assert updated_new.supersedes == old.id
    assert updated_new.id == new.id
