"""
Conflict resolution, uncertainty, and correction (Plan Steps 58-60).

Step 58's example is the easy case: "Memory A: Project uses AWS. Memory
B: Project uses GCP." Once you know B was learned after A, this isn't a
contradiction to adjudicate -- it's a state transition. "No contradiction
remains. It's a state transition." ConflictResolver handles exactly that
case: it closes A's validity window where B's begins and links them via
the existing supersession machinery (Step 35).

Step 59 is the case ConflictResolver deliberately does NOT try to solve:
two candidates, neither reliable enough to call. "Do not force a winner
... The system must be able to represent 'I don't know.'"
resolve_uncertain() returns a normalized probability distribution instead
of a verdict.

Step 60 turns "That's wrong" into a correction chain -- Old -> Correction
-> New -- reusing mark_superseded so the old memory becomes SUPERSEDED,
never silently deleted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import MemoryObject, SourceType, mark_superseded


class ConflictResolver:
    """Step 58: resolves two memories about the same subject into a
    state transition when their knowledge_time ordering makes that the
    obvious reading. This is NOT the tool for two same-time, equally
    unreliable claims -- that's resolve_uncertain(), below."""

    def resolve(self, earlier: MemoryObject, later: MemoryObject) -> tuple[MemoryObject, MemoryObject]:
        if later.knowledge_time <= earlier.knowledge_time:
            raise ValueError(
                "resolve(earlier, later) requires later.knowledge_time > earlier.knowledge_time; "
                "for two claims with no clear time ordering, use resolve_uncertain() instead"
            )

        transition_point = later.event_time or later.knowledge_time
        closed_earlier = earlier.new_version(valid_until=earlier.valid_until or transition_point)
        return mark_superseded(closed_earlier, later)


@dataclass(frozen=True)
class UncertainBelief:
    """Step 59: "I don't know" as a first-class, structured result --
    never a forced pick between candidates the evidence doesn't decide."""

    candidates: list[tuple[MemoryObject, float]]  # (memory, normalized probability)

    @property
    def status(self) -> str:
        return "uncertain"


def resolve_uncertain(candidates: list[MemoryObject]) -> UncertainBelief:
    """Step 59's own example: Source A says PostgreSQL, Source B says
    MySQL, neither reliable enough to call. Confidence values are
    normalized into a probability distribution over candidates rather
    than the system picking a winner it isn't actually sure of."""
    if not candidates:
        raise ValueError("resolve_uncertain requires at least one candidate")

    total = sum(c.confidence for c in candidates)
    if total <= 0:
        # Every candidate reported zero confidence: nothing to weight by,
        # so treat them as equally (un)likely rather than dividing by zero.
        share = 1.0 / len(candidates)
        return UncertainBelief(candidates=[(c, share) for c in candidates])

    return UncertainBelief(candidates=[(c, c.confidence / total) for c in candidates])


def apply_correction(
    old: MemoryObject,
    corrected_content: str,
    source_type: SourceType = SourceType.USER_STATEMENT,
    source_id: "str | None" = None,
) -> tuple[MemoryObject, MemoryObject]:
    """Step 60: "That's wrong" becomes Old -> Correction -> New, not a
    silent overwrite and not a delete. The old memory is preserved as
    SUPERSEDED (Step 35) via the same mark_superseded every other
    supersession in this codebase already goes through."""
    correction = MemoryObject(
        content=corrected_content,
        semantic_type=old.semantic_type,
        scope=old.scope,
        source_type=source_type,
        source_id=source_id,
        metadata={"is_correction": True, "corrects": old.id},
    )
    return mark_superseded(old, correction)
