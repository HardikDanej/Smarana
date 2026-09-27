# Universal Memory OS — Development Architecture

Consolidated from the 100-step development program (`Smaraṇa_1-25.md` through `Smaraṇa_76-100.md`) into one buildable roadmap.

## Recommendation

Build this as a new repository, `universal-memory-os`, separate from the current `smriti`/Smaraṇa repo. Do not try to grow it inside the existing codebase.

The existing repo is a Claude-Projects Skill: a Markdown orchestrator (`SKILL.md`) plus a single-file `MEMORY.md` persisted through an MCP server built for one client (claude.ai Connectors). The system described in these four files is a database-backed, multi-tenant, model-agnostic memory platform with a Postgres/pgvector core, a policy engine, and adapters for any LLM, agent framework, or application. These are not the same codebase at two different maturity levels. They are two different products that happen to share a name and a domain.

Forcing the second into the first means every core decision (storage, multi-tenancy, security) fights the Skill-file format the first was built around. Keep them separate and connect them on purpose:

- **Smaraṇa** stays the brand for the whole platform.
- **`universal-memory-os`** becomes the core engine — the Memory OS itself, vendor-neutral, no Claude-specific code in `core/`.
- The current repo's `SKILL.md` + `server/` becomes the **first client adapter**: a thin Claude-Projects integration that talks to the new engine over MCP (Step 98), the same way an OpenAI adapter or a LangGraph adapter would. Nothing in it is deleted; it is repositioned as one adapter among many, not the architecture.

This is a scope decision with real cost (new repo, new CI, a migration path for existing `MEMORY.md` files), so I have not created the repository — say the word and I'll scaffold Step 26 for real. Everything below assumes this split.

---

## 1. Constitution (Step 1-2)

Non-negotiable properties, checked against every future design decision:

Model agnostic · Agent agnostic · Framework agnostic · Database agnostic · Storage agnostic · OS agnostic · Cloud agnostic · Multi-agent compatible · Multimodal capable · Temporal · Auditable · Permission-aware · Extensible · Testable · Replaceable · Self-hostable.

**No vendor is ever part of the core architecture.** Claude, OpenAI, Gemini, a robot controller, a WordPress agent — all clients. Mem0, Graphiti — at most adapters. None of them are the Memory OS.

The problem set this solves (Step 2) — remember something/why/when/how, remember a relationship, a process, a decision, a failure, a preference, a skill, what changed, what is no longer true, what should be forgotten — is the acceptance criteria for "done." A system that only does semantic search over text has not built this.

## 2. Memory Taxonomy and Object Model (Steps 3-10, 31-35)

```
Memory OS
├── Memory Semantics       (what kind of thing: episodic, semantic, procedural,
│                           reflective, decision, failure, preference, goal,
│                           skill, knowledge, conversation, environmental, system)
├── Memory Scope           (session → conversation → task → agent → user →
│                           team → project → organization → global)
├── Memory Dimensions      (temporal, relational, confidence, importance,
│                           freshness, reliability, evidence, uncertainty,
│                           contradiction, sensitivity, decay, priority)
├── Memory Representation  (structured / vector / graph / object)
├── Memory Lifecycle       (state machine, below)
├── Memory Operations      (remember, recall, search, related, timeline,
│                           explain, update, confirm, correct, supersede,
│                           archive, forget, reflect, consolidate, learn)
├── Memory Intelligence    (extraction, classification, reflection, learning)
├── Memory Governance      (security, privacy, permissions, audit)
├── Memory Retrieval       (keyword, vector, graph, temporal, fusion)
└── Memory Infrastructure  (adapters, storage, observability)
```

The **Universal Memory Object** is the single envelope every memory type shares:

```
MemoryObject {
  id, content, semantic_type, scope, modality
  entities, relationships
  created_at, observed_at, valid_from, valid_until      # bitemporal (Step 56)
  confidence, importance, reliability                     # never conflated with truth (Step 34)
  source, provenance, evidence
  permissions, sensitivity
  version, lifecycle_state
  supersedes, superseded_by
  metadata
}
```

Lifecycle (Step 11): `Observed → Candidate → Validated → Stored → Confirmed → Consolidated → Updated → Superseded → Archived → Forgotten`. Not every memory traverses every state — this is a state machine, not a pipeline everything must complete.

