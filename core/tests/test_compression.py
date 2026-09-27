from memory_os import LifecycleState, MemoryScope, SemanticType, SourceType
from memory_os.compression import MemoryCompressor, deduplicate, drop_stale_or_low_confidence
from memory_os.models import MemoryObject

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


def test_deduplicate_is_case_and_whitespace_insensitive():
    memories = [
        _memory("Project Alpha uses PostgreSQL."),
        _memory("  project alpha uses postgresql.  "),
        _memory("Project Beta uses MongoDB."),
    ]

    result = deduplicate(memories)

    assert len(result) == 2


def test_drop_stale_or_low_confidence_filters_below_threshold():
    kept = _memory("kept", confidence=0.5)
    dropped = _memory("dropped", confidence=0.1)

    result = drop_stale_or_low_confidence([kept, dropped], min_confidence=0.3)

    assert result == [kept]


def test_drop_stale_or_low_confidence_removes_forgotten_memories():
    memory = _memory("forgotten", confidence=0.9, lifecycle_state=LifecycleState.FORGOTTEN)
    assert drop_stale_or_low_confidence([memory]) == []


def test_compressor_without_provider_returns_deduped_filtered_contents_not_a_fake_summary():
    memories = [_memory("Project Alpha uses PostgreSQL.") for _ in range(3)]
    compressor = MemoryCompressor(provider=None)

    result = compressor.compress(memories)

    # No provider -- must not claim to have summarized anything.
    assert result == ["Project Alpha uses PostgreSQL."]


def test_compressor_with_provider_summarizes_groups_larger_than_one():
    memories = [
        _memory("Project Alpha uses PostgreSQL."),
        _memory("Project Alpha's database choice was PostgreSQL."),
    ]
    provider = FakeLLMProvider()
    compressor = MemoryCompressor(provider=provider)

    result = compressor.compress(memories)

    assert len(result) == 1
    assert result[0].startswith("summary of:")
    assert provider.calls[0][0] == "summarize"


def test_compressor_does_not_summarize_a_single_item_group():
    memories = [_memory("A lone fact.")]
    provider = FakeLLMProvider()
    compressor = MemoryCompressor(provider=provider)

    result = compressor.compress(memories)

    assert result == ["A lone fact."]
    assert provider.calls == []


def test_compressor_groups_are_kept_separate_by_semantic_type():
    fact = _memory("Project Alpha uses PostgreSQL.", semantic_type=SemanticType.SEMANTIC)
    decision = _memory("PostgreSQL was chosen deliberately.", semantic_type=SemanticType.DECISION)
    compressor = MemoryCompressor(provider=None)

    result = compressor.compress([fact, decision])

    assert set(result) == {fact.content, decision.content}
