# V1 Architecture Package (Plan Step 100)

**Status: frozen at 1.0.0, gap #1 closed at 1.1.0.** Phase 21 (not one
of the plan's original 100 steps) built Adaptive Configuration
Profiles — see `docs/ADAPTIVE_PROFILES.md` — closing gap #1 in this
document's own closing list below. That's additive and backward
compatible, not a reopening of the freeze: nothing in the 32 sections
below changed shape, and gap #1's entry is left in place as the
historical record, with a forward reference, the same way
`docs/POSTGRES_RLS.md` handled its own later closure.

**Status: frozen.** `memory_os.__version__ == "1.0.0"`. This is the
plan's own "32-document specification package (Constitution through
Client Integration Guide)," delivered as 32 numbered sections in one
document rather than 32 separate files. That choice is deliberate, not
a shortcut: several of the 32 areas the plan implies would, split into
their own files, either restate an existing document under a new title
(padding) or need invented substance this codebase's 20 phases of actual
work don't support (fabrication). Neither is this project's standard.
Every section below is grounded in a real file, test, or gate that
already exists; every section that names a gap names it as a gap, the
same discipline `docs/THREAT_MODEL.md` and `docs/POSTGRES_RLS.md`
already established.

"Frozen" means: this is what V1 actually is, decided and written down,
so nothing after this point ships against a moving target. It does not
mean every gap named here is closed — Section 32 and the closing list
say explicitly which ones aren't, and that they're V2, not silently
dropped.

---

## 1. Constitution

Four rules this codebase enforces structurally, not by convention, since
Phase 6:

- **Confidence is not truth** (Step 34): `MemoryObject.confidence` (a
  probability) and `truth_status` (a judgment) are independent fields. A
  contradicted fact can carry any confidence value.
- **Core imports no vendor technology** (Step 31, and every phase since):
  `core/memory_os` imports no LLM, storage, crypto, telemetry, or web
  framework library — proven, not asserted, by
  `scripts/verify_no_llm_dependency.py` and
  `scripts/verify_adapter_isolation.py`, both re-run every phase (G2/G4,
  and their per-phase re-checks through G31).
- **Schema evolution is additive-only**: every new `MemoryObject` field
  across 20 phases (`tenant_id`, `sensitivity`, `object_ref`, ...) got a
  default and was checked against every existing test usage. Nothing was
  ever renamed or removed out from under an existing caller.
- **No vacuous tests, no faked infrastructure**: Phases 17-19's
  Postgres, telemetry, REST, and MCP tests run against real running
  services, not mocks — skip cleanly when unreachable
  (`tests/conftest.py`), never silently pass against a stub standing in
  for the real thing.

## 2. Universal Memory Object Specification

`memory_os/models.py`. The common envelope every memory shares: identity
and versioning (`id`, `version`, immutable history via `new_version()`),
content and modality, temporal fields, confidence/truth/importance/
reliability, provenance, tenancy and ownership, permissions, privacy
classification, memory class, lifecycle state, and free-form metadata.
Validated by Pydantic v2; `test_models.py`.

## 3. Memory Taxonomy

`SemanticType` (episodic/semantic/procedural/reflective/decision/
failure/preference/goal/intent/skill/knowledge/...), `Modality` (text
through binary_object/embedding), `MemoryClass` (information through
instruction/policy, Step 78). `RuleBasedClassifier` (`classifier.py`)
assigns `SemanticType` from raw content; `classify_memory_class`
(`security.py`) detects instruction/policy-shaped content as a risk
signal, never a silent reclassification.

## 4. Provenance and Trust Model

`SourceType` (user statement, agent observation, document, tool,
inferred, reflection, external system). `TrustLevel` (Level 0
unverified through Level 5 validated skill) and `can_promote()` (Step
79): one level at a time, gated on the evidence that level actually
requires, proven against the plan's own "don't let an LLM jump Level 0
to Level 5" example. `test_security.py`.

## 5. Bitemporal Model

`event_time`/`knowledge_time` (Step 56) as named accessors over
`valid_from`/`observed_at`, not duplicate storage. `valid_now()`,
`changed_between()`, `previous_state()` (`retrieval.py`'s
`TemporalRetriever`). `test_bitemporal.py`, `test_temporal_queries.py`.

## 6. Lifecycle and Supersession

`LifecycleState` (observed through forgotten). `mark_superseded()`
links a replacement to what it replaced on both sides in one operation
(Step 35) — never a silent disappearance. `ConflictResolver` (Step 58)
turns a clear time-ordered contradiction into a state transition;
`resolve_uncertain()` gives "I don't know" a first-class,
normalized-probability result rather than a forced pick.
`test_conflict.py`.

