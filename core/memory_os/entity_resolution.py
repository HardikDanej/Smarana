"""
Entity resolution (Plan Step 40).

Deterministic only: case/punctuation/corporate-suffix normalization plus
fuzzy matching (stdlib difflib) against entities already seen. This
catches near-identical variants -- "OpenAI" / "open ai" / "OpenAI Inc."
-- on its own.

It does NOT resolve abbreviation-style variants such as "Project Alpha"
vs. "Alpha" -- those aren't textually close enough for a similarity
threshold to catch without also catching unrelated entities, and the
plan itself only claims these "may be the same project," not that they
provably are. Use `register_alias` for cases like that where the mapping
is known out-of-band; don't lower the threshold to force it.
"""

from __future__ import annotations

import difflib
import re

_CORPORATE_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|company)\b\.?")
_PUNCTUATION = re.compile(r"[.,]")
_WHITESPACE = re.compile(r"\s+")


class EntityResolver:
    """Maps entity name variants to a single canonical name."""

    def __init__(self, similarity_threshold: float = 0.86):
        self.similarity_threshold = similarity_threshold
        self._known: dict[str, str] = {}  # normalized form -> canonical name
        self._aliases: dict[str, str] = {}  # explicit normalized alias -> canonical name

    @staticmethod
    def normalize(name: str) -> str:
        text = name.lower().strip()
        text = _PUNCTUATION.sub("", text)
        text = _CORPORATE_SUFFIX.sub("", text)
        text = _WHITESPACE.sub(" ", text).strip()
        return text

    def register_alias(self, alias: str, canonical: str) -> None:
        """Force `alias` to resolve to `canonical`, for known variants that
        normalization and fuzzy matching can't be trusted to catch on their own."""
        self._aliases[self.normalize(alias)] = canonical

    def resolve(self, name: str) -> str:
        """Returns the canonical name for `name`. The first surface form seen
        for a given entity becomes its canonical name."""
        normalized = self.normalize(name)

        if normalized in self._aliases:
            return self._aliases[normalized]
        if normalized in self._known:
            return self._known[normalized]

        best_canonical: str | None = None
        best_score = 0.0
        for known_normalized, canonical in self._known.items():
            score = difflib.SequenceMatcher(None, normalized, known_normalized).ratio()
            if score > best_score:
                best_score = score
                best_canonical = canonical

        if best_canonical is not None and best_score >= self.similarity_threshold:
            self._known[normalized] = best_canonical
            return best_canonical

        self._known[normalized] = name
        return name
