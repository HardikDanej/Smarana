"""
Retrieval, Steps 42-45: KeywordRetriever, VectorRetriever,
TemporalRetriever, RelationshipRetriever, and fusion into the first
Memory Router.

    RetrievalEngine
           |
           +-- KeywordRetriever    (Step 41/42)
           +-- VectorRetriever     (Step 42, optional adapter)
           +-- TemporalRetriever   (Step 43)
           +-- RelationshipRetriever (Step 44)

GraphRetriever isn't built here -- Step 44 is explicit that a lightweight
local traversal is enough at this stage: "We don't need Neo4j yet."

Fusion (Step 45) is a plain score-sum merge across retrievers, not a
tuned relevance formula -- Step 21 schedules that later. The point of
this phase is that fusion is the default shape, not that any one
retriever wins outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from contextlib import nullcontext

from .access_control import AccessPolicy, Permission, can_access_tenant
from .embedding import Embedder, HashingEmbedder, cosine_similarity
from .models import LifecycleState, MemoryObject
from .storage import StorageAdapter
from .telemetry import Telemetry

# Step 53, Rule G: "Current context should normally prefer currently
# valid information." A dampening, not exclusion -- Rule F requires a
# superseded fact to remain historically retrievable, so it must still
# be findable, just ranked behind its live replacement by default.
_SUPERSEDED_SCORE_DAMPENING = 0.5


@dataclass
class ScoredMemory:
    memory: MemoryObject
    score: float
    matched_by: set[str] = field(default_factory=set)


class KeywordRetriever:
    """Step 41/42: exact/keyword search over a StorageAdapter's full-text index."""

    def __init__(self, storage: StorageAdapter):
        self.storage = storage

    def retrieve(self, query: str, top_k: int = 10) -> list[ScoredMemory]:
        results = self.storage.search(query, top_k=top_k)
        # FTS rank order is the only signal available through this
        # interface; converted to a descending score so fusion can combine
        # it with other retrievers' scores.
        n = max(len(results), 1)
        return [
            ScoredMemory(memory=memory, score=1.0 - (i / n), matched_by={"keyword"})
            for i, memory in enumerate(results)
        ]


class VectorRetriever:
    """Step 42: similarity search, an optional adapter over whatever
    Embedder is supplied. Embeds the full result set on every call --
    fine at the scale this phase operates at; a real vector index is a
    later-phase concern (Step 87, pgvector), not this one."""

    def __init__(self, storage: StorageAdapter, embedder: Embedder | None = None):
        self.storage = storage
        self.embedder = embedder or HashingEmbedder()

    def retrieve(self, query: str, top_k: int = 10) -> list[ScoredMemory]:
        query_vector = self.embedder.embed(query)
        scored = []
        for memory in self.storage.list_all():
            similarity = cosine_similarity(query_vector, self.embedder.embed(memory.content))
            if similarity > 0:
                scored.append(ScoredMemory(memory=memory, score=similarity, matched_by={"vector"}))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]


class TemporalRetriever:
    """Step 43: what was valid at a requested point in time, using
    valid_from/valid_until -- not just "is it in the database."""

    def __init__(self, storage: StorageAdapter):
        self.storage = storage

    def valid_as_of(self, when: datetime) -> list[ScoredMemory]:
        results = []
        for memory in self.storage.list_all():
            if memory.valid_from is not None and when < memory.valid_from:
                continue
            if memory.valid_until is not None and when > memory.valid_until:
                continue
            results.append(ScoredMemory(memory=memory, score=1.0, matched_by={"temporal"}))
        return results

    def valid_now(self) -> list[ScoredMemory]:
        """Step 57: "What is true now?" """
        return self.valid_as_of(datetime.now(timezone.utc))

    def changed_between(self, start: datetime, end: "datetime | None" = None) -> list[ScoredMemory]:
        """Step 57: "What changed between January and June?" -- every
        memory whose validity window opened or closed inside [start, end).
        `end=None` means open-ended: "what changed after start" (Step 57's
        "what changed after event X", once X is resolved to a timestamp)."""
        results = []
        for memory in self.storage.list_all():
            starts_in_window = memory.valid_from is not None and start <= memory.valid_from and (
                end is None or memory.valid_from < end
            )
            ends_in_window = memory.valid_until is not None and start <= memory.valid_until and (
                end is None or memory.valid_until < end
            )
            if starts_in_window or ends_in_window:
                results.append(ScoredMemory(memory=memory, score=1.0, matched_by={"temporal"}))
        return results

    def previous_state(self, memory_id: str) -> "MemoryObject | None":
        """Step 57: "What was the previous state?" -- one hop back along
        the supersedes chain (Step 35)."""
        memory = self.storage.get(memory_id)
        if memory is None or memory.supersedes is None:
            return None
        return self.storage.get(memory.supersedes)


