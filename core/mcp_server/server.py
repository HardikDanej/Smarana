"""
MCP integration (Plan Step 98): "any MCP-compatible app can reach the
OS." This is the interoperability surface README.md's own Layout section
points at -- the plan's own repositioning of the existing Skill
(SKILL.md/server/) is that it "becomes the first client adapter... that
talks to the new engine over MCP (Step 98)," the same way an OpenAI
adapter or a LangGraph adapter would.

Tools call directly into the engine (StorageAdapter/RetrievalEngine/
PolicyEngine), not through the REST API -- an MCP server is itself a
process embedding the engine, not a REST client; Step 97's SDK is what a
caller reaches for when it wants HTTP instead. Every tool still goes
through PolicyEngine, same discipline as api/app.py's endpoints: an MCP
client is an external caller like any other, never a trusted internal
one just because it's in-process.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from memory_os.access_control import can_access_tenant
from memory_os.embedding import Embedder
from memory_os.models import MemoryObject, MemoryScope, PrivacyCategory, PrivacyLevel, SemanticType, SourceType
from memory_os.profiles import TenantProfileStore, apply_profile_defaults
from memory_os.retrieval import RetrievalEngine
from memory_os.security import PolicyEngine
from memory_os.storage import StorageAdapter


def create_mcp_server(
    storage: StorageAdapter,
    *,
    principal_id: str,
    tenant_id: "str | None" = None,
    policy_engine: "PolicyEngine | None" = None,
    embedder: "Embedder | None" = None,
    profile_store: "TenantProfileStore | None" = None,
) -> MCPServer:
    """One MCP server instance is bound to one principal/tenant, not one
    process serving many -- matching how an MCP stdio server is already
    1:1 with the client that spawned it, rather than inventing a
    per-tool-call auth scheme MCP itself has no slot for. api/app.py's
    API keys bind identity per request instead, because a REST server
    genuinely serves many callers from one process; this mirrors MCP's
    own shape rather than that one."""
    policy_engine = policy_engine if policy_engine is not None else PolicyEngine()
    profile_store = profile_store if profile_store is not None else TenantProfileStore()
    retrieval_engine = RetrievalEngine(storage, embedder=embedder)

    server = MCPServer(name="memory-os")

    @server.tool()
    def remember(
        content: str,
        semantic_type: str = "semantic",
        scope: str = "session",
        source_type: str = "user_statement",
        sensitivity: "str | None" = None,
        privacy_categories: "list[str] | None" = None,
        tags: "list[str] | None" = None,
    ) -> dict:
        """Store a new memory and return it. sensitivity/privacy_categories/tags
        left unset take this tenant's TenantProfile default, if one is
        registered (Phase 21)."""
        profile = profile_store.get(tenant_id)
        resolved_sensitivity, resolved_categories, resolved_tags = apply_profile_defaults(
            profile,
            sensitivity=PrivacyLevel(sensitivity) if sensitivity is not None else None,
            privacy_categories=(
                [PrivacyCategory(c) for c in privacy_categories] if privacy_categories is not None else None
            ),
            tags=tags,
        )
        candidate = MemoryObject(
            content=content,
            semantic_type=SemanticType(semantic_type),
            scope=MemoryScope(scope),
            source_type=SourceType(source_type),
            tenant_id=tenant_id,
            owner_id=principal_id,
            sensitivity=resolved_sensitivity,
            privacy_categories=resolved_categories,
            tags=resolved_tags,
        )
        decision = policy_engine.can_store(candidate)
        if not decision:
            # ToolError specifically, not a bare exception: this is the
            # policy engine's own considered answer, not a crash, and
            # ToolError is what the MCP layer reports back as a normal
            # is_error tool result rather than propagating as a raised
            # exception (its own docstring's distinction between "an
            # anticipated failure" and "a crash").
            raise ToolError(f"store denied: {decision.reason}")
        storage.store(candidate)
        return candidate.model_dump(mode="json")

    @server.tool()
    def recall(query: str, top_k: int = 10) -> list[dict]:
        """Search stored memories relevant to a query."""
        results = retrieval_engine.retrieve(
            query, top_k=top_k, principal_id=principal_id, tenant_id=tenant_id
        )
        return [{"memory_id": r.memory.id, "content": r.memory.content, "score": r.score} for r in results]

    @server.tool()
    def forget(memory_id: str) -> bool:
        """Delete a memory by id. Returns False (not an error) for a
        memory that doesn't exist, belongs to another tenant, or the
        caller isn't permitted to delete -- the same non-leaking shape
        api/app.py's 404s use, translated to MCP's tools-return-data
        convention rather than HTTP status codes."""
        memory = storage.get(memory_id)
        if memory is None:
            return False
        if tenant_id is not None and not can_access_tenant(memory, tenant_id):
            return False
        if not policy_engine.can_delete(memory, principal_id):
            return False
        storage.delete(memory_id)
        return True

    return server
