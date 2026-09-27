"""
Tests the Claude adapter against a mocked Anthropic client -- never a live
API call. No ANTHROPIC_API_KEY, no network egress, no cost, and a
deterministic result, which a real model call cannot promise anyway.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from adapters.claude_provider import ClaudeProvider


def _fake_message(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _provider_with_response(text: str) -> tuple[ClaudeProvider, MagicMock]:
    client = MagicMock()
    client.messages.create.return_value = _fake_message(text)
    return ClaudeProvider(client=client), client


def test_generate_returns_the_text_block_and_passes_no_default_key():
    provider, client = _provider_with_response("hello")

    result = provider.generate("say hello")

    assert result == "hello"
    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == provider.model
    assert kwargs["messages"] == [{"role": "user", "content": "say hello"}]


def test_classify_accepts_an_exact_category():
    provider, _ = _provider_with_response("episodic")
    result = provider.classify("what happened", categories=["episodic", "semantic"])
    assert result == "episodic"


def test_classify_is_case_insensitive_but_constrained_to_offered_categories():
    provider, _ = _provider_with_response("Episodic")
    result = provider.classify("what happened", categories=["episodic", "semantic"])
    assert result == "episodic"


def test_classify_rejects_a_category_that_was_never_offered():
    provider, _ = _provider_with_response("procedural")
    with pytest.raises(ValueError):
        provider.classify("what happened", categories=["episodic", "semantic"])


def test_extract_parses_json_response():
    payload = {"entity": "Company", "relation": "uses", "value": "GCP"}
    provider, _ = _provider_with_response(json.dumps(payload))

    result = provider.extract("some text", schema={"entity": "...", "relation": "...", "value": "..."})

    assert result == payload


def test_extract_strips_a_markdown_code_fence():
    payload = {"entity": "Company"}
    fenced = f"```json\n{json.dumps(payload)}\n```"
    provider, _ = _provider_with_response(fenced)

    result = provider.extract("some text", schema={"entity": "..."})

    assert result == {"entity": "Company"}


def test_extract_raises_on_unparseable_output_rather_than_fabricating_data():
    provider, _ = _provider_with_response("not json at all")
    with pytest.raises(ValueError):
        provider.extract("some text", schema={"entity": "..."})


def test_extract_fills_missing_schema_keys_with_empty_string():
    provider, _ = _provider_with_response(json.dumps({"entity": "Company"}))
    result = provider.extract("some text", schema={"entity": "...", "relation": "..."})
    assert result == {"entity": "Company", "relation": ""}