class RelationshipRetriever:
    """Step 44: related() as a lightweight local traversal, not a graph
    database. Two memories are "related" here if they share at least one
    entity -- one hop, not a general graph query."""

    def __init__(self, storage: StorageAdapter):
        self.storage = storage

    def related(self, memory_id: str) -> list[ScoredMemory]:
        anchor = self.storage.get(memory_id)
        if anchor is None or not anchor.entities:
            return []
        anchor_entities = set(anchor.entities)
        results = []
        for memory in self.storage.list_all():
            if memory.id == anchor.id:
                continue
            shared = anchor_entities & set(memory.entities)
            if shared:
                results.append(
                    ScoredMemory(
                        memory=memory,
                        score=len(shared) / len(anchor_entities),
                        matched_by={"relationship"},
                    )
                )
        results.sort(key=lambda s: s.score, reverse=True)
        return results


class RetrievalEngine:
    """Steps 45 and 64: fusion. A memory found by more than one retriever
    gets both scores summed and both retrievers recorded in matched_by.
    Step 64 adds relationship results to the default fusion (previously
    RelationshipRetriever needed its own separate call): whatever keyword
    or vector search already anchored on gets its entity-linked neighbors
    pulled in too, so "no individual retrieval technology is treated as
    universally superior" is true of the default call, not just something
    a caller can opt into by hand."""

    def __init__(
        self,
        storage: StorageAdapter,
        embedder: Embedder | None = None,
        telemetry: "Telemetry | None" = None,
    ):
        self.storage = storage
        self.keyword = KeywordRetriever(storage)
        self.vector = VectorRetriever(storage, embedder=embedder)
        self.temporal = TemporalRetriever(storage)
        self.relationship = RelationshipRetriever(storage)
        self.access_policy = AccessPolicy()
        self.telemetry = telemetry

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        as_of: datetime | None = None,
        include_relationships: bool = True,
        principal_id: str | None = None,
        tenant_id: str | None = None,
    ) -> list[ScoredMemory]:
        # Step 91: opt-in the same way audit_log is on PolicyEngine --
        # omitting telemetry costs nothing (nullcontext, no metric call),
        # every prior test with no telemetry argument keeps passing.
        span = (
            self.telemetry.span("retrieval_engine.retrieve", query=query, top_k=top_k)
            if self.telemetry is not None
            else nullcontext()
        )
        with span:
            merged: dict[str, ScoredMemory] = {}

            for scored in self.keyword.retrieve(query, top_k=top_k):
                merged[scored.memory.id] = scored

            for scored in self.vector.retrieve(query, top_k=top_k):
                if scored.memory.id in merged:
                    existing = merged[scored.memory.id]
                    existing.score += scored.score
                    existing.matched_by |= scored.matched_by
                else:
                    merged[scored.memory.id] = scored

            if include_relationships:
                for anchor_id in list(merged.keys()):
                    for scored in self.relationship.related(anchor_id):
                        if scored.memory.id in merged:
                            existing = merged[scored.memory.id]
                            existing.score += scored.score
                            existing.matched_by |= scored.matched_by
                        else:
                            merged[scored.memory.id] = scored

            if tenant_id is not None:
                # Step 81: the outer wall, checked before principal_id's inner
                # one -- a query never crosses a tenant boundary, full stop,
                # regardless of what any per-memory permission grant says.
                merged = {mid: s for mid, s in merged.items() if can_access_tenant(s.memory, tenant_id)}

            if principal_id is not None:
                # Step 66/69: an inaccessible memory is filtered out before
                # ranking or temporal logic ever sees it -- not merely
                # deprioritized, the way Rule G dampens superseded memories.
                merged = {
                    mid: s
                    for mid, s in merged.items()
                    if self.access_policy.can(s.memory, principal_id, Permission.READ)
                }

            if as_of is not None:
                # An explicit historical query: no dampening -- Rule F says a
                # superseded fact must be fully retrievable for its own era.
                valid_ids = {s.memory.id for s in self.temporal.valid_as_of(as_of)}
                merged = {mid: s for mid, s in merged.items() if mid in valid_ids}
            else:
                # No point in time requested: "give me the current state,"
                # so superseded memories are still discoverable (Rule F) but
                # ranked behind currently-valid ones by default (Rule G).
                for scored in merged.values():
                    if scored.memory.lifecycle_state == LifecycleState.SUPERSEDED:
                        scored.score *= _SUPERSEDED_SCORE_DAMPENING

            ranked = sorted(merged.values(), key=lambda s: s.score, reverse=True)
            results = ranked[:top_k]
            if self.telemetry is not None:
                self.telemetry.record_metric(
                    "retrieval_engine.result_count", float(len(results)), query=query
                )
            return results
