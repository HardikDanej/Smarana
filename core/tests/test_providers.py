from memory_os.providers import LLMProvider

from .fakes import FakeLLMProvider


def test_fake_provider_satisfies_the_protocol_structurally():
    # No inheritance from LLMProvider anywhere in FakeLLMProvider -- this
    # proves the interface is structural, per Step 37: any object with the
    # right methods qualifies, regardless of what it's vendored from.
    provider = FakeLLMProvider()
    assert isinstance(provider, LLMProvider)


def test_missing_a_method_fails_the_protocol_check():
    class Incomplete:
        def generate(self, prompt: str, **kwargs):
            return ""

    assert not isinstance(Incomplete(), LLMProvider)