## 7. LLM Provider Interface Specification

`memory_os/providers.py`'s `LLMProvider` Protocol (`extract`/`reflect`/
`summarize`/...). `adapters/claude_provider.py` is the first
implementation — mocked-SDK tested (`test_claude_provider.py`), never a
live network call in the suite; raises on unparseable model output
rather than fabricating a result (`test_hallucination_resistance`).

## 8. Storage Adapter Interface Specification

`memory_os/storage.py`'s `StorageAdapter` Protocol
(`store`/`get`/`update`/`delete`/`search`/`list_all`).
`adapters/sqlite_adapter.py` (dev-only, FTS5 keyword search) and
`adapters/postgres_adapter.py` (production baseline: pgvector cosine
search, hybrid full-text+vector fusion in one query, Row-Level Security
enforced at the database layer, persisted relationship edges).

## 9. Adapter Conformance and Certification

`core/conformance/storage_adapter.py` (Step 99): closes the plan's own
named gap ("no adapter certification or versioning contract"). Any
`StorageAdapter` proves itself compatible by passing
`CONFORMANCE_CHECKS` against a factory; `test_adapter_conformance.py`
runs it against both real adapters this codebase ships, plus a positive
control (a deliberately broken adapter fails certification, proving the
suite can actually catch a real violation). See
`docs/ADAPTER_ECOSYSTEM.md` for the full seven-category catalog and
what's honestly out of scope.

## 10. Retrieval Architecture

`retrieval.py`'s `RetrievalEngine`: `KeywordRetriever`,
`VectorRetriever`, `TemporalRetriever`, `RelationshipRetriever`, fused by
score-sum with `matched_by` tracking which retriever(s) found each
result (Step 45/64). "No individual retrieval technology is treated as
universally superior" (the plan's own words) is true of the default
fusion call, not an opt-in a caller has to request.

## 11. Vector and Hybrid Search

Dev path: `embedding.py`'s dependency-free `HashingEmbedder` plus
`VectorRetriever`'s brute-force cosine loop — provable without a model
download. Production path: `postgres_adapter.py`'s `vector_search()`
(real pgvector `<=>` ranking) and `hybrid_search()` (one SQL statement
combining `ts_rank_cd` and cosine similarity, Steps 87-88).

## 12. Context Engine Specification

`context_engine.py`: ranked retrieval results into a token-budgeted,
routed context package (Step 46). `test_context_engine.py`.

## 13. Memory Compression Specification

`compression.py`: `deduplicate()`, `drop_stale_or_low_confidence()`,
`MemoryCompressor` — honestly falls back to non-summarizing compression
when no `LLMProvider` is supplied rather than pretending to summarize.
`test_compression.py`.

## 14. Reflection and Consolidation

`reflection.py`'s `build_reflection()`: structurally cannot start as a
confirmed fact (`CANDIDATE`/`UNCERTAIN` only, Step 48) — the same
discipline `learning.py`'s `promote_reflection_to_candidate_procedure()`
and `ProcedureValidator` extend through the full pattern-to-validated-
skill chain (Steps 71-74), including Rule E: a skill cannot become
trusted merely because an LLM generated it (`build_skill()` raises
unless the source procedure is already `VALIDATED`).

## 15. Relationship Graph and Lineage

`relationships.py`'s `RelationshipGraph`: typed edges
(`derived_from`/`supports`/`contradicts`/...), `lineage()` (cycle-safe,
answers "why does the system believe this" back to original evidence,
Step 54), `dependencies()` (the narrower belief-maintenance subset, Step
55). Persisted, not just in-memory, via `postgres_adapter.py`'s
`sync_relationship_graph()`/`load_relationship_graph()` (Step 89) —
`RelationshipGraph` itself stays storage-agnostic; the adapter is the
persistence layer underneath it.

## 16. Conflict Resolution and Uncertainty

Covered under Section 6; called out separately because Step 58/59 are
their own planned unit. `apply_correction()`: "that's wrong" as an
Old→Correction→New chain on the same supersession machinery as
everything else, not a special case.

## 17. Retrieval Planning and Query Decomposition

`planning.py`: `RetrievalPlanner` (question → intent → entities → plan),
`QueryDecomposer` (compound requests split into independently-classified
sub-questions), `GraphExpander` (depth- and size-limited on purpose —
unbounded traversal turns memory into an archaeological dig, the plan's
own words), a rule-based intent→retriever strategy table (Step 65,
explicitly not the learned adaptation the plan itself defers to
"eventually").

