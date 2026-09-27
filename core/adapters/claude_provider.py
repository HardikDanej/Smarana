"""
Claude adapter (Plan Step 38): the first concrete LLMProvider.

"Claude must be an adapter, not the architecture." This is the ONLY file
in this codebase allowed to import `anthropic` -- core/memory_os never
does, enforced by the no-LLM-dependency gate on that package. Nothing in
core/memory_os imports this module either; callers wire it in from the
outside (e.g. `ExtractionPipeline(provider=ClaudeProvider())`), which is
what makes swapping in OpenAIProvider/GeminiProvider/CustomProvider later
a matter of passing a different object, not editing the engine.
"""

from __future__ import annotations

import json
import re
from typing import Mapping, Sequence

import anthropic

_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$")

DEFAULT_MODEL = "claude-sonnet-5"


def _text_from_message(message: anthropic.types.Message) -> str:
    return "".join(block.text for block in message.content if getattr(block, "type", None) == "text")


def _strip_code_fence(text: str) -> str:
    return _CODE_FENCE.sub("", text.strip()).strip()


class ClaudeProvider:
    """Implements the LLMProvider protocol on top of the Anthropic Messages API."""

    def __init__(self, model: str = DEFAULT_MODEL, client: "anthropic.Anthropic | None" = None):
        self.model = model
        self._client = client or anthropic.Anthropic()

    def generate(self, prompt: str, **kwargs: object) -> str:
        max_tokens = kwargs.pop("max_tokens", 1024)
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return _text_from_message(message)

    def classify(self, text: str, categories: Sequence[str]) -> str:
        options = list(categories)
        system = "Reply with exactly one of the given categories and nothing else."
        prompt = (
            f"Categories: {', '.join(options)}\n\n"
            f"Text: {text}\n\n"
            "Which category best fits? Reply with only the category name."
        )
        result = self.generate(prompt, system=system, max_tokens=32).strip()
        if result in options:
            return result
        case_insensitive = {opt.lower(): opt for opt in options}
        if result.lower() in case_insensitive:
            return case_insensitive[result.lower()]
        raise ValueError(f"classify: model returned {result!r}, not one of {options}")

    def extract(self, text: str, schema: Mapping[str, str]) -> dict:
        fields = "\n".join(f"- {name}: {description}" for name, description in schema.items())
        system = (
            "Extract the requested fields from the text. Reply with ONLY a single "
            "JSON object whose keys are exactly the given field names. Use an "
            "empty string for any field not present in the text. No prose, no "
            "markdown fences."
        )
        prompt = f"Fields to extract:\n{fields}\n\nText: {text}"
        raw = _strip_code_fence(self.generate(prompt, system=system, max_tokens=512))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"extract: model did not return valid JSON: {raw!r}") from exc
        return {key: data.get(key, "") for key in schema}

    def summarize(self, text: str, max_tokens: int | None = None) -> str:
        system = "Summarize the text. Reply with only the summary, no preamble."
        return self.generate(f"Text: {text}", system=system, max_tokens=max_tokens or 256).strip()

    def reflect(self, episodes: Sequence[str]) -> str:
        system = (
            "You will be given a numbered list of episodes. State, in one or two "
            "sentences, the single pattern they share, if any. If they share no "
            "clear pattern, say so plainly instead of inventing one."
        )
        numbered = "\n".join(f"{i + 1}. {episode}" for i, episode in enumerate(episodes))
        return self.generate(numbered, system=system, max_tokens=256).strip()

    def reason(self, question: str, context: Sequence[str]) -> str:
        system = (
            "Answer the question using ONLY the supplied context. If the context "
            "does not contain the answer, say that plainly instead of guessing."
        )
        numbered_context = "\n".join(f"- {item}" for item in context)
        prompt = f"Context:\n{numbered_context}\n\nQuestion: {question}"
        return self.generate(prompt, system=system, max_tokens=512).strip()
