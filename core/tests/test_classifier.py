import pytest

from memory_os import SemanticType
from memory_os.classifier import RuleBasedClassifier

# The exact examples from Plan Step 36.
CASES = [
    ("What happened yesterday?", SemanticType.EPISODIC),
    ("What database are we using?", SemanticType.SEMANTIC),
    ("How do we deploy?", SemanticType.PROCEDURAL),
    ("Why did we choose PostgreSQL?", SemanticType.DECISION),
    ("Have we encountered this error before?", SemanticType.FAILURE),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_plan_step_36_examples(text, expected):
    classifier = RuleBasedClassifier()
    result = classifier.classify(text)
    assert result.semantic_type == expected


def test_default_fallback_has_no_matched_rule():
    classifier = RuleBasedClassifier()
    result = classifier.classify("The sky is blue.")
    assert result.semantic_type == SemanticType.SEMANTIC
    assert result.matched_rule is None


def test_matched_rule_is_reported_for_provenance():
    classifier = RuleBasedClassifier()
    result = classifier.classify("Why did the build fail?")
    # "why" is checked before the failure pattern -- decision wins, and the
    # winning pattern is reported so the classification is explainable.
    assert result.semantic_type == SemanticType.DECISION
    assert result.matched_rule is not None
