# core/ — Universal Memory OS Engine

This is the vendor-neutral memory engine described in
`docs/UNIVERSAL_MEMORY_OS_PLAN.md`. It is a separate product from the
Skill/`server/` at the repo root (the Claude-Projects integration), kept in
this same repository but in its own namespace so the two never collide:

- `SKILL.md`, `server/`, `workflows/`, the root `schemas/` and `tests/` —
  the existing Smaraṇa Skill, a Claude-Projects-specific client.
- `core/` — the engine itself. No Claude-specific code lives here. The
  Skill above will eventually become one adapter that talks to this engine
  over MCP (Plan Step 98), not the other way around.

## Status

**V1 architecture frozen at 1.0.0, Adaptive Configuration Profiles added
at 1.1.0, GDPR named as the compliance target at 1.2.0**
(`memory_os.__version__`). All 20 phases of the 100-step plan
(Steps 31-100) plus Phases 21-22 are built, tested, and gated —
`GATES.md` (37/37 met), 359/359 tests passing, both isolation gates (no
LLM/network/vendor dependency in `core/memory_os`; `core/memory_os`
never imports `core/adapters`) holding after every single addition since
Phase 6.

**Read `docs/V1_ARCHITECTURE.md` first** — the 32-section specification
package the freeze produced (Constitution through Client Integration
Guide), grounded in the real files and tests below, honest about what's
explicitly deferred to V2 rather than silently dropped. Then
`docs/ADAPTIVE_PROFILES.md` (Phase 21, not one of the plan's original
100 steps): `TenantProfile` maps industry/application-type/business-type
to default policy bundles, tag-based taxonomy extension, and retention
rules — closing V1's own highest-priority named gap without reopening
the freeze. Then `docs/GDPR_COMPLIANCE.md` (Phase 22): GDPR named as the
compliance target, with a real article-by-article mapping of what's
built (`data_subject_rights.py`'s Articles 15/17/20, `TenantProfile`'s
recorded-not-enforced data residency) against what stays organizational
or legal, honestly, rather than claimed as solved by code. Three earlier
milestones still hold underneath all of it: **v0.1** (Step 50, the full
observe→store→recall→context cycle, `tests/test_v0_1_milestone.py`),
**v0.5** (Step 75, the multi-agent learning prototype,
`tests/test_v0_5_milestone.py`), and Phase 17's production infrastructure
(a real Postgres+pgvector backend, not just SQLite).

`core/adapters/` (plus `core/api`, `core/sdk`, and `core/mcp_server`,
which depend on the engine but never the reverse) is the only place any
vendor or storage technology is imported — enforced by repeated
isolation gates, not just convention, checked again at every phase
through this final one.

## Layout

```
core/
├── memory_os/              # the package -- vendor-free, storage-free
│   ├── models.py           # MemoryObject, enums, versioning, supersession, bitemporal accessors
│   ├── classifier.py       # rule-based semantic-type classifier
│   ├── providers.py        # LLMProvider interface
│   ├── extraction.py       # text -> MemoryObject pipeline
│   ├── entity_resolution.py
│   ├── storage.py          # StorageAdapter interface
│   ├── embedding.py        # Embedder interface + HashingEmbedder
│   ├── retrieval.py        # Keyword/Vector/Temporal/Relationship + hybrid fusion
│   ├── context_engine.py   # ranked results -> usable context package
│   ├── compression.py      # dedup, stale/low-confidence removal
│   ├── reflection.py       # episodes -> a structurally-uncertain reflection
│   ├── relationships.py    # typed evidence graph, lineage, belief maintenance
│   ├── conflict.py         # state-transition resolver, uncertainty, corrections
│   ├── planning.py         # RetrievalPlanner, QueryDecomposer, GraphExpander, strategy table
│   ├── access_control.py   # ownership, permissions, sharing, scope precedence, tenant isolation
│   ├── learning.py         # PatternDetector, procedure validation, Skill Memory
│   ├── security.py         # PoisoningGuard, trust ladder, PolicyEngine
│   ├── audit.py            # AuditLog/AuditEntry (who/what/when/why/source/result)
│   ├── encryption.py       # Encryptor interface
│   ├── object_store.py     # ObjectStore interface (binary/file memory)
│   ├── telemetry.py        # Telemetry interface (spans + metrics)
│   ├── metrics.py          # recall_at_k, precision_at_k, MRR, contradiction/staleness rate, provenance coverage
│   ├── reliability.py       # FailureInjectingStorageAdapter
│   ├── backup.py           # export/import over StorageAdapter + RelationshipGraph
│   ├── profiles.py         # Phase 21: TenantProfile, PolicyDefaults, RetentionPolicy, TenantProfileStore
│   ├── retention.py        # Phase 21: sweep_expired_memories() -- marks aged-out memories FORGOTTEN
│   └── data_subject_rights.py  # Phase 22: find/export/erase_data_subject() -- GDPR Articles 15/17/20
├── adapters/                # the ONLY place vendor/storage tech is imported
│   ├── claude_provider.py
│   ├── sqlite_adapter.py
│   ├── fernet_adapter.py         # Encryptor, via cryptography.fernet
│   ├── postgres_adapter.py       # StorageAdapter + pgvector + hybrid search + relationship persistence, over real Postgres
│   ├── filesystem_object_store.py  # ObjectStore, content-addressed
│   ├── otel_adapter.py           # Telemetry, via opentelemetry-sdk
│   └── file_backup.py            # save_backup/load_backup to a JSON file on disk
├── memory_evals/            # Step 93 benchmark repo -- run: PYTHONPATH=. python3 -m memory_evals
│   ├── scenarios.py         # named ground-truth retrieval scenarios
│   └── runner.py            # runs the real engine end to end, reports metrics.py's numbers
├── api/                     # Step 96: REST/OpenAPI over the engine (FastAPI)
│   ├── app.py                # create_app() -- auth + rate limit + PolicyEngine enforced on every route
│   ├── auth.py                # APIKeyStore, Principal (principal_id + tenant_id)
│   ├── rate_limit.py           # per-principal fixed-window RateLimiter
│   └── schemas.py              # request/response DTOs
├── sdk/                      # Step 97: synchronous Python client for api/ (httpx)
├── mcp_server/               # Step 98: remember/recall/forget as MCP tools, straight into the engine
├── conformance/              # Step 99: adapter certification suites (storage_adapter.py)
├── tests/                   # pytest; intelligence-layer tests use fakes/mocks, never live calls
├── scripts/                 # gate-check verification scripts (no-LLM-dep, adapter-isolation)
├── docs/                    # THREAT_MODEL.md, POSTGRES_RLS.md, POSTGRES_SETUP.md,
│                            # ADAPTER_ECOSYSTEM.md, V1_ARCHITECTURE.md (start here),
│                            # ADAPTIVE_PROFILES.md, GDPR_COMPLIANCE.md
├── GATES.md                 # unlazy verified-completion ledger, 37/37 met
├── requirements.txt
└── requirements-dev.txt
```

## Running the tests

```bash
pip install -r core/requirements.txt -r core/requirements-dev.txt
PYTHONPATH=core python -m pytest core/tests -v
```

Not committed until this reaches a working, efficient system — see the
standing instruction in this repo's development log; `GATES.md` in this
directory is the actual verification trail, not this README.