**Event ≠ Memory** (Step 30). Every event that enters the system is raw material; formation decides what's worth keeping. 100,000 tool events becoming 2,000 memories is the system working correctly, not data loss.

## 3. Architecture: Core vs. Adapter (Steps 27-28)

```
                   CLIENT SYSTEM
                         │
          ┌──────────────┼──────────────┐
         LLM           AGENT        APPLICATION
          │              │              │
          └──────────────┼──────────────┘
                         │
                  MEMORY API                 ← REST/OpenAPI, MCP, SDK (Steps 96-98)
                         │
                  MEMORY ENGINE               ← the core; never imports an adapter directly
       ┌─────────────────┼─────────────────┐
   Formation         Retrieval         Lifecycle
       └─────────────────┼─────────────────┘
                  REPRESENTATION
       ┌─────────────────┼─────────────────┐
    Structured         Vector            Graph
                         │
                     STORAGE
```

Rule: `Core → Interface → Adapter → External technology`. The core never imports `psycopg`, `anthropic`, `neo4j`, or any concrete library. It imports its own interfaces (`LLMProvider`, `StorageAdapter`, `AgentAdapter`); adapters implement them. This is what makes "replace Postgres" or "swap Claude for a local model" a config change, not a rewrite.

## 4. Build Roadmap — 20 Phases, 100 Steps

| Phase | Steps | Deliverable | Exit criteria |
|---|---|---|---|
| A. Product definition | 1-10 | Constitution, problem definition, taxonomy, dimensions, scope, modality, Memory Object spec, storage-adapter interface | Zero code. Documents only. |
| B. Memory behavior | 11-18 | Lifecycle state machine, formation pipeline, consolidation, reflection, proceduralization, skill formation, decision memory, failure memory | Zero code. Documents only. |
| C. Universal retrieval (design) | 19-22 | Retrieval intent taxonomy, retrieval planner spec, fusion scoring, Context Engine spec | Zero code. Documents only. |
| D. Universality (design) | 23-25 | Universal Memory API surface, provider/agent/storage adapter layer, v0.0.1 prototype spec | `memory.observe()` / `memory.recall()` contract frozen on paper |
| 5. Real system bootstrap | 26-30 | `universal-memory-os/` repo, layered architecture, Core-vs-Adapter rule enforced, internal `MemoryEvent` system, event≠memory boundary | Repo exists, one understandable Python project, no microservices |
| 6. Memory Engine core | 31-35 | `MemoryObject` (Pydantic), IDs + versioning, provenance, confidence ≠ truth, contradiction handling | Deterministic data layer works with **no LLM connected** |
| 7. Basic intelligence | 36-40 | Rule-based classifier, `LLMProvider` interface, first Claude adapter, extraction pipeline, entity resolution | Classifier + extraction run without any specific vendor hardcoded |
| 8. Real retrieval | 41-45 | Keyword (SQLite FTS) baseline, vector adapter (optional), temporal retrieval, relationship retrieval, fusion | Local, free baseline works before any paid API is required |
| 9. Memory intelligence | 46-50 | Context Engine, memory compression, reflection, evaluation framework, **Memory OS v0.1** | First milestone: full observe→store→recall→context cycle, benchmarked |
| 10. Coexisting memory types | 51-55 | Coexistence matrix, memory relationships (evidence graph), coexistence rules, lineage, dependency graph | Single event → multiple memory types, all traceable to source |
| 11. Temporal + conflict intelligence | 56-60 | Bitemporal model, temporal queries, conflict resolver, uncertainty handling, correction chains | System can answer "what did we believe in February" without rewriting history |
| 12. Advanced retrieval | 61-65 | Retrieval planner, query decomposition, controlled graph expansion, hybrid retrieval, adaptive strategy selection | Retrieval plan, not just a memory-type classifier |
| 13. Agent memory | 66-70 | Private agent memory, shared memory, ownership, permissions (READ/WRITE/SHARE/etc.), scope inheritance | Agent A cannot read Agent B's private memory by default |
| 14. Learning from experience | 71-75 | Pattern detection, reflection→procedure, procedure validation, skill memory, **Memory OS v0.5** | Second milestone: multi-agent learning prototype with governance |
| 15. Security and memory risk | 76-80 | Threat model, memory-poisoning defenses, instruction/memory separation, trust ladder (Level 0-5), Policy Engine | No external content becomes trusted memory automatically |
| 16. Identity, privacy, multi-tenancy | 81-85 | Tenant isolation (org→workspace→project→user→agent→task), Postgres Row-Level Security, privacy classes, audit trails, encryption strategy | A query can never "accidentally" cross tenants |
| 17. Production infrastructure | 86-90 | Postgres migration, pgvector, hybrid full-text+vector search, graph adapter, object/file memory | SQLite stays dev-only; Postgres+pgvector is the production baseline |
| 18. Observability and reliability | 91-95 | OpenTelemetry instrumentation, memory-specific metrics (Recall@K, contradiction rate, etc.), `memory-evals/` benchmark repo, failure injection, backup/recovery | "Here are the numbers," not "I think it works" |
| 19. Universal interoperability | 96-98 | REST/OpenAPI (FastAPI), Python SDK, MCP integration | Any language, any MCP-compatible app, can reach the OS |
| 20. Industrialization | 99-100 | Full adapter ecosystem (LLM/agent/app/storage/protocol/industrial/OS), **frozen V1 architecture package** (32 numbered specs) | V1 architecture package published; nothing ships against a moving target |

