"""
Retrieval planning (Plan Steps 61-63, 65).

Step 61 replaces the flat "Question -> Memory Type" routing with a real
plan: Question -> Intent -> Entities -> Retrieval plan. Step 62
decomposes a compound request into independently-answerable
sub-questions. Step 63 expands from an entity through the relationship
graph with hard depth/size limits -- "otherwise our memory has become an
archaeological site." Step 65 is a rule-based strategy table mapping
intent to which retrievers should run; the plan is explicit that actual
*learning* which strategy works ("the system can learn these patterns
from evaluation results") is a later, "eventually" capability -- this
module builds the rule-based starting point that later learning would
refine, the same relationship Step 36's rule classifier has to a future
ML/LLM classifier. Nothing here claims to learn anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from .classifier import RuleBasedClassifier
from .models import SemanticType
from .relationships import MemoryRelationship, RelationshipGraph

# Step 65: which retrievers participate for a given classified intent.
# Not learned -- a fixed table, the deliberate starting point for later
# adaptation, not adaptation itself.
_STRATEGY_BY_INTENT: dict[SemanticType, frozenset[str]] = {
    SemanticType.DECISION: frozenset({"keyword", "vector", "relationship"}),
    SemanticType.REFLECTIVE: frozenset({"keyword", "vector", "relationship"}),
    SemanticType.FAILURE: frozenset({"keyword", "vector"}),
    SemanticType.EPISODIC: frozenset({"keyword", "vector"}),
    SemanticType.PROCEDURAL: frozenset({"keyword", "vector"}),
}
_DEFAULT_STRATEGY = frozenset({"keyword", "vector"})


def select_strategy(intent: SemanticType) -> frozenset[str]:
    """Step 65: the retrievers this intent should run against."""
    return _STRATEGY_BY_INTENT.get(intent, _DEFAULT_STRATEGY)


@dataclass
class RetrievalPlan:
    query: str
    intent: SemanticType
    entities: list[str]
    strategy: frozenset[str]
    steps: list[str]
    as_of: datetime | None = None


class RetrievalPlanner:
    """Step 61: turns a raw question into a plan, not just a memory-type
    label. `known_entities` is the set of entity names the planner can
    recognize in a query -- realistically, whatever's already in storage;
    this deliberately does not attempt real NER."""

    def __init__(
        self,
        classifier: RuleBasedClassifier | None = None,
        known_entities: list[str] | None = None,
    ):
        self.classifier = classifier or RuleBasedClassifier()
        self.known_entities = known_entities or []

    def plan(self, query: str, as_of: datetime | None = None) -> RetrievalPlan:
        intent = self.classifier.classify(query).semantic_type
        entities = self._find_entities(query)
        strategy = select_strategy(intent)
        steps = self._build_steps(entities, intent, as_of)
        return RetrievalPlan(
            query=query, intent=intent, entities=entities, strategy=strategy, steps=steps, as_of=as_of
        )

    def _find_entities(self, query: str) -> list[str]:
        lowered = query.lower()
        return [name for name in self.known_entities if name.lower() in lowered]

    def _build_steps(
        self, entities: list[str], intent: SemanticType, as_of: datetime | None
    ) -> list[str]:
        steps = [f"Find {entity}." for entity in entities] or ["Identify the subject of the question."]
        steps.append("Retrieve relevant memories by keyword and vector similarity.")
        if intent == SemanticType.DECISION:
            steps.append("Find decision memory.")
            steps.append("Retrieve supporting evidence.")
        elif intent == SemanticType.PROCEDURAL:
            steps.append("Retrieve the relevant procedure.")
        elif intent == SemanticType.REFLECTIVE:
            steps.append("Retrieve reflections derived from relevant episodes.")
        if entities:
            steps.append("Expand through related entities.")
        if as_of is not None:
            steps.append(f"Check temporal validity as of {as_of.isoformat()}.")
        else:
            steps.append("Check temporal validity.")
        steps.append("Assemble answer.")
        return steps


@dataclass
class SubQuestion:
    text: str
    intent: SemanticType


# Splits on ", and ", a bare comma, or a standalone " and " -- in that
# priority order, so "A, B, and C" splits into three parts rather than
# leaving a dangling "and C".
_SPLIT_PATTERN = re.compile(r",\s*and\s+|,\s*|\s+and\s+", re.IGNORECASE)


class QueryDecomposer:
    """Step 62: splits a compound request into sub-questions that can be
    answered independently and then recombined. Not perfect -- a fixed
    set of conjunction patterns, same honesty as the rule-based
    classifier it depends on."""

    def __init__(self, classifier: RuleBasedClassifier | None = None):
        self.classifier = classifier or RuleBasedClassifier()

    def decompose(self, request: str) -> list[SubQuestion]:
        text = request.strip()
        if text.endswith((".", "?", "!")):
            text = text[:-1]
        parts = [p.strip() for p in _SPLIT_PATTERN.split(text) if p.strip()]
        if len(parts) <= 1:
            parts = [text]
        return [SubQuestion(text=p, intent=self.classifier.classify(p).semantic_type) for p in parts]


class GraphExpander:
    """Step 63: controlled expansion from an entity/memory through the
    relationship graph. Hard depth and size limits on purpose -- the
    plan's own warning is "one entity -> 10 million nodes," and this
    exists specifically to make that impossible."""

    def __init__(self, graph: RelationshipGraph, max_depth: int = 2, max_edges: int = 20):
        self.graph = graph
        self.max_depth = max_depth
        self.max_edges = max_edges

    def expand(self, memory_id: str) -> list[MemoryRelationship]:
        visited = {memory_id}
        frontier = [(memory_id, 0)]
        collected: list[MemoryRelationship] = []

        while frontier and len(collected) < self.max_edges:
            current, depth = frontier.pop(0)
            if depth >= self.max_depth:
                continue
            neighbors = self.graph.outgoing(current) + self.graph.incoming(current)
            for edge in neighbors:
                if len(collected) >= self.max_edges:
                    break
                collected.append(edge)
                neighbor_id = edge.target_id if edge.source_id == current else edge.source_id
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    frontier.append((neighbor_id, depth + 1))

        return collected
