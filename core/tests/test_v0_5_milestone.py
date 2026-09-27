"""
Memory OS v0.5 (Plan Step 75): the second milestone -- a multi-agent
learning prototype. The plan's own description:

    EVENT -> EPISODE -> PATTERN -> REFLECTION -> PROCEDURE -> VALIDATED SKILL

"while maintaining: provenance, confidence, temporal validity,
relationships, permissions, scope, evidence" -- alongside governance:
private / shared / inherited memory. This single test walks that whole
chain with real components (learning.py, access_control.py,
relationships.py) and checks every one of those seven properties is
actually present on the result, not just the pipeline's happy path.
"""

from memory_os import (
    LifecycleState,
    MemoryScope,
    PatternDetector,
    ProcedureValidator,
    SemanticType,
    SourceType,
    ValidationRecord,
    build_reflection,
    build_skill,
    promote_reflection_to_candidate_procedure,
    share_to_scope,
)
from memory_os.models import MemoryObject
from memory_os.relationships import RelationshipGraph, RelationshipType

from .fakes import FakeLLMProvider


def _episode(content: str, condition_met: bool, outcome: str) -> MemoryObject:
    return MemoryObject(
        content=content,
        semantic_type=SemanticType.FAILURE if outcome == "failure" else SemanticType.EPISODIC,
        scope=MemoryScope.AGENT,
        owner_id="agent-A",
        source_type=SourceType.AGENT_OBSERVATION,
        metadata={"env_validated": condition_met, "outcome": outcome},
    )


def test_full_v0_5_learning_chain_event_to_validated_skill():
    graph = RelationshipGraph()

    # EVENT -> EPISODE: Agent A's own private observations.
    episodes = [
        _episode("Deployment 1 failed.", condition_met=False, outcome="failure"),
        _episode("Deployment 2 failed.", condition_met=False, outcome="failure"),
        _episode("Deployment 3 succeeded after validating env vars.", condition_met=True, outcome="success"),
        _episode("Deployment 4 failed, env vars not validated.", condition_met=False, outcome="failure"),
    ]
    for ep in episodes:
        graph.add(ep.id, RelationshipType.RELATED_TO, "deployment-pipeline")

    # EPISODE -> PATTERN
    pattern = PatternDetector().detect(episodes, condition_key="env_validated", scope=MemoryScope.AGENT)
    assert pattern is not None
    assert pattern.predicts == "success"

    # PATTERN -> REFLECTION (governed: still private to Agent A, still
    # structurally uncertain per Step 48/Rule D -- reflections don't
    # promote themselves).
    reflection = build_reflection(episodes, FakeLLMProvider(), scope=MemoryScope.AGENT)
    reflection = reflection.new_version(owner_id="agent-A")
    graph.add(reflection.id, RelationshipType.DERIVED_FROM, episodes[0].id)
    for ep in episodes[1:]:
        graph.add(reflection.id, RelationshipType.DERIVED_FROM, ep.id)

    # REFLECTION -> CANDIDATE PROCEDURE
    procedure = promote_reflection_to_candidate_procedure(
        reflection,
        steps=["Load required variables.", "Validate them.", "Abort if missing."],
        scope=MemoryScope.AGENT,
        preconditions=["deployment pipeline configured"],
    )
    procedure = procedure.new_version(owner_id="agent-A")
    graph.add(procedure.id, RelationshipType.DERIVED_FROM, reflection.id)
    assert procedure.lifecycle_state == LifecycleState.CANDIDATE

    # PROCEDURE -> VALIDATED (Step 73: real repeated trials, not one success)
    validated_procedure = ProcedureValidator(min_attempts=5, min_success_rate=0.9).validate(
        procedure, ValidationRecord(attempts=100, successes=97)
    )
    assert validated_procedure.lifecycle_state == LifecycleState.VALIDATED

    # VALIDATED PROCEDURE -> SKILL (Rule E enforced: only reachable
    # because the procedure is actually VALIDATED)
    skill = build_skill(validated_procedure, tools=["docker", "aws-cli"])
    private_skill_memory = skill.as_memory(scope=MemoryScope.AGENT).new_version(owner_id="agent-A")
    graph.add(private_skill_memory.id, RelationshipType.DERIVED_FROM, validated_procedure.id)

    # GOVERNANCE: private -> shared. Agent A contributes the validated
    # skill (not the raw episodes) up to organization scope.
    shared_skill_memory = share_to_scope(
        private_skill_memory, new_scope=MemoryScope.ORGANIZATION, shared_by="org-memory", graph=graph
    )

    # --- Now verify every property Step 75 asks the system to maintain ---

    # Provenance: traceable to a real source type, not fabricated.
    assert private_skill_memory.source_type == SourceType.REFLECTION

    # Confidence: carried through from real validation numbers, not a
    # placeholder.
    assert shared_skill_memory.confidence == validated_procedure.confidence == 0.97

    # Temporal validity: the skill has real timestamps, not None.
    assert shared_skill_memory.created_at is not None
    assert skill.last_validated == validated_procedure.updated_at

    # Relationships: the full lineage is walkable, skill back to episode.
    lineage_from_shared = graph.lineage(shared_skill_memory.id)
    lineage_targets = {edge.target_id for edge in lineage_from_shared}
    assert private_skill_memory.id in lineage_targets
    assert validated_procedure.id in lineage_targets
    assert reflection.id in lineage_targets
    assert all(ep.id in lineage_targets for ep in episodes)

    # Permissions/ownership: private original still owned by Agent A;
    # the shared copy is reassigned, not silently left owner-less.
    assert private_skill_memory.owner_id == "agent-A"
    assert shared_skill_memory.owner_id == "org-memory"

    # Scope: private stayed AGENT-scoped; sharing produced a broader,
    # distinct ORGANIZATION-scoped copy -- inheritance, not a mutation.
    assert private_skill_memory.scope == MemoryScope.AGENT
    assert shared_skill_memory.scope == MemoryScope.ORGANIZATION
    assert shared_skill_memory.id != private_skill_memory.id

    # Evidence: sharing moves scope, not the warrant for belief -- the
    # shared copy still points at the same validated procedure the
    # private original did. Sharing lineage itself lives separately, in
    # metadata["shared_from"] and the graph edge checked above.
    assert shared_skill_memory.evidence == private_skill_memory.evidence == [validated_procedure.id]
    assert shared_skill_memory.metadata["shared_from"] == private_skill_memory.id
