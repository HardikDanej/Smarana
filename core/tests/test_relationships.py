from memory_os import (
    LifecycleState,
    MemoryScope,
    RelationshipGraph,
    RelationshipType,
    SemanticType,
    SourceType,
    TruthStatus,
    recompute_confidence_from_dependencies,
)
from memory_os.models import MemoryObject


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def test_add_and_query_outgoing_and_incoming_edges():
    graph = RelationshipGraph()
    reflection = _memory("Deployments fail without env validation.")
    episode = _memory("Deployment failed: missing env variable.")

    graph.add(reflection.id, RelationshipType.DERIVED_FROM, episode.id)

    outgoing = graph.outgoing(reflection.id)
    incoming = graph.incoming(episode.id)

    assert len(outgoing) == 1
    assert outgoing[0].target_id == episode.id
    assert outgoing[0].relationship_type == RelationshipType.DERIVED_FROM
    assert incoming == outgoing


def test_relationship_type_filter_narrows_results():
    graph = RelationshipGraph()
    a, b, c = _memory("A"), _memory("B"), _memory("C")
    graph.add(a.id, RelationshipType.DERIVED_FROM, b.id)
    graph.add(a.id, RelationshipType.CONTRADICTS, c.id)

    derived_only = graph.outgoing(a.id, RelationshipType.DERIVED_FROM)

    assert len(derived_only) == 1
    assert derived_only[0].target_id == b.id


def test_lineage_walks_the_full_derived_from_chain():
    # Step 54's own example: Skill <- Reflection <- Episode1, Episode2
    skill = _memory("Deploy Python API", semantic_type=SemanticType.SKILL)
    reflection = _memory("Env validation prevents failures.", semantic_type=SemanticType.REFLECTIVE)
    episode1 = _memory("Deployment 1 failed.", semantic_type=SemanticType.FAILURE)
    episode2 = _memory("Deployment 2 failed.", semantic_type=SemanticType.FAILURE)

    graph = RelationshipGraph()
    graph.add(skill.id, RelationshipType.DERIVED_FROM, reflection.id)
    graph.add(reflection.id, RelationshipType.DERIVED_FROM, episode1.id)
    graph.add(reflection.id, RelationshipType.DERIVED_FROM, episode2.id)

    lineage = graph.lineage(skill.id)
    targets = {edge.target_id for edge in lineage}

    assert targets == {reflection.id, episode1.id, episode2.id}


def test_lineage_is_cycle_safe():
    a, b = _memory("A"), _memory("B")
    graph = RelationshipGraph()
    graph.add(a.id, RelationshipType.DERIVED_FROM, b.id)
    graph.add(b.id, RelationshipType.DERIVED_FROM, a.id)  # cycle

    lineage = graph.lineage(a.id)  # must terminate, not loop forever

    assert len(lineage) == 2


def test_dependencies_returns_only_direct_targets_not_full_lineage():
    skill = _memory("Deploy Python API", semantic_type=SemanticType.SKILL)
    reflection = _memory("Env validation prevents failures.", semantic_type=SemanticType.REFLECTIVE)
    episode = _memory("Deployment failed.", semantic_type=SemanticType.FAILURE)

    graph = RelationshipGraph()
    graph.add(skill.id, RelationshipType.DERIVED_FROM, reflection.id)
    graph.add(reflection.id, RelationshipType.DERIVED_FROM, episode.id)

    assert graph.dependencies(skill.id) == [reflection.id]


def test_rule_b_multiple_memory_types_can_derive_from_the_same_episode():
    # Step 53, Rule B/C: a semantic memory AND a procedure may both derive
    # from the same episode set -- coexistence, not competition.
    episode = _memory("Migrated backend from AWS to GCP.", semantic_type=SemanticType.EPISODIC)
    semantic_fact = _memory("Project uses GCP.", semantic_type=SemanticType.SEMANTIC)
    procedure = _memory("Migration procedure.", semantic_type=SemanticType.PROCEDURAL)

    graph = RelationshipGraph()
    graph.add(semantic_fact.id, RelationshipType.DERIVED_FROM, episode.id)
    graph.add(procedure.id, RelationshipType.DERIVED_FROM, episode.id)

    incoming = graph.incoming(episode.id, RelationshipType.DERIVED_FROM)
    assert {e.source_id for e in incoming} == {semantic_fact.id, procedure.id}


def test_confidence_drops_when_all_dependencies_are_stale():
    fact = _memory("Customer uses PostgreSQL.", confidence=0.8)
    stale_evidence = [
        _memory("Evidence A", lifecycle_state=LifecycleState.SUPERSEDED),
        _memory("Evidence B", lifecycle_state=LifecycleState.FORGOTTEN),
    ]

    updated = recompute_confidence_from_dependencies(fact, stale_evidence)

    assert updated.confidence <= 0.3
    assert updated.truth_status == TruthStatus.UNCERTAIN
    assert updated.version == fact.version + 1


def test_confidence_unaffected_when_any_dependency_still_live():
    fact = _memory("Customer uses PostgreSQL.", confidence=0.8)
    mixed_evidence = [
        _memory("Evidence A", lifecycle_state=LifecycleState.SUPERSEDED),
        _memory("Evidence B", lifecycle_state=LifecycleState.STORED),
    ]

    updated = recompute_confidence_from_dependencies(fact, mixed_evidence)

    assert updated is fact
    assert updated.confidence == 0.8


def test_confidence_unaffected_with_no_dependencies():
    fact = _memory("Customer uses PostgreSQL.", confidence=0.8)
    assert recompute_confidence_from_dependencies(fact, []) is fact
