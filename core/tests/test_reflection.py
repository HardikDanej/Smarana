import pytest

from memory_os import LifecycleState, MemoryScope, SemanticType, SourceType, TruthStatus
from memory_os.models import MemoryObject
from memory_os.reflection import build_reflection

from .fakes import FakeLLMProvider


def _episode(content: str) -> MemoryObject:
    return MemoryObject(
        content=content,
        semantic_type=SemanticType.FAILURE,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.AGENT_OBSERVATION,
    )


def test_reflection_is_reflective_type_derived_from_episode_content():
    episodes = [_episode("Deployment failed: missing env variable X.")]
    provider = FakeLLMProvider()

    reflection = build_reflection(episodes, provider, scope=MemoryScope.PROJECT)

    assert reflection.semantic_type == SemanticType.REFLECTIVE
    assert reflection.source_type.value == "reflection"


def test_reflection_never_starts_as_confirmed_fact():
    # Step 48's core rule: "LLM said something clever -> permanent truth"
    # must never happen. Enforced on the object itself, not by convention.
    episodes = [_episode("Deployment failed.")]
    reflection = build_reflection(episodes, FakeLLMProvider(), scope=MemoryScope.PROJECT)

    assert reflection.truth_status == TruthStatus.UNCERTAIN
    assert reflection.lifecycle_state == LifecycleState.CANDIDATE


def test_reflection_preserves_evidence_back_to_source_episodes():
    episodes = [_episode("Failure A"), _episode("Failure B"), _episode("Failure C")]

    reflection = build_reflection(episodes, FakeLLMProvider(), scope=MemoryScope.PROJECT)

    assert reflection.evidence == [e.id for e in episodes]
    assert reflection.metadata["source_episode_count"] == 3


def test_confidence_increases_with_more_corroborating_episodes_but_stays_capped():
    one_episode = build_reflection([_episode("A")], FakeLLMProvider(), scope=MemoryScope.PROJECT)
    many_episodes = build_reflection(
        [_episode(f"E{i}") for i in range(10)], FakeLLMProvider(), scope=MemoryScope.PROJECT
    )

    assert many_episodes.confidence > one_episode.confidence
    assert many_episodes.confidence <= 0.85


def test_reflection_requires_at_least_one_episode():
    with pytest.raises(ValueError):
        build_reflection([], FakeLLMProvider(), scope=MemoryScope.PROJECT)


def test_reflection_calls_provider_reflect_with_episode_contents():
    episodes = [_episode("Failure A"), _episode("Failure B")]
    provider = FakeLLMProvider()

    build_reflection(episodes, provider, scope=MemoryScope.PROJECT)

    call_name, args, _ = provider.calls[0]
    assert call_name == "reflect"
    assert args[0] == ("Failure A", "Failure B")
