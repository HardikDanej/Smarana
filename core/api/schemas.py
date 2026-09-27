"""
Request/response shapes for the REST API (Plan Step 96).

A deliberately narrower surface than MemoryObject's full field set:
`id`/`version`/`created_at`/`updated_at`/`lifecycle_state`/`supersedes`/
`superseded_by` are server-managed, never client-supplied, and
`tenant_id` comes from the authenticated principal (api/auth.py), never
from the request body -- a caller cannot ask to write into a tenant
other than the one their API key is bound to.

`sensitivity`/`privacy_categories`/`tags` default to `None`, not
`MemoryObject`'s own hardcoded defaults (Phase 21): `None` means "the
caller didn't specify this," which `create_memory()` (app.py) needs to
tell apart from an explicit choice so a tenant's `TenantProfile` can
supply its own default instead -- an explicit `PrivacyLevel.PUBLIC` and
"not specified, use the profile" look identical if both are represented
the same way.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from memory_os.models import (
    MemoryClass,
    MemoryScope,
    Modality,
    PrivacyCategory,
    PrivacyLevel,
    SemanticType,
    SourceType,
)


class MemoryCreateRequest(BaseModel):
    content: str
    semantic_type: SemanticType
    scope: MemoryScope
    source_type: SourceType
    modality: Modality = Modality.TEXT
    entities: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_id: "str | None" = None
    evidence: list[str] = Field(default_factory=list)
    owner_id: "str | None" = None
    permissions: dict = Field(default_factory=dict)
    sensitivity: "PrivacyLevel | None" = None
    privacy_categories: "list[PrivacyCategory] | None" = None
    tags: "list[str] | None" = None
    memory_class: MemoryClass = MemoryClass.INFORMATION
    metadata: dict = Field(default_factory=dict)


class SearchResult(BaseModel):
    memory_id: str
    content: str
    score: float
    matched_by: list[str]
