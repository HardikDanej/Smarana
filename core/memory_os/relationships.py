"""
Memory relationships and lineage (Plan Steps 51-52, 54-55).

Step 51's coexistence matrix says a single event can produce many memory
types (episodic, semantic, temporal, decision, reflective, procedural,
relational...) that are not competing, just different representations of
the same experience. Step 52 gives them an evidence graph connecting them:
derived_from, supports, contradicts, supersedes, and the rest. Step 54
asks the graph one specific question well -- "why does the system
believe this?" -- a traceable chain back to original evidence (lineage).
Step 55 distinguishes that general relationship graph from
*dependencies*: the narrower derived_from subset that drives belief
maintenance -- if everything a memory depended on stops being valid, the
memory's own confidence should reflect that, not stay frozen.

Storage-agnostic on purpose, same as retrieval.py: a RelationshipGraph is
a plain in-memory index over edges, not a database. Persisting it is a
StorageAdapter's job -- Step 89 (Phase 17) is that later phase:
PostgresAdapter.sync_relationship_graph()/load_relationship_graph() read
and write exactly the edges `edges()` exposes here, underneath this same
in-memory class, which does not change to know about storage at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import LifecycleState, MemoryObject, TruthStatus


class RelationshipType(str, Enum):
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    CAUSED_BY = "caused_by"
    RESULTED_IN = "resulted_in"
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    EXAMPLE_OF = "example_of"
    INSTANCE_OF = "instance_of"
    LEARNED_FROM = "learned_from"
    VALIDATED_BY = "validated_by"
    INVALIDATED_BY = "invalidated_by"


@dataclass(frozen=True)
class MemoryRelationship:
    source_id: str
    relationship_type: RelationshipType
    target_id: str
    metadata: dict = field(default_factory=dict)


class RelationshipGraph:
    """A directed multigraph of MemoryRelationship edges. Step 51's
    coexistence matrix is exactly what lets many edges point at or from
    the same memory; this class places no limit on that (Rules A-C:
    multiple memories can describe the same event, and a semantic
    memory or procedure may derive from more than one episode)."""

    def __init__(self):
        self._edges: list[MemoryRelationship] = []

    def add(
        self,
        source_id: str,
        relationship_type: RelationshipType,
        target_id: str,
        **metadata,
    ) -> MemoryRelationship:
        edge = MemoryRelationship(source_id, relationship_type, target_id, metadata)
        self._edges.append(edge)
        return edge

    def outgoing(
        self, memory_id: str, relationship_type: "RelationshipType | None" = None
    ) -> list[MemoryRelationship]:
        return [
            e
            for e in self._edges
            if e.source_id == memory_id
            and (relationship_type is None or e.relationship_type == relationship_type)
        ]

    def incoming(
        self, memory_id: str, relationship_type: "RelationshipType | None" = None
    ) -> list[MemoryRelationship]:
        return [
            e
            for e in self._edges
            if e.target_id == memory_id
            and (relationship_type is None or e.relationship_type == relationship_type)
        ]

    def lineage(self, memory_id: str) -> list[MemoryRelationship]:
        """Step 54: the full DERIVED_FROM chain back from memory_id to
        original evidence, breadth-first, cycle-safe."""
        chain: list[MemoryRelationship] = []
        visited: set[str] = {memory_id}
        frontier = [memory_id]
        while frontier:
            current = frontier.pop(0)
            for edge in self.outgoing(current, RelationshipType.DERIVED_FROM):
                chain.append(edge)
                if edge.target_id not in visited:
                    visited.add(edge.target_id)
                    frontier.append(edge.target_id)
        return chain

    def dependencies(self, memory_id: str) -> list[str]:
        """Step 55: the narrower subset used for belief maintenance --
        direct DERIVED_FROM targets only, not the full recursive lineage."""
        return [e.target_id for e in self.outgoing(memory_id, RelationshipType.DERIVED_FROM)]

    def edges(self) -> list[MemoryRelationship]:
        """Every edge currently held, in insertion order. Step 89: this
        is what a StorageAdapter reads to persist the graph -- the whole
        point of a public accessor instead of a caller reaching into
        `_edges` directly."""
        return list(self._edges)


# Step 55/92: the shared definition of "no longer live," used both to
# dampen a memory that depends entirely on stale evidence (below) and to
# compute Step 92's staleness_rate metric (metrics.py) -- one definition,
# not two that could drift apart.
STALE_LIFECYCLE_STATES = {LifecycleState.SUPERSEDED, LifecycleState.FORGOTTEN, LifecycleState.ARCHIVED}


def recompute_confidence_from_dependencies(
    memory: MemoryObject, dependency_memories: list[MemoryObject]
) -> MemoryObject:
    """Step 55's belief-maintenance primitive: if every memory this one
    depends on is no longer live (superseded/forgotten/archived), this
    memory's own confidence drops and its truth_status moves toward
    uncertain. Deliberately conservative -- a dampening, not a verdict.
    Full contradiction resolution (weighing partial evidence loss,
    timestamps, source quality) is Step 58, a later phase, not this one."""
    if not dependency_memories:
        return memory

    stale_states = STALE_LIFECYCLE_STATES
    all_evidence_stale = all(dep.lifecycle_state in stale_states for dep in dependency_memories)

    if all_evidence_stale and memory.truth_status != TruthStatus.UNCERTAIN:
        return memory.new_version(
            confidence=min(memory.confidence, 0.3),
            truth_status=TruthStatus.UNCERTAIN,
        )
    return memory


# Rule E ("a skill cannot automatically become trusted merely because an
# LLM generated it") is now enforced structurally in learning.py:
# build_skill() raises unless the source procedure's lifecycle_state is
# already VALIDATED (Step 73). See test_learning.py::test_rule_e_*.
