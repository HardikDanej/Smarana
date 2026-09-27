"""
The Universal Memory Object (Plan Step 8, implemented per Steps 31-35).

This is a deterministic data model only. It does not call an LLM, does not
touch storage, and does not classify or retrieve anything — Step 31 is
explicit that the Memory OS must work as a plain data system before any
intelligence is layered on top.

Two design rules from the plan are enforced here, not left to convention:

- confidence != truth (Step 34): a memory's `truth_status` (a judgment
  about whether it currently holds) and its `confidence` (a probability)
  are separate fields. A contradicted fact can carry any confidence value;
  the schema does not couple them.
- supersession is bidirectional (Step 35 / prior CHANGELOG precedent):
  `mark_superseded` sets `supersedes` and `superseded_by` on both sides of
  a replacement in the same operation, so "what replaced X" and "what did
  Y replace" are both directly readable without parsing free text.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SemanticType(str, Enum):
    """What kind of thing is being remembered (Step 4)."""

    WORKING_STATE = "working_state"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    REFLECTIVE = "reflective"
    DECISION = "decision"
    FAILURE = "failure"
    PREFERENCE = "preference"
    GOAL = "goal"
    INTENT = "intent"
    SKILL = "skill"
    KNOWLEDGE = "knowledge"
    CONVERSATION = "conversation"
    ENVIRONMENTAL = "environmental"
    SYSTEM = "system"


class MemoryScope(str, Enum):
    """Who owns this memory (Step 6). WORKSPACE added for Step 81's
    hierarchy (Organization -> Workspace -> Project -> User -> Agent ->
    Task) -- additive, sits between ORGANIZATION and PROJECT."""

    SESSION = "session"
    CONVERSATION = "conversation"
    TASK = "task"
    WORKFLOW = "workflow"
    AGENT = "agent"
    SUB_AGENT = "sub_agent"
    USER = "user"
    TEAM = "team"
    PROJECT = "project"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    DEVICE = "device"
    MACHINE = "machine"
    APPLICATION = "application"
    ENVIRONMENT = "environment"
    GLOBAL = "global"


class Modality(str, Enum):
    """What form the content takes (Step 7)."""

    TEXT = "text"
    STRUCTURED_DATA = "structured_data"
    DOCUMENT = "document"
    CODE = "code"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    SENSOR_DATA = "sensor_data"
    TIME_SERIES = "time_series"
    EVENTS = "events"
    LOGS = "logs"
    FILES = "files"
    BINARY_OBJECT = "binary_object"
    GRAPH = "graph"
    EMBEDDING = "embedding"


class SourceType(str, Enum):
    """Where this memory came from (Step 33) — the basis for provenance."""

    USER_STATEMENT = "user_statement"
    AGENT_OBSERVATION = "agent_observation"
    DOCUMENT = "document"
    TOOL = "tool"
    INFERRED = "inferred"
    REFLECTION = "reflection"
    EXTERNAL_SYSTEM = "external_system"


class TruthStatus(str, Enum):
    """A judgment about current validity — independent of confidence (Step 34)."""

    BELIEVED = "believed"
    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"
    UNCERTAIN = "uncertain"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class LifecycleState(str, Enum):
    """The state machine every memory moves through (Step 11).

    Not every memory traverses every state — this enumerates the possible
    states, not a required sequence.
    """

    OBSERVED = "observed"
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    STORED = "stored"
    CONFIRMED = "confirmed"
    CONSOLIDATED = "consolidated"
    UPDATED = "updated"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"


class MemoryClass(str, Enum):
    """Step 78: instructions and memories are separate categories, not
    two readings of the same field. Default is INFORMATION -- nothing
    becomes INSTRUCTION or POLICY without something explicitly saying
    so; a memory retrieved into context does not silently become an
    executable command just because its text sounds like one."""

    INFORMATION = "information"
    EVIDENCE = "evidence"
    HISTORY = "history"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    INSTRUCTION = "instruction"
    POLICY = "policy"


class PrivacyLevel(str, Enum):
    """Step 83: how sensitive a memory is, as a level -- distinct from
    PrivacyCategory (below), which is what KIND of sensitive data it is.
    "User likes Python" and "Production database credentials" are both
    representable, and radically different: the first is PUBLIC or
    INTERNAL with no category; the second is SECRET plus CREDENTIAL."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    SECRET = "secret"


class PrivacyCategory(str, Enum):
    """Step 83: the domain a memory's sensitivity comes from. A memory
    can carry more than one -- credentials are often also proprietary."""

    PERSONAL = "personal"
    FINANCIAL = "financial"
    SECURITY = "security"
    CREDENTIAL = "credential"
    PROPRIETARY = "proprietary"
    INDUSTRIAL = "industrial"