## 5. Security and Governance Overlay (Steps 76-85)

This runs alongside every phase from Phase 15 onward, not after it:

- **Threat model** (Step 76): who can write/read/modify/delete/share/infer memory, and every attack surface (user, agent, LLM, tool, document, API, external system, plugin, adapter, database).
- **Poisoning defense** (Step 77): `Input → Candidate memory → Risk analysis → Evidence validation → Policy → Memory`. No external document auto-promotes to trusted memory.
- **Instructions ≠ memories** (Step 78): memory is classified as `INFORMATION / EVIDENCE / HISTORY / PREFERENCE / PROCEDURE / INSTRUCTION / POLICY`. Retrieved memory does not silently become an executable command.
- **Trust ladder** (Step 79): Level 0 (unverified observation) through Level 5 (validated skill). No LLM promotes Level 0 straight to Level 5; promotion requires evidence.
- **Policy Engine** (Step 80): a component separate from the LLM that gates store/retrieve/share/reason/instruct/act/export/delete. This separation is architectural, not a prompt instruction.
- **Tenant isolation** (Step 81-82): `tenant_id`/`organization_id`/`project_id`/`owner_id`/`agent_id`/`scope` on every memory, enforced at both the application layer and the database layer (Postgres RLS) — never application code alone.
- **Privacy classes** (Step 83): `PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED/SECRET`, plus `PERSONAL/FINANCIAL/SECURITY/CREDENTIAL/PROPRIETARY/INDUSTRIAL`.
- **Audit trails** (Step 84): every operation logs who/what/when/why/source/result, including denials.
- **Encryption** (Step 85): at rest, in transit, key management, per-tenant and per-field — built on established libraries, never custom cryptography.

## 6. The Learning Loop (Steps 14-18, 71-75)

```
EVENT → EPISODE → PATTERN → REFLECTION → PROCEDURE → VALIDATED SKILL
```

Every step up this ladder carries `evidence_count`, `confidence`, `exceptions`, `scope` — never promoted to fact by narrative plausibility alone. A skill is a structured, validated capability object (preconditions, procedure, tools, success rate, known failures, last validation) — explicitly **not** a prompt, a memory snippet, or "an LLM said something clever."

## 7. Retrieval Stack (Steps 19-22, 41-45, 61-65)

```
QUERY → Intent analysis → Entities → Time constraints → Required evidence → Retrieval plan
              │
   ┌──────────┼──────────┬────────────┐
Keyword     Vector      Graph      Temporal
   └──────────┼──────────┴────────────┘
              ↓
      Conflict resolution
              ↓
         Reranking / Fusion
              ↓
         Context Engine  ── token budget, model capability, priority, recency,
              ↓             confidence, contradiction, redundancy
      LLM / Agent / Application
```

No retrieval technology is treated as universally superior. Graph expansion is depth-limited and relevance-thresholded on purpose — unbounded traversal turns "memory" into an archaeological dig.

## 8. Technology Stack (v1, per Step 100)