## 18. Access Control and Ownership

`access_control.py`'s `AccessPolicy` (Step 66-69): owner has full
access unconditionally, anyone else needs an explicit grant or the `"*"`
wildcard, `ADMIN` implies every other permission. `share_to_scope()`:
an agent contributing a private memory upward as a new, lineage-tracked
copy, never a mutation. `most_specific()`: Step 70's "the most specific
valid memory should generally win" precedence rule.

## 19. Multi-Tenancy and Isolation

Application layer: `tenant_id` on every memory, `can_access_tenant()`,
enforced in `RetrievalEngine.retrieve()` before `principal_id`'s
finer-grained check — a tenant boundary, not a permission (Step 81).
Database layer: `postgres_adapter.py`'s `tenant_isolation` RLS policy,
`FORCE ROW LEVEL SECURITY` (the one real gotcha this closed — table
owners are exempt from their own table's RLS by default), proven by a
raw query that bypasses the adapter's own Python code entirely and is
still blocked (Step 82, `docs/POSTGRES_RLS.md`).

## 20. Privacy Classification

`models.py`'s `PrivacyLevel` (public through secret) and
`PrivacyCategory` (personal/financial/security/credential/proprietary/
industrial) — a memory carries both a level and zero or more domain
tags (Step 83). Verified against the plan's own worked example: a
stated preference is public with no category; a database credential is
secret plus credential.

## 21. Learning Loop

Covered in Section 14; the full chain — EVENT → EPISODE → PATTERN →
REFLECTION → PROCEDURE → VALIDATED SKILL — is walked end to end in
`test_v0_5_milestone.py`, checking all seven properties Step 75 names
(provenance, confidence, temporal validity, relationships, permissions,
scope, evidence) on the result, including a real private-to-shared
governance step.

## 22. Security: Threat Model and Poisoning Defense

`docs/THREAT_MODEL.md` (Step 76): the plan's own who-can-do-what
questions answered against the actual code, updated at every phase that
changes an answer — most recently Phase 19's API/MCP closure.
`PoisoningGuard` (Step 77): flags the plan's own worked example (an
untrusted document carrying an imperative instruction) as high risk;
identical content from a user statement is not — content alone isn't
the whole signal, source matters.

## 23. Policy Engine Specification

