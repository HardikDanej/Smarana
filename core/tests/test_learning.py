import pytest

from memory_os import (
    LifecycleState,
    MemoryScope,
    PatternDetector,
    ProcedureValidator,
    SemanticType,
    SourceType,
    TruthStatus,
    ValidationRecord,
    build_reflection,
    build_skill,
    promote_reflection_to_candidate_procedure,
)
from memory_os.models import MemoryObject

from .fakes import FakeLLMProvider


def _episode(content: str, condition_met: bool, outcome: str) -> MemoryObject:
    return MemoryObject(
        content=content,
        semantic_type=SemanticType.FAILURE if outcome == "failure" else SemanticType.EPISODIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.AGENT_OBSERVATION,
        metadata={"env_validated": condition_met, "outcome": outcome},
    )


# --- Step 71: Pattern detection ---


def test_plan_step_71_worked_example():
    episodes = [
        _episode("Deployment 1 failed.", condition_met=False, outcome="failure"),
        _episode("Deployment 2 failed.", condition_met=False, outcome="failure"),
        _episode("Deployment 3 succeeded after validating env vars.", condition_met=True, outcome="success"),
        _episode("Deployment 4 failed, env vars not validated.", condition_met=False, outcome="failure"),
    ]

    pattern = PatternDetector().detect(episodes, condition_key="env_validated", scope=MemoryScope.PROJECT)

    assert pattern is not None
    assert pattern.predicts == "success"
    assert pattern.evidence_count == 4
    assert pattern.confidence == 1.0
    assert pattern.exceptions == 0


def test_pattern_confidence_reflects_partial_correlation():
    episodes = [
        _episode("A", condition_met=True, outcome="success"),
        _episode("B", condition_met=True, outcome="failure"),  # exception
        _episode("C", condition_met=False, outcome="failure"),
        _episode("D", condition_met=False, outcome="failure"),
    ]

    pattern = PatternDetector().detect(episodes, condition_key="env_validated", scope=MemoryScope.PROJECT)

    assert pattern.predicts == "success"
    assert 0 < pattern.confidence < 1.0
    assert pattern.exceptions == 1


def test_no_pattern_when_condition_metadata_is_absent():
    episodes = [MemoryObject(content="no metadata here", semantic_type=SemanticType.EPISODIC, scope=MemoryScope.PROJECT, source_type=SourceType.AGENT_OBSERVATION)]
    assert PatternDetector().detect(episodes, condition_key="env_validated", scope=MemoryScope.PROJECT) is None


def test_no_pattern_when_only_one_group_is_represented():
    episodes = [
        _episode("A", condition_met=True, outcome="success"),
        _episode("B", condition_met=True, outcome="success"),
    ]
    assert PatternDetector().detect(episodes, condition_key="env_validated", scope=MemoryScope.PROJECT) is None


# --- Step 72: Reflection -> candidate procedure ---


def test_promote_reflection_to_candidate_procedure():
    episode = _episode("Deployment failed.", condition_met=False, outcome="failure")
    reflection = build_reflection([episode], FakeLLMProvider(), scope=MemoryScope.PROJECT)

    procedure = promote_reflection_to_candidate_procedure(
        reflection,
        steps=["Load required variables.", "Validate them.", "Abort if missing."],
        scope=MemoryScope.PROJECT,
        preconditions=["deployment pipeline configured"],
    )

    assert procedure.semantic_type == SemanticType.PROCEDURAL
    assert procedure.lifecycle_state == LifecycleState.CANDIDATE
    assert procedure.truth_status == TruthStatus.UNCERTAIN
    assert procedure.content.startswith("1. Load required variables.")
    assert procedure.evidence == [reflection.id]
    assert procedure.metadata["preconditions"] == ["deployment pipeline configured"]


def test_promote_requires_a_reflective_memory():
    not_a_reflection = _episode("Deployment failed.", condition_met=False, outcome="failure")
    with pytest.raises(ValueError):
        promote_reflection_to_candidate_procedure(not_a_reflection, steps=["step"], scope=MemoryScope.PROJECT)


# --- Step 73: procedure validation ---


def _candidate_procedure() -> MemoryObject:
    episode = _episode("Deployment failed.", condition_met=False, outcome="failure")
    reflection = build_reflection([episode], FakeLLMProvider(), scope=MemoryScope.PROJECT)
    return promote_reflection_to_candidate_procedure(reflection, steps=["Validate env vars."], scope=MemoryScope.PROJECT)


def test_plan_step_73_worked_example_97_of_100():
    procedure = _candidate_procedure()
    record = ValidationRecord(attempts=100, successes=97)

    validated = ProcedureValidator().validate(procedure, record, applicable_conditions={"project_class": ["A", "B"]})

    assert validated.lifecycle_state == LifecycleState.VALIDATED
    assert validated.truth_status == TruthStatus.CONFIRMED
    assert validated.confidence == 0.97
    assert validated.metadata["applicable_conditions"] == {"project_class": ["A", "B"]}


def test_below_min_attempts_stays_candidate_regardless_of_rate():
    procedure = _candidate_procedure()
    record = ValidationRecord(attempts=1, successes=1)  # one lucky success

    validated = ProcedureValidator(min_attempts=5).validate(procedure, record)

    assert validated.lifecycle_state == LifecycleState.CANDIDATE


def test_below_min_success_rate_is_not_validated():
    procedure = _candidate_procedure()
    record = ValidationRecord(attempts=100, successes=40)

    validated = ProcedureValidator().validate(procedure, record)

    assert validated.lifecycle_state == LifecycleState.CANDIDATE
    assert validated.truth_status == TruthStatus.CONTRADICTED


# --- Step 74: Skill Memory ---


def test_build_skill_from_a_validated_procedure():
    procedure = _candidate_procedure()
    validated = ProcedureValidator().validate(procedure, ValidationRecord(attempts=100, successes=97))

    skill = build_skill(validated, tools=["docker", "aws-cli"], known_failures=["missing credentials"])

    assert skill.procedure_id == validated.id
    assert skill.success_rate == 0.97
    assert skill.tools == ["docker", "aws-cli"]
    assert skill.preconditions == []


def test_rule_e_skill_cannot_be_built_from_an_unvalidated_procedure():
    # Rule E (Step 53), enforced structurally: an LLM-fluent candidate
    # procedure is not a trusted skill just because it reads well.
    candidate = _candidate_procedure()
    assert candidate.lifecycle_state == LifecycleState.CANDIDATE
    with pytest.raises(ValueError):
        build_skill(candidate, tools=[])


def test_skill_as_memory_is_a_skill_type_memory_object():
    procedure = _candidate_procedure()
    validated = ProcedureValidator().validate(procedure, ValidationRecord(attempts=10, successes=9))
    skill = build_skill(validated, tools=["docker"])

    memory = skill.as_memory(scope=MemoryScope.ORGANIZATION)

    assert memory.semantic_type == SemanticType.SKILL
    assert memory.lifecycle_state == LifecycleState.VALIDATED
    assert memory.evidence == [validated.id]
    assert memory.metadata["tools"] == ["docker"]