class MemoryObject(BaseModel):
    """The common envelope every memory type shares (Step 8)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = Field(default=1, ge=1)

    content: str
    semantic_type: SemanticType
    scope: MemoryScope
    modality: Modality = Modality.TEXT

    entities: list[str] = Field(default_factory=list)
    relationships: list[dict] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    truth_status: TruthStatus = TruthStatus.BELIEVED
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)

    source_type: SourceType
    source_id: str | None = None
    source_timestamp: datetime | None = None
    evidence: list[str] = Field(default_factory=list)

    tenant_id: str | None = None
    """Step 81: the outermost isolation boundary -- "a query should never
    be able to accidentally search another tenant's memory." None means
    untenanted, not "belongs to every tenant"; a tenant-scoped query
    never surfaces untenanted data by accident either (see
    access_control.can_access_tenant)."""

    owner_id: str | None = None
    """Step 68: who owns this memory -- a specific agent/user/project/
    organization identifier, distinct from `scope` (which category of
    container it belongs to). None means unowned/unclaimed, not
    "everyone owns it"; access_control.py's AccessPolicy treats an
    unowned memory as having no automatic owner-access shortcut."""

    permissions: dict = Field(default_factory=dict)
    """Step 69: principal_id -> list of granted Permission values (plain
    strings, not a set -- this field round-trips through JSON via
    model_dump_json()/model_validate_json(), and JSON has no set type).
    The "*" key is a wildcard grant to any principal."""

    sensitivity: PrivacyLevel = PrivacyLevel.INTERNAL
    privacy_categories: list[PrivacyCategory] = Field(default_factory=list)
    """Step 83: zero or more domain tags (a memory can be both FINANCIAL
    and CREDENTIAL, for instance) -- kept separate from `sensitivity`,
    which is a single level, not a set."""

    tags: list[str] = Field(default_factory=list)
    """Phase 21 (Adaptive Configuration Profiles): free-form,
    tenant/profile-defined categorization, deliberately separate from
    `privacy_categories`. `PrivacyCategory` is a fixed, reviewed,
    security-relevant enum (Step 83) and stays closed -- extending it
    per tenant would mean an unreviewed string silently gaining
    security meaning. `tags` is the honest "taxonomy extension"
    mechanism instead: open-ended, tenant-specific, carries no special
    handling of its own (unlike sensitivity, nothing in PolicyEngine
    reads it) -- a `TenantProfile` (profiles.py) can supply defaults
    for it, the same way it can for `sensitivity`."""

    memory_class: MemoryClass = MemoryClass.INFORMATION

    data_subject_ids: list[str] = Field(default_factory=list)
    """Phase 22 (compliance target: GDPR): the real person or people this
    memory's content is about, when that's someone other than
    `owner_id`. GDPR's rights (Article 15 access, Article 17 erasure,
    Article 20 portability) belong to a data subject -- a person -- not
    a tenant or an agent; `owner_id` in this codebase usually names the
    agent/system that manages a memory, which is a different question
    from whose personal data it contains. A healthcare tenant's memory
    about a patient is a clear example: the patient is a data subject
    here even though they never touch this system as a principal.
    data_subject_rights.py's erase_data_subject()/export_data_subject()
    are what read this field; nothing else in this codebase does, the
    same "no special handling unless a module explicitly reads it"
    discipline `tags` (Phase 21) already established."""

    object_ref: str | None = None
    """Step 90: a reference into an ObjectStore for memories whose real
    content is binary (Modality.FILES/BINARY_OBJECT/IMAGE/AUDIO/VIDEO/...)
    -- `content` stays a human-readable caption/description either way;
    this is where the actual bytes live. None means this memory has no
    binary payload, the case every earlier phase's text-only memories
    are still in."""

    lifecycle_state: LifecycleState = LifecycleState.OBSERVED
    supersedes: str | None = None
    superseded_by: str | None = None

    metadata: dict = Field(default_factory=dict)

    @property
    def event_time(self) -> datetime | None:
        """Step 56, bitemporal model: when this became true IN THE WORLD.
        `valid_from` already carries exactly this meaning -- this is a
        named accessor, not a second field, so the two can never drift
        apart. None means the state's start time was never recorded."""
        return self.valid_from

    @property
    def knowledge_time(self) -> datetime:
        """Step 56: when the SYSTEM learned this -- distinct from
        event_time. "Actual migration: January. Memory learned: March."
        `observed_at` carries this when explicitly recorded; `created_at`
        is the honest fallback when it wasn't, since a memory can't exist
        in storage before the system learned it."""
        return self.observed_at or self.created_at

    @model_validator(mode="after")
    def _no_self_supersession(self) -> "MemoryObject":
        if self.supersedes is not None and self.supersedes == self.id:
            raise ValueError("a memory cannot supersede itself")
        if self.superseded_by is not None and self.superseded_by == self.id:
            raise ValueError("a memory cannot be superseded by itself")
        return self

    def new_version(self, **changes) -> "MemoryObject":
        """Returns a new object: same id, version + 1, created_at preserved.

        Step 32: memories are never overwritten in place — we need history.
        """
        data = self.model_dump()
        data.update(changes)
        data["version"] = self.version + 1
        data["updated_at"] = _utcnow()
        return MemoryObject(**data)


def mark_superseded(old: MemoryObject, new: MemoryObject) -> tuple[MemoryObject, MemoryObject]:
    """Links a replacement to the memory it replaces, on both sides at once.

    The old memory becomes `superseded` rather than silently disappearing
    (Step 35); the new memory records what it replaced.
    """
    updated_old = old.new_version(
        superseded_by=new.id,
        lifecycle_state=LifecycleState.SUPERSEDED,
        truth_status=TruthStatus.SUPERSEDED,
    )
    updated_new = MemoryObject(**{**new.model_dump(), "supersedes": updated_old.id})
    return updated_old, updated_new
