"""
Memory OS v0.1 (Plan Step 50): the first milestone -- a complete,
demonstrable cycle, not a collection of architectural documents.

    User/Agent -> Observation -> Memory Formation -> Memory Object
        -> Storage -> Query -> Retrieval Planning (keyword, vector,
        temporal, relationship) -> Fusion -> Context Engine -> LLM/Agent

This single test walks that whole cycle with real components (SQLite
storage, the actual RetrievalEngine and ContextEngine) and only the LLM
call itself faked, exactly like every other intelligence-layer test in
this suite.
"""

from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import MemoryScope, SemanticType, SourceType
from memory_os.context_engine import ContextEngine
from memory_os.extraction import ExtractionPipeline
from memory_os.models import MemoryObject
from memory_os.retrieval import RetrievalEngine

from .fakes import FakeLLMProvider


def test_full_v0_1_cycle_observation_to_context():
    # 1. Observation: raw text a user actually said.
    observation = "Hardik said Project Alpha moved its backend from AWS to GCP in June."

    # 2. Memory Formation: extraction turns the observation into a
    #    structured, classified MemoryObject. No LLM call happens for
    #    real -- the provider is scripted, same as every extraction test.
    provider = FakeLLMProvider(
        extraction_result={
            "entity": "Project Alpha",
            "relation": "uses",
            "value": "GCP",
            "previous_value": "AWS",
            "valid_from": "June",
        }
    )
    pipeline = ExtractionPipeline(provider=provider)
    migration_memory = pipeline.extract_memory(
        observation, source_type=SourceType.USER_STATEMENT, scope=MemoryScope.PROJECT
    )

    assert migration_memory.entities == ["Project Alpha"]

    # 3. Storage: the Memory Object is persisted, not just constructed.
    storage = SQLiteAdapter()
    storage.store(migration_memory)

    # A couple of other memories so retrieval has to do real work, not
    # just return the only row in the table.
    decision = MemoryObject(
        content="GCP was chosen over AWS for lower cost.",
        semantic_type=SemanticType.DECISION,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
        entities=["Project Alpha"],
    )
    procedure = MemoryObject(
        content="Deploy Project Alpha with the standard GCP pipeline.",
        semantic_type=SemanticType.PROCEDURAL,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
        entities=["Project Alpha"],
    )
    unrelated = MemoryObject(
        content="The office coffee machine was replaced last week.",
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    for memory in (decision, procedure, unrelated):
        storage.store(memory)

    assert len(storage.list_all()) == 4

    # 4. Query + 5. Retrieval Planning + 6. Fusion: a real question,
    #    answered by keyword+vector fusion over everything stored.
    query = "What does Project Alpha use for its backend?"
    ranked = RetrievalEngine(storage).retrieve(query, top_k=5)

    ranked_ids = [r.memory.id for r in ranked]
    assert migration_memory.id in ranked_ids
    assert unrelated.id not in ranked_ids  # fusion should not surface the noise memory

    # 7. Context Engine: raw ranked rows become a usable package, not a
    #    database dump.
    context = ContextEngine().build(ranked)
    rendered = context.render()

    assert migration_memory.content in context.current_facts
    assert decision.content in context.decisions
    assert procedure.content in context.procedures
    assert "Confidence:" in rendered

    # 8. LLM/Agent: this rendered string is what a real LLMProvider.reason()
    #    call would receive as context -- confirmed reachable, not invoked
    #    for real here (that's what test_claude_provider.py already covers).
    assert isinstance(rendered, str) and len(rendered) > 0
