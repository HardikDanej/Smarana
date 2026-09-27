"""
The LLM intelligence provider interface (Plan Step 37).

"The Memory OS doesn't care whether the implementation is Claude, GPT,
Gemini, a local model, or a custom model." This module defines the shape
every provider must satisfy; it contains no vendor code and imports
nothing beyond the standard library, so it stays inside the deterministic
core alongside models.py and classifier.py. A concrete provider (Step 38:
the Claude adapter) lives under core/adapters/, never here.

Protocol, not ABC: any object with these methods satisfies the interface
structurally, so a test double doesn't need to inherit from anything.
"""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """The provider-agnostic surface the rest of the engine calls."""

    def generate(self, prompt: str, **kwargs: object) -> str:
        """Free-form completion."""
        ...

    def classify(self, text: str, categories: Sequence[str]) -> str:
        """Return exactly one of `categories` that best fits `text`."""
        ...

    def extract(self, text: str, schema: Mapping[str, str]) -> dict:
        """Extract structured data matching `schema` (field name -> description) from `text`."""
        ...

    def summarize(self, text: str, max_tokens: int | None = None) -> str:
        """Compress `text` to its essential content."""
        ...

    def reflect(self, episodes: Sequence[str]) -> str:
        """Produce a reflection: what pattern do these episodes, taken together, suggest?"""
        ...

    def reason(self, question: str, context: Sequence[str]) -> str:
        """Answer `question` using only the supplied `context`."""
        ...
