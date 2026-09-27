"""
Learning from experience (Plan Steps 71-74): Episode -> Pattern ->
Reflection -> Candidate Procedure -> Validated Procedure -> Skill.

Every step up this ladder carries evidence_count/confidence/exceptions,
never promoted by narrative plausibility alone (Step 71). A candidate
procedure stays a candidate until Step 73's validator actually runs it
enough times (Step 73: "prevents the system from learning a bad
procedure from one lucky success"). A Skill can only be built from an
already-VALIDATED procedure (Step 74) -- this is Rule E from Step 53
("a skill cannot automatically become trusted merely because an LLM
generated it") enforced structurally, the same way Step 48's reflection
rule is: by what the code refuses to accept, not by a comment asking
nicely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import (
    LifecycleState,
    MemoryObject,
    MemoryScope,
    SemanticType,
    SourceType,
    TruthStatus,
)


@dataclass(frozen=True)
class Pattern:
    """Step 71: a condition that correlates with an outcome across
    episodes -- evidence_count/confidence/exceptions attached, never
    stored as absolute truth."""

    condition: str
    predicts: str  # "success" or "failure"
    evidence_count: int
    confidence: float
    exceptions: int
    scope: MemoryScope
    episode_ids: list[str]


def _success_rate(episodes: list[MemoryObject], outcome_key: str) -> "float | None":
    if not episodes:
        return None
    successes = sum(1 for ep in episodes if ep.metadata.get(outcome_key) == "success")
    return successes / len(episodes)


class PatternDetector:
    """Step 71's own example: episodes where a condition (e.g. "X was
    changed") held true succeeded far more often than episodes where it
    didn't -- "Pattern: X strongly predicts successful execution.\""""

    def detect(
        self,
        episodes: list[MemoryObject],
        condition_key: str,
        scope: MemoryScope,
        outcome_key: str = "outcome",
    ) -> "Pattern | None":
        relevant = [ep for ep in episodes if condition_key in ep.metadata and outcome_key in ep.metadata]
        if not relevant:
            return None

        met = [ep for ep in relevant if ep.metadata[condition_key]]
        not_met = [ep for ep in relevant if not ep.metadata[condition_key]]

        met_rate = _success_rate(met, outcome_key)
        not_met_rate = _success_rate(not_met, outcome_key)
        if met_rate is None or not_met_rate is None:
            return None  # need both groups represented to compare at all

        predicts = "success" if met_rate >= not_met_rate else "failure"
        confidence = abs(met_rate - not_met_rate)

        predicting_group = met if predicts == "success" else not_met
        exceptions = sum(1 for ep in predicting_group if ep.metadata[outcome_key] != predicts)

        return Pattern(
            condition=condition_key,
            predicts=predicts,
            evidence_count=len(relevant),
            confidence=confidence,
            exceptions=exceptions,
            scope=scope,
            episode_ids=[ep.id for ep in relevant],
        )


def promote_reflection_to_candidate_procedure(
    reflection: MemoryObject,
    steps: list[str],
    scope: MemoryScope,
    preconditions: "list[str] | None" = None,
) -> MemoryObject:
    """Step 72: a repeated pattern's reflection becomes a candidate
    procedure -- concrete, numbered steps, but still unvalidated. Stays
    CANDIDATE (same rule as Step 48's reflection) until Step 73's
    validator actually runs it."""
    if reflection.semantic_type != SemanticType.REFLECTIVE:
        raise ValueError("promote_reflection_to_candidate_procedure requires a REFLECTIVE memory")

    return MemoryObject(
        content="\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps)),
        semantic_type=SemanticType.PROCEDURAL,
        scope=scope,
        confidence=reflection.confidence,
        truth_status=TruthStatus.UNCERTAIN,
        source_type=SourceType.REFLECTION,
        evidence=[reflection.id],
        lifecycle_state=LifecycleState.CANDIDATE,
        metadata={
            "derived_from_reflection": reflection.id,
            "preconditions": preconditions or [],
        },
    )


@dataclass
class ValidationRecord:
    """Step 73: attempts/successes tracked across real runs -- not a
    single trial."""

    attempts: int = 0
    successes: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0


class ProcedureValidator:
    """Step 73: "Eventually: Success: 97/100. Confidence: high." Won't
    promote past `min_attempts` trials, whatever the rate looks like so
    far -- "prevents the system from learning a bad procedure from one
    lucky success.\""""

    def __init__(self, min_attempts: int = 5, min_success_rate: float = 0.8):
        self.min_attempts = min_attempts
        self.min_success_rate = min_success_rate

    def validate(
        self,
        procedure: MemoryObject,
        record: ValidationRecord,
        applicable_conditions: "dict | None" = None,
    ) -> MemoryObject:
        metadata = {
            **procedure.metadata,
            "validation_attempts": record.attempts,
            "validation_successes": record.successes,
        }
        if applicable_conditions is not None:
            metadata["applicable_conditions"] = applicable_conditions

        if record.attempts < self.min_attempts:
            # Not enough evidence yet, whatever the rate looks like so far.
            return procedure.new_version(metadata=metadata)

        if record.success_rate >= self.min_success_rate:
            return procedure.new_version(
                lifecycle_state=LifecycleState.VALIDATED,
                truth_status=TruthStatus.CONFIRMED,
                confidence=record.success_rate,
                metadata=metadata,
            )

        return procedure.new_version(
            lifecycle_state=LifecycleState.CANDIDATE,
            truth_status=TruthStatus.CONTRADICTED,
            confidence=record.success_rate,
            metadata=metadata,
        )


@dataclass(frozen=True)
class Skill:
    """Step 74: a structured, validated capability representation.
    "Skill != Prompt. Skill != Memory snippet. Skill != LLM response."
    """

    name: str
    preconditions: list[str]
    procedure_id: str
    tools: list[str]
    known_failures: list[str]
    success_rate: float
    last_validated: datetime
    confidence: float

    def as_memory(self, scope: MemoryScope) -> MemoryObject:
        return MemoryObject(
            content=self.name,
            semantic_type=SemanticType.SKILL,
            scope=scope,
            confidence=self.confidence,
            truth_status=TruthStatus.CONFIRMED,
            source_type=SourceType.REFLECTION,
            evidence=[self.procedure_id],
            lifecycle_state=LifecycleState.VALIDATED,
            metadata={
                "preconditions": self.preconditions,
                "tools": self.tools,
                "known_failures": self.known_failures,
                "success_rate": self.success_rate,
                "last_validated": self.last_validated.isoformat(),
            },
        )


def build_skill(
    procedure: MemoryObject, tools: list[str], known_failures: "list[str] | None" = None
) -> Skill:
    """A Skill can only be built from a procedure that has actually
    passed Step 73's validation -- Rule E (Step 53) generalized: a skill
    doesn't get to be trusted just because something produced fluent
    steps for it."""
    if procedure.lifecycle_state != LifecycleState.VALIDATED:
        raise ValueError("a Skill can only be built from a VALIDATED procedure")

    attempts = procedure.metadata.get("validation_attempts")
    successes = procedure.metadata.get("validation_successes")
    success_rate = successes / attempts if attempts else procedure.confidence

    first_line = procedure.content.splitlines()[0] if procedure.content else "unnamed skill"

    return Skill(
        name=first_line,
        preconditions=list(procedure.metadata.get("preconditions", [])),
        procedure_id=procedure.id,
        tools=list(tools),
        known_failures=list(known_failures or []),
        success_rate=success_rate,
        last_validated=procedure.updated_at,
        confidence=procedure.confidence,
    )
