"""Universal Memory OS engine. V1 architecture frozen at 1.0.0 (Plan Step
100, docs/V1_ARCHITECTURE.md's 32-section specification). 1.1.0 (Phase
21) adds Adaptive Configuration Profiles -- additive and backward
compatible, closing the plan's own highest-priority self-flagged gap
without reopening the freeze: see docs/ADAPTIVE_PROFILES.md. 1.2.0
(Phase 22) names GDPR as the compliance target (gap #2) and adds data
subject rights (Articles 15/17/20) plus a recorded, not enforced, data
residency field on TenantProfile: see docs/GDPR_COMPLIANCE.md."""

__version__ = "1.2.0"

from .access_control import AccessPolicy, Permission, can_access_tenant, most_specific, share_to_scope
from .audit import AuditEntry, AuditLog
from .backup import export_memories, export_relationships, import_memories, import_relationships
from .classifier import Classification, RuleBasedClassifier
from .data_subject_rights import erase_data_subject, export_data_subject, find_memories_for_data_subject
from .compression import MemoryCompressor, deduplicate, drop_stale_or_low_confidence
from .conflict import ConflictResolver, UncertainBelief, apply_correction, resolve_uncertain
from .context_engine import ContextEngine, MemoryContext
from .embedding import Embedder, HashingEmbedder, cosine_similarity
from .encryption import Encryptor
from .entity_resolution import EntityResolver
from .extraction import EXTRACTION_SCHEMA, ExtractionPipeline
from .learning import (
    Pattern,
    PatternDetector,
    ProcedureValidator,
    Skill,
    ValidationRecord,
    build_skill,
    promote_reflection_to_candidate_procedure,
)
from .metrics import (
    contradiction_rate,
    mean_reciprocal_rank,
    precision_at_k,
    provenance_coverage,
    recall_at_k,
    staleness_rate,
)
from .models import (
    LifecycleState,
    MemoryClass,
    MemoryObject,
    MemoryScope,
    Modality,
    PrivacyCategory,
    PrivacyLevel,
    SemanticType,
    SourceType,
    TruthStatus,
    mark_superseded,
)
from .object_store import ObjectStore
from .planning import (
    GraphExpander,
    QueryDecomposer,
    RetrievalPlan,
    RetrievalPlanner,
    SubQuestion,
    select_strategy,
)
from .profiles import (
    ApplicationType,
    BusinessType,
    Industry,
    PolicyDefaults,
    RetentionPolicy,
    TenantProfile,
    TenantProfileStore,
    apply_profile_defaults,
)
from .providers import LLMProvider
from .reflection import build_reflection
from .reliability import FailureInjectingStorageAdapter, StorageFailure
from .retention import sweep_expired_memories
from .relationships import (
    STALE_LIFECYCLE_STATES,
    MemoryRelationship,
    RelationshipGraph,
    RelationshipType,
    recompute_confidence_from_dependencies,
)
from .retrieval import (
    KeywordRetriever,
    RelationshipRetriever,
    RetrievalEngine,
    ScoredMemory,
    TemporalRetriever,
    VectorRetriever,
)
from .security import (
    PoisoningGuard,
    PolicyDecision,
    PolicyEngine,
    PolicyResult,
    RiskAssessment,
    TrustLevel,
    can_promote,
    classify_memory_class,
    infer_trust_level,
)
from .storage import StorageAdapter
from .telemetry import Telemetry

__all__ = [
    "AccessPolicy",
    "apply_correction",
    "apply_profile_defaults",
    "ApplicationType",
    "AuditEntry",
    "AuditLog",
    "BusinessType",
    "build_reflection",
    "build_skill",
    "can_access_tenant",
    "can_promote",
    "Classification",
    "classify_memory_class",
    "ConflictResolver",
    "contradiction_rate",
    "ContextEngine",
    "cosine_similarity",
    "deduplicate",
    "drop_stale_or_low_confidence",
    "Embedder",
    "erase_data_subject",
    "export_data_subject",
    "export_memories",
    "export_relationships",
    "Encryptor",
    "EntityResolver",
    "EXTRACTION_SCHEMA",
    "ExtractionPipeline",
    "FailureInjectingStorageAdapter",
    "find_memories_for_data_subject",
    "GraphExpander",
    "HashingEmbedder",
    "import_memories",
    "import_relationships",
    "Industry",
    "infer_trust_level",
    "KeywordRetriever",
    "LifecycleState",
    "LLMProvider",
    "mark_superseded",
    "mean_reciprocal_rank",
    "MemoryClass",
    "MemoryCompressor",
    "MemoryContext",
    "MemoryObject",
    "MemoryRelationship",
    "MemoryScope",
    "Modality",
    "most_specific",
    "ObjectStore",
    "Pattern",
    "PatternDetector",
    "Permission",
    "PoisoningGuard",
    "PolicyDecision",
    "PolicyDefaults",
    "PolicyEngine",
    "PolicyResult",
    "precision_at_k",
    "PrivacyCategory",
    "PrivacyLevel",
    "ProcedureValidator",
    "promote_reflection_to_candidate_procedure",
    "provenance_coverage",
    "QueryDecomposer",
    "recall_at_k",
    "recompute_confidence_from_dependencies",
    "RelationshipGraph",
    "RelationshipRetriever",
    "RelationshipType",
    "resolve_uncertain",
    "RetentionPolicy",
    "RetrievalEngine",
    "RetrievalPlan",
    "RetrievalPlanner",
    "RiskAssessment",
    "RuleBasedClassifier",
    "ScoredMemory",
    "select_strategy",
    "SemanticType",
    "share_to_scope",
    "Skill",
    "SourceType",
    "STALE_LIFECYCLE_STATES",
    "staleness_rate",
    "StorageAdapter",
    "StorageFailure",
    "SubQuestion",
    "sweep_expired_memories",
    "TemporalRetriever",
    "Telemetry",
    "TenantProfile",
    "TenantProfileStore",
    "TrustLevel",
    "TruthStatus",
    "UncertainBelief",
    "ValidationRecord",
    "VectorRetriever",
]
