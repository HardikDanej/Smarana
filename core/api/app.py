"""
REST/OpenAPI surface (Plan Step 96): a FastAPI app over the engine.

This closes docs/THREAT_MODEL.md's own named API-surface gap head on --
"no authentication, rate limiting, or request-level policy enforcement
exists because there is no API yet to enforce it on" -- by making all
three non-optional on every memory-touching endpoint, not something a
caller has to remember: authentication (api/auth.py) resolves who is
calling before anything else runs; the rate limiter (api/rate_limit.py)
runs right after; PolicyEngine.can_store/can_retrieve/can_delete are
consulted on every request that needs them, closing THREAT_MODEL.md's
other open item too -- "PolicyEngine is not wired in automatically" --
at the one layer that both can and should do it (an external boundary,
not the storage layer, which THREAT_MODEL.md was right to keep clear of
policy logic).

A denied or missing memory both come back as 404, never 403 -- Phase
13's own retrieval philosophy ("an inaccessible memory is filtered out,
not merely deprioritized") extended to the API boundary: telling a
caller "this exists, but you can't see it" is itself a leak.

`create_app()` builds one self-contained app per call, not a module-
level singleton -- tests construct as many independent instances as they
need, each with its own storage/keys/limiter.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query, status

from memory_os.access_control import can_access_tenant
from memory_os.embedding import Embedder
from memory_os.models import MemoryObject
from memory_os.profiles import TenantProfileStore, apply_profile_defaults
from memory_os.retrieval import RetrievalEngine
from memory_os.security import PolicyEngine
from memory_os.storage import StorageAdapter
from memory_os.telemetry import Telemetry

from .auth import APIKeyStore, Principal, make_authenticate_dependency
from .rate_limit import RateLimitExceeded, RateLimiter
from .schemas import MemoryCreateRequest, SearchResult


def create_app(
    storage: StorageAdapter,
    *,
    api_keys: "APIKeyStore | None" = None,
    rate_limiter: "RateLimiter | None" = None,
    policy_engine: "PolicyEngine | None" = None,
    embedder: "Embedder | None" = None,
    telemetry: "Telemetry | None" = None,
    profile_store: "TenantProfileStore | None" = None,
) -> FastAPI:
    api_keys = api_keys if api_keys is not None else APIKeyStore()
    rate_limiter = rate_limiter if rate_limiter is not None else RateLimiter()
    policy_engine = policy_engine if policy_engine is not None else PolicyEngine(telemetry=telemetry)
    profile_store = profile_store if profile_store is not None else TenantProfileStore()
    retrieval_engine = RetrievalEngine(storage, embedder=embedder, telemetry=telemetry)

    app = FastAPI(title="Universal Memory OS API")
    app.state.api_keys = api_keys
    app.state.rate_limiter = rate_limiter
    app.state.policy_engine = policy_engine
    app.state.profile_store = profile_store
    app.state.storage = storage

    authenticate = make_authenticate_dependency(api_keys)

    def authenticate_and_rate_limit(principal: Principal = Depends(authenticate)) -> Principal:
        try:
            rate_limiter.check(principal.principal_id)
        except RateLimitExceeded as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
        return principal

    def _visible_or_404(memory: "MemoryObject | None", principal: Principal, permission_check) -> MemoryObject:
        """One shared gate for get/delete: missing, wrong tenant, and
        policy-denied all look identical from the outside -- 404."""
        if memory is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        if principal.tenant_id is not None and not can_access_tenant(memory, principal.tenant_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        if not permission_check(memory):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        return memory

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/memories", status_code=status.HTTP_201_CREATED, response_model=MemoryObject)
    def create_memory(
        request: MemoryCreateRequest, principal: Principal = Depends(authenticate_and_rate_limit)
    ) -> MemoryObject:
        # Phase 21: an explicit sensitivity/privacy_categories/tags in
        # the request always wins; otherwise the tenant's TenantProfile
        # (if one was registered) supplies its default instead of
        # MemoryObject's own hardcoded one.
        profile = profile_store.get(principal.tenant_id)
        sensitivity, privacy_categories, tags = apply_profile_defaults(
            profile,
            sensitivity=request.sensitivity,
            privacy_categories=request.privacy_categories,
            tags=request.tags,
        )
        candidate = MemoryObject(
            **request.model_dump(exclude={"owner_id", "sensitivity", "privacy_categories", "tags"}),
            tenant_id=principal.tenant_id,
            owner_id=request.owner_id or principal.principal_id,
            sensitivity=sensitivity,
            privacy_categories=privacy_categories,
            tags=tags,
        )
        decision = policy_engine.can_store(candidate)
        if not decision:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)
        storage.store(candidate)
        return candidate

    @app.get("/memories/{memory_id}", response_model=MemoryObject)
    def get_memory(memory_id: str, principal: Principal = Depends(authenticate_and_rate_limit)) -> MemoryObject:
        memory = storage.get(memory_id)
        return _visible_or_404(
            memory, principal, lambda m: bool(policy_engine.can_retrieve(m, principal.principal_id))
        )

    @app.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_memory(memory_id: str, principal: Principal = Depends(authenticate_and_rate_limit)) -> None:
        memory = storage.get(memory_id)
        _visible_or_404(memory, principal, lambda m: bool(policy_engine.can_delete(m, principal.principal_id)))
        storage.delete(memory_id)

    @app.get("/memories", response_model=list[SearchResult])
    def search_memories(
        q: str = Query(...),
        top_k: int = Query(default=10, ge=1, le=100),
        principal: Principal = Depends(authenticate_and_rate_limit),
    ) -> list[SearchResult]:
        results = retrieval_engine.retrieve(
            q, top_k=top_k, principal_id=principal.principal_id, tenant_id=principal.tenant_id
        )
        return [
            SearchResult(
                memory_id=r.memory.id, content=r.memory.content, score=r.score, matched_by=sorted(r.matched_by)
            )
            for r in results
        ]

    return app
