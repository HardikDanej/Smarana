"""
Reflection (Plan Step 48): the first controlled reflection process.
Input: episodes. Output: a new REFLECTIVE memory whose evidence is
preserved, never presented as settled fact. "We never want: LLM said
something clever -> permanent truth." That rule is enforced structurally
here, not just documented: a reflection is built with lifecycle_state
CANDIDATE and truth_status UNCERTAIN, the same fields Steps 11 and 34
already gave every memory -- there is no separate "is this a reflection"
flag to forget to check.
"""

from __future__ import annotations

from .models import (
    LifecycleState,
    MemoryObject,
    MemoryScope,
    SemanticType,
    SourceType,
    TruthStatus,
)
from .providers import LLMProvider


def build_reflection(
    episodes: list[MemoryObject], provider: LLMProvider, scope: MemoryScope
) -> MemoryObject:
    if not episodes:
        raise ValueError("reflection requires at least one episode as evidence")

    reflection_text = provider.reflect([episode.content for episode in episodes])

    # More corroborating episodes make a pattern more credible, never
    # certain -- capped well short of 1.0.
    confidence = min(0.5 + 0.1 * len(episodes), 0.85)

    return MemoryObject(
        content=reflection_text,
        semantic_type=SemanticType.REFLECTIVE,
        scope=scope,
        confidence=confidence,
        truth_status=TruthStatus.UNCERTAIN,
        source_type=SourceType.REFLECTION,
        evidence=[episode.id for episode in episodes],
        lifecycle_state=LifecycleState.CANDIDATE,
        metadata={"source_episode_count": len(episodes)},
    )
