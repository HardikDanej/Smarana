"""
Memory ownership, permissions, sharing, and scope precedence
(Plan Steps 66-70).

Step 66 establishes agent-private memory (Agent B cannot automatically
see Agent A's). Step 67 layers shared memory on top: an agent
contributes SELECTED memories upward, not everything. Step 68 makes
ownership explicit -- every memory that matters has an owner. Step 69
is the permission model (READ/WRITE/UPDATE/DELETE/SHARE/EXPORT/DERIVE/
ADMIN). Step 70 is inheritance: when several memories about the same
subject exist at different scope levels, "the most specific valid
memory should generally win."

This is also where Phase 9's evaluation framework closes its one
documented gap. That file's comment said: "nothing built through Phase 9
enforces [scope] -- SQLiteAdapter and RetrievalEngine operate over the
whole store with no scope filter... Revisit this comment when Phase 13
is built, not before." This is Phase 13. See test_access_control.py's
test_isolation for the real, passing replacement.
"""

from __future__ import annotations

from enum import Enum

from .models import MemoryObject, MemoryScope
from .relationships import RelationshipGraph, RelationshipType


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"
    EXPORT = "export"
    DERIVE = "derive"
    ADMIN = "admin"


class AccessPolicy:
    """Step 68's rule (every memory needs an owner) plus Step 69's
    grants. The owner always has full access, unconditionally; anyone
    else needs an explicit grant for the specific permission requested,
    keyed by their principal_id or the "*" wildcard. ADMIN is treated as
    implying every other permission; nothing else implies anything else."""

    def can(self, memory: MemoryObject, principal_id: str, permission: Permission) -> bool:
        if memory.owner_id is not None and memory.owner_id == principal_id:
            return True

        grants = set(memory.permissions.get(principal_id, []))
        grants |= set(memory.permissions.get("*", []))
        return permission.value in grants or Permission.ADMIN.value in grants


def share_to_scope(
    memory: MemoryObject,
    new_scope: MemoryScope,
    shared_by: "str | None" = None,
    graph: "RelationshipGraph | None" = None,
) -> MemoryObject:
    """Step 67: an agent contributes a SELECTED private memory to a
    broader shared scope. Returns a new memory at that scope; the
    original private memory is untouched -- sharing is additive, a copy
    with traceable lineage (Step 52's derived_from, when a graph is
    supplied), never a move or a mutation of the private original."""
    shared = MemoryObject(
        content=memory.content,
        semantic_type=memory.semantic_type,
        scope=new_scope,
        confidence=memory.confidence,
        source_type=memory.source_type,
        source_id=memory.source_id,
        owner_id=shared_by if shared_by is not None else memory.owner_id,
        entities=list(memory.entities),
        # Evidence is why the memory is believed, not how it moved
        # scope -- a shared copy keeps its evidentiary backing.
        # "shared_from" (below) is the separate, sharing-specific link.
        evidence=list(memory.evidence),
        metadata={"shared_from": memory.id},
    )
    if graph is not None:
        graph.add(shared.id, RelationshipType.DERIVED_FROM, memory.id)
    return shared


# Step 70's own example chain: organization -> project -> task -> agent,
# broadest to most specific. Scopes outside that stated chain (DEVICE,
# MACHINE, APPLICATION, ENVIRONMENT, GLOBAL) aren't part of it, so they
# rank below everything named rather than being force-fit into a
# hierarchy the plan never specified for them.
_SCOPE_SPECIFICITY: dict[MemoryScope, int] = {
    MemoryScope.ORGANIZATION: 1,
    MemoryScope.TEAM: 2,
    MemoryScope.PROJECT: 3,
    MemoryScope.WORKFLOW: 4,
    MemoryScope.TASK: 5,
    MemoryScope.AGENT: 6,
    MemoryScope.USER: 6,  # same tier as agent -- both "who," not "where"
    MemoryScope.SUB_AGENT: 7,
    MemoryScope.SESSION: 8,
    MemoryScope.CONVERSATION: 9,
}


def most_specific(candidates: list[MemoryObject]) -> "MemoryObject | None":
    """Step 70: "The most specific valid memory should generally win."
    Given several memories about the same subject at different scope
    levels, returns the one from the narrowest scope. Ties (including
    every candidate being outside the named hierarchy) fall back to
    first-in-list -- this is a precedence rule, not a conflict resolver;
    genuine same-specificity contradictions are Step 58/59's job."""
    if not candidates:
        return None
    return max(candidates, key=lambda m: _SCOPE_SPECIFICITY.get(m.scope, 0))


def can_access_tenant(memory: MemoryObject, tenant_id: str) -> bool:
    """Step 81: tenant isolation is a hard wall, not a permission grant --
    "a query should never be able to accidentally search another
    tenant's memory." A memory with no tenant_id belongs to no tenant,
    not to every tenant, so a tenant-scoped query never accidentally
    surfaces untenanted data either."""
    return memory.tenant_id == tenant_id
