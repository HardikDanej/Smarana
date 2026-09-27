# Adapter Ecosystem (Plan Step 99)

The plan names seven adapter categories: LLM, agent, application, storage,
protocol, industrial, OS. This document catalogs each honestly: what is
real and tested, what is a defined-but-unimplemented interface, and what
is out of scope for V1 because no concrete target system exists to build
against — the same discipline this project has applied since Phase 6
(`docs/THREAT_MODEL.md`, `docs/POSTGRES_RLS.md`): name a gap, never pad
around it.

## Certification: what "adapter" means here

Every category below follows the same shape: `core/memory_os` defines a
`Protocol` (structural typing, `@runtime_checkable`), and a concrete
adapter in `core/adapters` implements it. This is what the plan's own
gap list flagged as missing — "no adapter certification or versioning
contract... matters the moment anyone outside your team writes an
adapter" — and it is now closed for the one category with more than one
real implementation to prove it against:

`core/conformance/storage_adapter.py` is a runnable certification suite.
Any `StorageAdapter` — `SQLiteAdapter`, `PostgresAdapter`, or a third
party's — proves itself compatible by passing every check in
`CONFORMANCE_CHECKS` against a factory that builds a fresh instance:

```python
from conformance import certify
certify(lambda: MyNewAdapter(...))
```

`tests/test_adapter_conformance.py` runs this against both adapters this
codebase actually ships, proving they are behaviorally interchangeable,
not just structurally type-compatible. The same pattern generalizes to
any Protocol in this codebase (`Embedder`, `LLMProvider`, `Encryptor`,
`ObjectStore`, `Telemetry`) — `storage_adapter.py` is the one built out
because it is the one category with two real, independent
implementations to certify against each other; the others have exactly
one implementation each so far, which a conformance suite would only be
checking against itself.

**Versioning contract, honestly scoped:** none of this codebase's own
Protocols carry a version number, and there is no compatibility policy
for what happens when one changes shape. This is real, unclosed scope —
named here rather than assumed solved, matching gap #8 in
`docs/UNIVERSAL_MEMORY_OS_PLAN.md`'s own list. `core/memory_os.__version__`
(Step 100) versions the *engine as a whole*; per-interface versioning is
V2 work.

## The seven categories

### LLM — real, tested

`memory_os.providers.LLMProvider` (Phase 7). `adapters/claude_provider.py`
is the one implementation, mocked-SDK tested (`test_claude_provider.py`),
never a live network call in the test suite.

### Storage — real, tested, now certified

`memory_os.storage.StorageAdapter` (Phase 8/17). `adapters/sqlite_adapter.py`
(dev-only) and `adapters/postgres_adapter.py` (production baseline, pgvector
+ hybrid search + RLS) both certified by `conformance/storage_adapter.py`.

### Protocol / Interoperability — real, tested (Phase 19)

REST (`core/api`, FastAPI + OpenAPI), MCP (`core/mcp_server`), and a
Python SDK (`core/sdk`) over the REST surface. All three enforce auth,
rate limiting, and `PolicyEngine` non-optionally — see `THREAT_MODEL.md`'s
API row.

### Agent / client framework — real target named, not yet built

The plan's own words: "The current repo's `SKILL.md` + `server/` becomes
the first client adapter: a thin Claude-Projects integration that talks
to the new engine over MCP (Step 98), the same way an OpenAI adapter or
a LangGraph adapter would." That target exists in this same repository
today, running its own separate, bespoke, single-file `MEMORY.md`
persistence — a live, working, separate product, not a stub.

**This migration is deliberately not done as part of Steps 99-100.**
Rewiring `server/`'s MCP server (`server/server.py`) to call
`core/mcp_server` instead of its own `memory_index.py` changes real
behavior for whatever is using that Skill today. That is a scoped,
reversible-in-principle but user-visible change to a *separate existing
product* — exactly the kind of action this project's own standing
practice treats as the user's call, not something to fold silently into
a documentation-freeze phase. It is real, buildable, well-specified work
for whenever that decision is made; it is not done here.

A LangGraph/AutoGen/CrewAI-style adapter for a *different* agent
framework is a different question again: `core/sdk` (Step 97) is
already exactly what such an adapter would be built on (a synchronous
Python client, auth handled, tenant-scoped) — no new core interface is
needed for that case, only someone to write the specific integration
when a specific framework is targeted.

### Application — same shape as agent/client, no specific target named

The plan uses "application adapter" and "agent adapter" close enough to
synonymously that no additional interface is implied beyond what Step 97's
SDK and Step 96's REST API already provide. Any application reaches the
OS the same way the Skill migration above would: through the SDK, the
REST API directly, or MCP. Nothing further to build until a specific
application names itself.

### Industrial — deferred, no target system

No industrial system (SCADA, an MES, a PLC integration, anything) is
named anywhere in the four source planning documents beyond the single
word "industrial" in Step 99's own step description. Building a stub
adapter with no real system to conform to would be fabricated scope, not
architecture — exactly what this project's own discipline (real tests
against real infrastructure, Phases 17-19) exists to avoid. Deferred to
V2, to be scoped against an actual target once one exists.

### OS — deferred, no target named

Same reasoning as Industrial. "OS adapter" most plausibly means
something like local filesystem/native-notification integration for a
desktop-embedded deployment, but nothing in the source material commits
to a specific shape. Deferred to V2 for the same reason.
