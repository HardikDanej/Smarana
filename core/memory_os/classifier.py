"""
Deterministic memory classifier (Plan Step 36).

Rule-based, not machine-learned and not an LLM call: the point of this
module is to establish the classification *interface* before any
intelligence is attached, per Step 36 -- "This doesn't need to be
perfect. The purpose is to establish the interface." A rule classifier,
an ML classifier, and an LLM classifier are meant to coexist later behind
the same call shape; this is the first of the three.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import SemanticType

# Ordered rules: first matching pattern wins. Order encodes priority --
# e.g. "why" (a decision question) is checked before the more generic
# failure/episodic patterns so "Why did this fail yesterday?" resolves to
# DECISION, the more specific intent.
_RULES: list[tuple[re.Pattern[str], SemanticType]] = [
    (re.compile(r"\bwhy\b", re.IGNORECASE), SemanticType.DECISION),
    (re.compile(r"\bhow\b", re.IGNORECASE), SemanticType.PROCEDURAL),
    (re.compile(r"\b(error|fail|failure|failed|bug|crash|broke)\b", re.IGNORECASE), SemanticType.FAILURE),
    (re.compile(r"\b(prefer|preference|rather|would like)\b", re.IGNORECASE), SemanticType.PREFERENCE),
    (re.compile(r"\b(goal|plan to|aim to|intend to)\b", re.IGNORECASE), SemanticType.GOAL),
    (re.compile(r"\b(happened|yesterday|earlier|what did|when did)\b", re.IGNORECASE), SemanticType.EPISODIC),
]

_DEFAULT = SemanticType.SEMANTIC


@dataclass(frozen=True)
class Classification:
    semantic_type: SemanticType
    matched_rule: str | None
    """The regex pattern that fired, or None if the default was used --
    kept for provenance: "why does the system believe this is episodic"
    should be answerable, per the plan's general lineage requirement."""


class RuleBasedClassifier:
    """Deterministic, keyword-pattern memory-type classifier."""

    def classify(self, text: str) -> Classification:
        for pattern, semantic_type in _RULES:
            if pattern.search(text):
                return Classification(semantic_type=semantic_type, matched_rule=pattern.pattern)
        return Classification(semantic_type=_DEFAULT, matched_rule=None)
