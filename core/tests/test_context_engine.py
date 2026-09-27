from memory_os import LifecycleState, MemoryScope, ScoredMemory, SemanticType, SourceType
from memory_os.context_engine import ContextEngine
from memory_os.models import MemoryObject


def _memory(content: str, semantic_type: SemanticType, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=semantic_type,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def test_routes_memories_into_sections_by_semantic_type():
    current = _memory("Project Alpha uses PostgreSQL.", SemanticType.SEMANTIC)
    decision = _memory("PostgreSQL was chosen over MongoDB.", SemanticType.DECISION)
    procedure = _memory("Deploy with the standard pipeline.", SemanticType.PROCEDURAL)
    reflection = _memory("Deployments fail without env validation.", SemanticType.REFLECTIVE)
    historical = _memory(
        "Project Alpha used MongoDB.", SemanticType.SEMANTIC, lifecycle_state=LifecycleState.SUPERSEDED
    )

    results = [
        ScoredMemory(memory=m, score=1.0)
        for m in [current, decision, procedure, reflection, historical]
    ]

    context = ContextEngine().build(results)

    assert context.current_facts == [current.content]
    assert context.decisions == [decision.content]
    assert context.procedures == [procedure.content]
    assert context.reflections == [reflection.content]
    assert context.historical_facts == [historical.content]


def test_respects_max_items_budget():
    memories = [_memory(f"fact {i}", SemanticType.SEMANTIC) for i in range(20)]
    results = [ScoredMemory(memory=m, score=1.0) for m in memories]

    context = ContextEngine(max_items=5).build(results)

    total_items = (
        len(context.current_facts)
        + len(context.historical_facts)
        + len(context.decisions)
        + len(context.procedures)
        + len(context.reflections)
    )
    assert total_items == 5


def test_average_confidence_is_computed_over_selected_items():
    high = _memory("high confidence fact", SemanticType.SEMANTIC, confidence=0.9)
    low = _memory("low confidence fact", SemanticType.SEMANTIC, confidence=0.3)
    results = [ScoredMemory(memory=high, score=1.0), ScoredMemory(memory=low, score=1.0)]

    context = ContextEngine().build(results)

    assert abs(context.average_confidence - 0.6) < 1e-9


def test_render_produces_labeled_plain_text():
    memory = _memory("Project Alpha uses PostgreSQL.", SemanticType.SEMANTIC, confidence=0.8)
    context = ContextEngine().build([ScoredMemory(memory=memory, score=1.0)])

    text = context.render()

    assert "Current facts:" in text
    assert "- Project Alpha uses PostgreSQL." in text
    assert "Confidence: 0.80" in text


def test_empty_results_produce_empty_context():
    context = ContextEngine().build([])
    assert context.render() == "Confidence: 0.00"