| Layer | Choice |
|---|---|
| Core language | Python |
| Data models | Pydantic |
| API | FastAPI |
| API protocol | HTTP + JSON |
| API spec | OpenAPI |
| Dev database | SQLite |
| Production database | PostgreSQL |
| Vector | pgvector |
| Graph | Adapter, later |
| Object storage | Adapter, later |
| LLM interface | Custom provider interface |
| First LLM adapter | Claude |
| Agent interface | Custom provider interface |
| Interoperability | MCP |
| Testing | Pytest |
| Containers | Docker |
| Observability | OpenTelemetry |
| Version control | Git/GitHub |
| Documentation | Markdown + OpenAPI |

## 9. Milestones

- **v0.1** (Step 50): full observe → store → recall → context cycle, evaluated against a benchmark, no multi-agent or governance yet.
- **v0.5** (Step 75): multi-agent learning prototype — formation, retrieval, and learning running together, with private/shared/inherited memory governance.
- **V1 architecture freeze** (Step 100): a 32-document specification package (Constitution through Client Integration Guide), REST + MCP + SDK all live, full adapter ecosystem defined.

---

## What's not in these four files — and needs a decision from you

You asked me to flag gaps. These aren't nitpicks; they're places where the 100 steps describe *mechanism* but leave the *policy* for your specific goal — a platform that adapts to use case, application type, and business type — undefined.

1. **There is no first-class "adaptive profile" concept.** The files give you extensible taxonomy and scope, but nothing that says "this tenant is a healthcare app, so default privacy classes/retention/redaction rules are X; this tenant is an e-commerce store, so they're Y." Without this, "adapts to the environment of the user's use case, application type, and business type" stays a marketing sentence, not an architecture. I'd add it as **Phase 21: Adaptive Configuration Profiles** — a profile object (`industry`, `application_type`, `business_type`) that maps to default policy bundles, taxonomy extensions, and retention rules at tenant-creation time. This is the single biggest thing worth adding before you freeze V1.

2. **No compliance target is named.** Steps 76-85 build real security mechanism (RLS, encryption, audit, trust levels) but never say which regime you're building toward — SOC 2, HIPAA, GDPR, ISO 27001. Each implies different hard requirements (breach-notification timelines, right-to-erasure semantics, data residency, BAAs for healthcare). "Most secure system" isn't a spec until you pick a target; pick one now, because it changes the storage and audit design, not just a checklist added later.

3. **No metering or cost-attribution model.** A multi-tenant platform serving different business types needs to know, per tenant, per project: storage growth, retrieval volume, LLM token cost, embedding cost. Step 92 has system metrics (latency, throughput, cost) but nothing per-tenant, and nothing about how you'd price or rate-limit a customer. Needed before this is commercially real.

4. **No schema migration tooling named.** Step 33's `schema_version const` bump strategy works for a single Markdown file; a production Postgres system with live tenants needs an actual migration framework (e.g., Alembic) and a documented backward-compatibility contract, not just "bump the const."

5. **Decay is named, never defined.** Step 5 lists `Decay` as a memory dimension; no step ever specifies the actual decay function (how importance/confidence erodes over time, per memory type). This will matter as soon as v0.1 runs long enough to need it.

6. **No prompt-injection-specific red-teaming.** Step 77 covers memory poisoning at write time, but retrieval is a second injection surface: a stored (legitimately trusted) memory that later gets crafted to manipulate an LLM's behavior when retrieved into context. Step 94's failure injection list should explicitly include "adversarial memory content designed to hijack retrieval-time reasoning," not just corrupted/stale/wrong memory.

7. **No data residency / DPA story.** Multi-tenant across business types eventually means enterprise customers asking "is my data in the EU," and needing a signed data processing agreement. Worth a one-line stance now (even "V1 is single-region, DPA support is V2") so it's a decision, not a surprise.

8. **No adapter certification or versioning contract.** Step 99 defines a large adapter ecosystem (LLM, agent, storage, protocol, industrial, OS) but nothing about how a third-party adapter gets certified compatible, or what happens when the core's interface version bumps. Matters the moment anyone outside your team writes an adapter.

Item 1 is the one I'd resolve before writing any more spec — it's the actual product differentiator you named, and right now the source material treats it as an afterthought of "extensibility" rather than a designed feature.