`security.py`'s `PolicyEngine` (Step 80): one place that answers every
store/retrieve/share/reason/instruct/export/delete question through
deterministic logic and `AccessPolicy`, never by calling an LLM — "that
separation is non-negotiable" in the plan's own words. Wired
non-optionally into the REST API and MCP server (Steps 96/98); still
optional for a caller embedding the engine directly, a real, named,
unclosed gap (see `THREAT_MODEL.md`'s open-items list).

## 24. Audit Trail Specification

`audit.py`'s `AuditLog`/`AuditEntry` (Step 84): who/what/when/why/
source/result on every logged operation, including denials.
`PolicyEngine`'s optional `audit_log` parameter logs every `can_*`
decision when supplied — opt-in, matching every other cross-cutting
concern in this codebase (telemetry, encryption).

## 25. Encryption Specification

`encryption.py`'s `Encryptor` Protocol; `adapters/fernet_adapter.py`'s
`FernetEncryptor` (Step 85) — built on `cryptography.fernet`
(authenticated AES + HMAC), never a custom cipher, per the plan's own
explicit instruction. Not auto-wired into storage: per-field encryption
is a caller's decision about which fields need it.

## 26. Object/File Memory Specification

`object_store.py`'s `ObjectStore` Protocol; `adapters/
filesystem_object_store.py` (Step 90), content-addressed by sha256 —
storing identical bytes twice is a no-op. `MemoryObject.object_ref`
(additive field) is where a `Modality.FILES`/`BINARY_OBJECT` memory
points to its actual bytes; `content` stays a human-readable caption.

## 27. Observability Specification

`telemetry.py`'s `Telemetry` Protocol; `adapters/otel_adapter.py`'s
`OTelTelemetry` (Step 91) — kept behind the same core-vs-adapter wall as
every other vendor library, no carve-out even for one designed to be a
neutral abstraction. `metrics.py` (Step 92): `recall_at_k`,
`precision_at_k`, `mean_reciprocal_rank`, `contradiction_rate`,
`staleness_rate`, `provenance_coverage` as real numbers.
`core/memory_evals/` (Step 93): a benchmark repo running the real
engine end to end, `python3 -m memory_evals` prints the numbers — "here
are the numbers," not "I think it works," the plan's own framing for
this whole phase.

## 28. Reliability Specification

`reliability.py`'s `FailureInjectingStorageAdapter` (Step 94): wraps any
`StorageAdapter`, fails on command, proves a failed call never partially
reaches the real store and that `RetrievalEngine` propagates a real
outage rather than swallowing it. `backup.py`'s export/import functions
plus `adapters/file_backup.py` (Step 95): a real test round-trips a
backup from `SQLiteAdapter`, through a file on disk, into
`PostgresAdapter` — a genuinely different storage technology, memories
and relationships both intact.

## 29. REST API Specification

`core/api/app.py` (Step 96): FastAPI, OpenAPI schema auto-served at
`/openapi.json`. `api/auth.py`'s per-key `Principal` (principal_id +
tenant_id) resolved before any route body runs; `api/rate_limit.py`'s
per-principal fixed-window limiter; `PolicyEngine` consulted
non-optionally on every memory-touching route, denying as 404 (never
403 — a denied memory and a missing one must look identical from the
outside).

## 30. Python SDK Specification

`core/sdk/client.py`'s `MemoryOSClient` (Step 97): synchronous, `httpx`-
based, matching every other client in this codebase. Tested against a
real live `uvicorn` server on an ephemeral port
(`tests/conftest.py`'s `live_api_server` fixture) — a real network
round trip, not an in-process shortcut.

## 31. MCP Integration Specification

`core/mcp_server/server.py` (Step 98): `remember`/`recall`/`forget` as
real MCP tools, calling directly into the same engine `api/` uses —
not proxied through the REST API, since an MCP server is itself a
process embedding the engine. Same `PolicyEngine` gate as the REST
layer; a denied `remember` raises `ToolError`, a cross-tenant `forget`
returns `False`, both proven in `test_mcp_server.py`.

## 32. Client Integration Guide

Three ways to reach the engine, in order of how much a client trusts:

1. **Embed it directly** (Python only): construct a `StorageAdapter` and
   call `RetrievalEngine`/`PolicyEngine` yourself. Fastest, and the one
   path where `PolicyEngine` is *not* automatically enforced — Section
   23's named gap. For trusted, in-process code only.
2. **The Python SDK** (`core/sdk`): `MemoryOSClient(base_url, api_key)`.
   Auth, rate limiting, and policy enforcement all apply, the same as
   any other REST caller.
3. **REST directly, or MCP** (any language): `core/api`'s OpenAPI schema
   is the contract for any HTTP client; `core/mcp_server` is the
   contract for any MCP-compatible one.

**This repository's own existing Skill (`SKILL.md` + `server/`) has not
been migrated onto any of these three paths.** It is a separate, live
product with its own bespoke `MEMORY.md` persistence — the plan's own
words describe it as becoming "the first client adapter" over MCP, and
that migration is real, well-specified, buildable work. It is
deliberately not done as part of this freeze: it changes behavior for
whatever is using that Skill today, and that is the kind of call this
project's own standing practice treats as the user's to make, not
something to fold silently into a documentation phase. See
`docs/ADAPTER_ECOSYSTEM.md`'s "Agent / client framework" section.

---

## What V1 explicitly does not include

Named, not hidden — the same eight items
`docs/UNIVERSAL_MEMORY_OS_PLAN.md`'s own gap list already flagged,
carried forward here as the freeze's own record of what's V2:

1. ~~**No adaptive configuration profiles**~~ **Closed at 1.1.0** (Phase
   21, `docs/ADAPTIVE_PROFILES.md`): `TenantProfile` (industry/
   application-type/business-type) now maps to default policy bundles,
   `tags`-based taxonomy extension, and retention rules, at
   tenant-registration time. Left in place as the historical record of
   this being V1's own highest-priority named gap.
2. **No named compliance target** (SOC 2 / HIPAA / GDPR / ISO 27001).
3. **No metering or cost-attribution model** per tenant/project.
4. **No schema migration tooling** (Alembic or equivalent) for a live
   Postgres deployment with real tenants.
5. **No decay function defined** — Step 5 names `Decay` as a dimension;
   no step specifies how importance/confidence actually erodes over
   time, per memory type.
6. **No retrieval-time prompt-injection red-teaming** — Step 77 covers
   write-time poisoning; a legitimately-trusted stored memory crafted to
   hijack retrieval-time reasoning is a distinct, untested surface.
7. **No data residency / DPA story.**
8. **Adapter certification is closed for StorageAdapter (Section 9);
   versioning is not** — no Protocol in this codebase carries a version
   number or a compatibility policy for when its shape changes.

Freezing V1 means deciding these are out, not forgetting to decide.
