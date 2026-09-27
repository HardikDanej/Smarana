"""
The Context Engine (Plan Step 46): turns ranked retrieval results into a
compact, usable package. "The LLM doesn't receive raw database rows. It
receives usable cognitive context." That distinction -- a formatted,
budgeted package instead of a dump of rows -- is the entire point of
this module; it adds no new intelligence of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import LifecycleState, SemanticType
from .retrieval import ScoredMemory


@dataclass
class MemoryContext:
    current_facts: list[str] = field(default_factory=list)
    historical_facts: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    procedures: list[str] = field(default_factory=list)
    reflections: list[str] = field(default_factory=list)
    average_confidence: float = 0.0

    def render(self) -> str:
        """The plain-text package a caller actually hands to an LLM/agent."""
        sections = [
            ("Current facts", self.current_facts),
            ("Historical facts", self.historical_facts),
            ("Decisions", self.decisions),
            ("Procedures", self.procedures),
            ("Reflections", self.reflections),
        ]
        lines: list[str] = []
        for title, items in sections:
            if items:
                lines.append(f"{title}:")
                lines.extend(f"- {item}" for item in items)
        lines.append(f"Confidence: {self.average_confidence:.2f}")
        return "\n".join(lines)


class ContextEngine:
    """Builds a MemoryContext from ranked retrieval results, respecting a
    token budget (Step 22: "5,000,000 stored memories -> ... -> 7-15
    useful memories") instead of returning everything retrieval found."""

    def __init__(self, max_items: int = 12):
        self.max_items = max_items

    def build(self, results: list[ScoredMemory]) -> MemoryContext:
        context = MemoryContext()
        selected = results[: self.max_items]

        for scored in selected:
            memory = scored.memory
            if memory.semantic_type == SemanticType.DECISION:
                context.decisions.append(memory.content)
            elif memory.semantic_type == SemanticType.PROCEDURAL:
                context.procedures.append(memory.content)
            elif memory.semantic_type == SemanticType.REFLECTIVE:
                context.reflections.append(memory.content)
            elif memory.lifecycle_state == LifecycleState.SUPERSEDED:
                context.historical_facts.append(memory.content)
            else:
                context.current_facts.append(memory.content)

        if selected:
            context.average_confidence = sum(s.memory.confidence for s in selected) / len(selected)

        return context
