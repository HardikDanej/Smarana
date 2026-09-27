"""
Extraction pipeline (Plan Step 39): turns a raw event's text into a
structured MemoryObject.

Example from the plan:

    "Hardik said the company moved its backend from AWS to GCP in June."
        -> entity: Company, relation: uses, value: GCP,
           previous_value: AWS, valid_from: June

This module owns the *shape* of that pipeline. It calls out to whatever
LLMProvider it's given (Step 37's interface) to do the actual extraction,
and to the deterministic RuleBasedClassifier (Step 36) to assign a
semantic_type -- so the pipeline itself has no vendor dependency and is
tested against a fake provider, never a live one.
"""

from __future__ import annotations

from typing import Mapping

from .classifier import RuleBasedClassifier
from .entity_resolution import EntityResolver
from .models import MemoryObject, MemoryScope, SourceType
from .providers import LLMProvider

# field name -> what the provider should extract for it
EXTRACTION_SCHEMA: Mapping[str, str] = {
    "entity": "the primary subject entity this statement is about",
    "relation": "the relationship or predicate connecting the entity to its value",
    "value": "the new or current value/fact",
    "previous_value": "the prior value, if this statement describes a change; empty string otherwise",
    "valid_from": "when the new value became true, as stated in the text; empty string if not stated",
}

# Step 33/34: confidence reflects the reliability of the source, never the
# LLM's own certainty. An explicit first-person statement is the strongest
# source; an inference is the weakest. These are starting points, not a
# final scoring model -- Step 34 only asks that confidence and truth stay
# separate fields, not that this table be exhaustive.
_BASE_CONFIDENCE_BY_SOURCE: Mapping[SourceType, float] = {
    SourceType.USER_STATEMENT: 0.75,
    SourceType.AGENT_OBSERVATION: 0.7,
    SourceType.TOOL: 0.7,
    SourceType.EXTERNAL_SYSTEM: 0.6,
    SourceType.DOCUMENT: 0.6,
    SourceType.REFLECTION: 0.5,
    SourceType.INFERRED: 0.4,
}


class ExtractionPipeline:
    def __init__(
        self,
        provider: LLMProvider,
        classifier: RuleBasedClassifier | None = None,
        entity_resolver: EntityResolver | None = None,
    ):
        self.provider = provider
        self.classifier = classifier or RuleBasedClassifier()
        self.entity_resolver = entity_resolver

    def extract_memory(
        self,
        text: str,
        source_type: SourceType,
        scope: MemoryScope,
        source_id: str | None = None,
    ) -> MemoryObject:
        classification = self.classifier.classify(text)
        extracted = dict(self.provider.extract(text, EXTRACTION_SCHEMA))

        entity = extracted.get("entity") or ""
        if entity and self.entity_resolver is not None:
            entity = self.entity_resolver.resolve(entity)

        relationships = []
        relation = extracted.get("relation")
        value = extracted.get("value")
        if relation and value:
            relationships.append({"relation": relation, "value": value})

        metadata = {
            "extraction": extracted,
            "classification_rule": classification.matched_rule,
        }

        return MemoryObject(
            content=text,
            semantic_type=classification.semantic_type,
            scope=scope,
            entities=[entity] if entity else [],
            relationships=relationships,
            confidence=_BASE_CONFIDENCE_BY_SOURCE.get(source_type, 0.5),
            source_type=source_type,
            source_id=source_id,
            metadata=metadata,
        )
