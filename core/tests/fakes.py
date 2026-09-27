"""A deterministic LLMProvider test double.

Every intelligence-layer test in this package runs against this fake, not
a live model -- the plumbing (extraction pipeline, provider contract)
must be provable without network access, credentials, or nondeterminism.
The Claude adapter is tested separately with a mocked SDK client, for the
same reason.
"""

from __future__ import annotations

from typing import Mapping, Sequence


class FakeLLMProvider:
    """Satisfies the LLMProvider protocol with scripted, deterministic responses."""

    def __init__(self, extraction_result: dict | None = None):
        self.extraction_result = extraction_result or {}
        self.calls: list[tuple[str, tuple, dict]] = []

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls.append(("generate", (prompt,), kwargs))
        return "generated"

    def classify(self, text: str, categories: Sequence[str]) -> str:
        self.calls.append(("classify", (text, tuple(categories)), {}))
        return categories[0]

    def extract(self, text: str, schema: Mapping[str, str]) -> dict:
        self.calls.append(("extract", (text, tuple(schema)), {}))
        return {key: self.extraction_result.get(key, "") for key in schema}

    def summarize(self, text: str, max_tokens: int | None = None) -> str:
        self.calls.append(("summarize", (text,), {"max_tokens": max_tokens}))
        return f"summary of: {text[:20]}"

    def reflect(self, episodes: Sequence[str]) -> str:
        self.calls.append(("reflect", (tuple(episodes),), {}))
        return f"pattern across {len(episodes)} episodes"

    def reason(self, question: str, context: Sequence[str]) -> str:
        self.calls.append(("reason", (question, tuple(context)), {}))
        return f"answer to: {question}"
