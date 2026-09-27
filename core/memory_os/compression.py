"""
Memory compression (Plan Step 47): reduces a large set of memories down
to fewer, higher-value ones. "43 memories -> 11 useful facts/events -> 3
compact summaries." Contradictions are never silently dropped here --
representing a contradiction is Step 35's supersession model's job, not
compression's; this module only removes true redundancy and noise.
"""

from __future__ import annotations

from .models import LifecycleState, MemoryObject, SemanticType
from .providers import LLMProvider


def deduplicate(memories: list[MemoryObject]) -> list[MemoryObject]:
    """Exact-content dedup, case/whitespace-insensitive. First occurrence wins."""
    seen: dict[str, MemoryObject] = {}
    for memory in memories:
        key = memory.content.strip().lower()
        if key not in seen:
            seen[key] = memory
    return list(seen.values())


def drop_stale_or_low_confidence(
    memories: list[MemoryObject], min_confidence: float = 0.3
) -> list[MemoryObject]:
    return [
        m
        for m in memories
        if m.confidence >= min_confidence and m.lifecycle_state != LifecycleState.FORGOTTEN
    ]


class MemoryCompressor:
    """Dedup + stale/low-confidence removal always run. Grouped
    summarization only runs when an LLMProvider is supplied -- without
    one, this returns the deduped, filtered contents themselves rather
    than pretending to summarize (an honest fallback, not a fake one)."""

    def __init__(self, provider: LLMProvider | None = None, min_confidence: float = 0.3):
        self.provider = provider
        self.min_confidence = min_confidence

    def compress(self, memories: list[MemoryObject]) -> list[str]:
        working = deduplicate(memories)
        working = drop_stale_or_low_confidence(working, self.min_confidence)

        groups: dict[SemanticType, list[MemoryObject]] = {}
        for memory in working:
            groups.setdefault(memory.semantic_type, []).append(memory)

        summaries: list[str] = []
        for group in groups.values():
            if self.provider is not None and len(group) > 1:
                summaries.append(self.provider.summarize(" ".join(m.content for m in group)))
            else:
                summaries.extend(m.content for m in group)
        return summaries
