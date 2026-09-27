from datetime import datetime, timezone

from memory_os import SemanticType
from memory_os.planning import (
    GraphExpander,
    QueryDecomposer,
    RetrievalPlanner,
    select_strategy,
)
from memory_os.relationships import RelationshipGraph, RelationshipType


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# --- Step 61: RetrievalPlanner ---


def test_plan_identifies_entities_mentioned_in_the_query():
    planner = RetrievalPlanner(known_entities=["Project Alpha", "Project Beta"])

    plan = planner.plan("Why did we move Project Alpha from AWS to GCP?")

    assert plan.entities == ["Project Alpha"]
    assert plan.intent == SemanticType.DECISION


def test_plan_steps_include_entity_and_decision_specific_steps():
    planner = RetrievalPlanner(known_entities=["Project Alpha"])

    plan = planner.plan("Why did we move Project Alpha from AWS to GCP?")

    assert "Find Project Alpha." in plan.steps
    assert "Find decision memory." in plan.steps
    assert plan.steps[-1] == "Assemble answer."


def test_plan_with_no_known_entities_still_produces_a_plan():
    planner = RetrievalPlanner()
    plan = planner.plan("How do we deploy?")
    assert plan.intent == SemanticType.PROCEDURAL
    assert plan.entities == []
    assert "Retrieve the relevant procedure." in plan.steps


def test_plan_records_as_of_when_given():
    planner = RetrievalPlanner()
    when = _dt("2026-02-01")
    plan = planner.plan("What database were we using?", as_of=when)
    assert plan.as_of == when
    assert any("2026-02-01" in step for step in plan.steps)


# --- Step 65: strategy selection ---


def test_decision_intent_includes_relationship_in_strategy():
    assert "relationship" in select_strategy(SemanticType.DECISION)


def test_default_strategy_is_keyword_and_vector_only():
    strategy = select_strategy(SemanticType.SEMANTIC)
    assert strategy == frozenset({"keyword", "vector"})


def test_plan_carries_the_strategy_for_its_intent():
    planner = RetrievalPlanner()
    plan = planner.plan("Why did we choose PostgreSQL?")
    assert plan.strategy == select_strategy(SemanticType.DECISION)


# --- Step 62: QueryDecomposer ---


def test_plan_step_62_worked_example_splits_into_three_subquestions():
    decomposer = QueryDecomposer()
    request = (
        "Tell me what changed in the project, why it changed, and whether "
        "our previous deployment procedure is still valid."
    )

    sub_questions = decomposer.decompose(request)

    assert len(sub_questions) == 3
    assert sub_questions[0].text == "Tell me what changed in the project"
    assert sub_questions[1].text == "why it changed"
    assert sub_questions[1].intent == SemanticType.DECISION
    assert sub_questions[2].text == "whether our previous deployment procedure is still valid"


def test_simple_request_with_no_conjunction_stays_one_subquestion():
    decomposer = QueryDecomposer()
    sub_questions = decomposer.decompose("What database are we using?")
    assert len(sub_questions) == 1
    assert sub_questions[0].text == "What database are we using"


def test_decompose_handles_standalone_and_without_a_comma():
    decomposer = QueryDecomposer()
    sub_questions = decomposer.decompose("What database are we using and how do we deploy?")
    assert len(sub_questions) == 2
    assert sub_questions[1].intent == SemanticType.PROCEDURAL


# --- Step 63: GraphExpander ---


def test_expand_respects_max_depth():
    graph = RelationshipGraph()
    graph.add("A", RelationshipType.DERIVED_FROM, "B")
    graph.add("B", RelationshipType.DERIVED_FROM, "C")
    graph.add("C", RelationshipType.DERIVED_FROM, "D")

    edges = GraphExpander(graph, max_depth=1).expand("A")

    reached = {e.target_id for e in edges} | {e.source_id for e in edges}
    assert "B" in reached
    assert "C" not in reached  # two hops away, past max_depth=1
    assert "D" not in reached


def test_expand_respects_max_edges():
    graph = RelationshipGraph()
    for i in range(50):
        graph.add("hub", RelationshipType.RELATED_TO, f"node-{i}")

    edges = GraphExpander(graph, max_depth=5, max_edges=10).expand("hub")

    assert len(edges) == 10


def test_expand_traverses_both_outgoing_and_incoming_edges():
    graph = RelationshipGraph()
    graph.add("skill", RelationshipType.DERIVED_FROM, "reflection")  # skill -> reflection (outgoing from skill)
    graph.add("other", RelationshipType.SUPPORTS, "skill")  # other -> skill (incoming to skill)

    edges = GraphExpander(graph, max_depth=1).expand("skill")

    neighbors = {e.target_id if e.source_id == "skill" else e.source_id for e in edges}
    assert neighbors == {"reflection", "other"}


def test_expand_from_entity_with_no_relationships_returns_empty():
    graph = RelationshipGraph()
    assert GraphExpander(graph).expand("lonely-node") == []
