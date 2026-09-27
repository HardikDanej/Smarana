from memory_os import MemoryScope, SourceType
from memory_os.entity_resolution import EntityResolver
from memory_os.extraction import EXTRACTION_SCHEMA, ExtractionPipeline

from .fakes import FakeLLMProvider


PLAN_STEP_39_TEXT = "Hardik said the company moved its backend from AWS to GCP in June."


def test_extraction_builds_a_memory_object_from_provider_output():
    provider = FakeLLMProvider(
        extraction_result={
            "entity": "Company",
            "relation": "uses",
            "value": "GCP",
            "previous_value": "AWS",
            "valid_from": "June",
        }
    )
    pipeline = ExtractionPipeline(provider=provider)

    memory = pipeline.extract_memory(
        PLAN_STEP_39_TEXT,
        source_type=SourceType.USER_STATEMENT,
        scope=MemoryScope.PROJECT,
    )

    assert memory.content == PLAN_STEP_39_TEXT
    assert memory.entities == ["Company"]
    assert memory.relationships == [{"relation": "uses", "value": "GCP"}]
    assert memory.metadata["extraction"]["previous_value"] == "AWS"
    assert memory.metadata["extraction"]["valid_from"] == "June"
    assert memory.source_type == SourceType.USER_STATEMENT


def test_provider_is_called_with_the_declared_schema():
    provider = FakeLLMProvider()
    pipeline = ExtractionPipeline(provider=provider)

    pipeline.extract_memory(PLAN_STEP_39_TEXT, source_type=SourceType.TOOL, scope=MemoryScope.PROJECT)

    call_name, args, _ = provider.calls[0]
    assert call_name == "extract"
    _, schema_keys = args
    assert set(schema_keys) == set(EXTRACTION_SCHEMA)


def test_confidence_reflects_source_reliability_not_llm_certainty():
    provider = FakeLLMProvider(extraction_result={"entity": "X", "relation": "is", "value": "Y"})
    pipeline = ExtractionPipeline(provider=provider)

    stated = pipeline.extract_memory(PLAN_STEP_39_TEXT, source_type=SourceType.USER_STATEMENT, scope=MemoryScope.PROJECT)
    inferred = pipeline.extract_memory(PLAN_STEP_39_TEXT, source_type=SourceType.INFERRED, scope=MemoryScope.PROJECT)

    assert stated.confidence > inferred.confidence


def test_entity_resolver_is_applied_when_provided():
    resolver = EntityResolver()
    resolver.resolve("Company")  # seed the canonical form
    provider = FakeLLMProvider(extraction_result={"entity": "COMPANY", "relation": "uses", "value": "GCP"})
    pipeline = ExtractionPipeline(provider=provider, entity_resolver=resolver)

    memory = pipeline.extract_memory(PLAN_STEP_39_TEXT, source_type=SourceType.USER_STATEMENT, scope=MemoryScope.PROJECT)

    assert memory.entities == ["Company"]


def test_no_relation_or_value_yields_no_relationships():
    provider = FakeLLMProvider(extraction_result={"entity": "Company"})
    pipeline = ExtractionPipeline(provider=provider)

    memory = pipeline.extract_memory("Company exists.", source_type=SourceType.USER_STATEMENT, scope=MemoryScope.PROJECT)

    assert memory.relationships == []
