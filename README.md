# Smaraṇa

> **स्मरण**, Sanskrit for *"remembrance, recollection, the act of remembering."* Where *śruti* is what is heard fresh in the moment, smaraṇa is the calling back to mind of what was retained.

This repository holds memory infrastructure for AI systems, built twice, for two different problems.

The first build is a Claude Projects Skill: a tier-aware pipeline that gives one Claude Project persistent, structured state across sessions, with nothing to install beyond pasting a few files in. It works today.

The second build is `core/`: a full memory operating system, vendor-neutral, storage-neutral, and model-agnostic, meant to sit underneath any LLM, any agent framework, any application. It has a REST API, an MCP server, a Python SDK, multi-tenant isolation enforced at the database layer, and a compliance mapping against GDPR. It is not a bigger version of the Skill. It is a different product that happens to share a name, a domain, and this repository.

Neither one is a demo. Both ship with real, automated test suites, and neither claims a number it can't show you.

## Two products, one name, no collision

The Skill and the engine never touch each other's code:

- `SKILL.md`, `server/`, `workflows/`, root `schemas/`, root `tests/`, `docs/project-setup-guide.md`: the Claude Projects Skill.
- `core/`: the engine. Nothing Claude-specific lives here, and nothing in `core/` imports from the Skill's files or vice versa.

`core/README.md` already names where this goes next: the Skill becomes the first client of the engine, talking to `core/mcp_server` over MCP instead of managing its own file, the same way any other agent framework would connect. That migration hasn't happened yet. It's real, scoped work for whenever it's decided on, not a background assumption.

## The Skill: memory for one Claude Project

Most attempts at giving Claude memory fail in one of two ways. Either everything gets remembered until the file is useless, or nothing gets remembered and every session starts from zero. The Skill avoids both with a 3-tier taxonomy, a deterministic 4-phase pipeline, and a hard cap that forces compression instead of unbounded growth.

Every memory operation runs the same state machine:

```
[Phase 1: Ingestion/Probe] → [Phase 2: Tier Resolution] → [Phase 3: Compression/GC] → [Phase 4: Persistence Handshake]
```

State sorts into three tiers, by volatility:

| Tier | Holds | Volatility |
|---|---|---|
| **1: Active Execution** | Current tasks, in-flight bugs, uncommitted state | High. Pruned every GC pass. |
| **2: System Architecture & Decisions** | Tech stack choices, ADRs, "why we built it this way" | Medium. Superseded, never silently deleted. |
| **3: Domain Rules & User Preferences** | Standing rules ("always X, never Y") | Low. Append-and-supersede only. |

The result persists to `MEMORY.md`, written through an MCP filesystem/memory server when one's connected, or as a Markdown artifact you paste into the Project's Knowledge when it isn't. The file caps at 120 lines / roughly 800 tokens. Anything that ages out collapses into a two-line changelog entry instead of disappearing.

A Tier 1 task can carry a **verified-completion gate**: a `check`/`expect` command pair adapted from the [`unlazy`](https://github.com/Leonxlnx/unlazy) skill's gate-contract pattern. A gated task only reaches `status: done` once that check has actually run and passed. A confident self-report isn't evidence, and the schema itself rejects a `done` task whose gate was never verified.

Connected through `server/`, the Skill also gets **semantic search over its own aged-out history**, an idea adapted from [`claude-mem`](https://github.com/thedotmack/claude-mem)'s hybrid retrieval approach. Superseded decisions and compressed changelog entries get indexed into a local, free vector store, so `search_memory` finds the right one by meaning instead of requiring the exact original wording.

Setup: [`docs/project-setup-guide.md`](docs/project-setup-guide.md). Status: 29/29 tests passing, version `2.4.0`. See [`tests/README.md`](tests/README.md) for what's covered and what isn't.

## The engine: `core/`

The Skill solves memory for one Claude Project. `core/` solves it for any application, any LLM, any storage backend, at the scale where tenants, compliance, and production infrastructure stop being optional.

It's built on one rule, enforced by an automated gate at every phase since the engine's sixth: `core/memory_os` imports no LLM library, no storage driver, no network client, nothing. Every concrete technology, Claude, Postgres, SQLite, Fernet encryption, OpenTelemetry, lives in `core/adapters` and nowhere else. Swap the storage backend, swap the model, swap the encryption library. The engine underneath doesn't change.

What's actually in it:

- A universal memory object with provenance, confidence kept separate from truth, bitemporal validity, and full version history, never overwritten in place.
- Retrieval that fuses keyword, vector, temporal, and relationship search, with no single method treated as authoritative.
- A policy engine that answers store, retrieve, share, and delete questions through deterministic logic, never by asking an LLM.
- Multi-tenant isolation enforced twice: once in application code, once as PostgreSQL row-level security, proven by a test that issues a raw SQL query bypassing the engine's own code and still gets blocked.
- A REST API and an MCP server, both requiring authentication and rate limiting, both consulting the policy engine on every request, denying a memory that exists but that the caller can't see with the same 404 as one that doesn't exist at all, because telling the difference is itself a leak.
- Adaptive Configuration Profiles: a tenant's industry sets default sensitivity, data retention, and privacy tagging, without hardcoding a single tenant's assumptions into the engine.
- A GDPR compliance mapping that says plainly which articles are handled by code and which ones aren't, because a breach-notification runbook was never going to be a Python function.

None of this is aspirational. `core/GATES.md` is the actual verification ledger: 37 gates, 37 met, each one a real command that either passes or doesn't. 359 tests pass, including integration tests against a live PostgreSQL instance and a live HTTP server, not mocks standing in for them. Two isolation gates get re-run after every single addition and have never once failed.

Start with [`core/docs/V1_ARCHITECTURE.md`](core/docs/V1_ARCHITECTURE.md): the frozen V1 specification, 32 sections, Constitution through Client Integration Guide, every claim pointing at the file or test that backs it. Then [`core/README.md`](core/README.md) for the full layout and how to run it yourself.

## Installation

**The Skill** (per Claude Project, no infrastructure): follow [`docs/project-setup-guide.md`](docs/project-setup-guide.md). Short version: paste the Custom Instructions block into your Project's settings, upload a seed `MEMORY.md` ([`examples/MEMORY.md`](examples/MEMORY.md) is a populated reference), and upload `SKILL.md`, `schemas/`, and `workflows/` as the Skill itself.

**The engine** (a real Python service): see [`instructions.md`](instructions.md) for the full walkthrough, including standing up PostgreSQL with pgvector for the production adapter. Short version:

```bash
pip install -r core/requirements.txt -r core/requirements-dev.txt
PYTHONPATH=core python -m pytest core/tests -v
```

## Development

```bash
pip install -r requirements-dev.txt      # the Skill's own tests
python -m unittest discover -s tests -v
```

```bash
pip install -r core/requirements-dev.txt # the engine's tests
PYTHONPATH=core python -m pytest core/tests -v
```

Both suites run in CI on every push and pull request against `main`. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml) for the full workflow.

## Non-negotiable rules

These hold across both products:

- Nothing is fabricated. No invented decisions, no invented tasks, no invented test results, no invented compliance claims.
- A gate that hasn't actually run doesn't count as passed. A confident report is not evidence.
- `core/memory_os` stays free of vendor and storage dependencies, checked by an automated gate, not by convention.
- Additive schema changes only. A new field gets a default; nothing already working breaks underneath it.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Security reports go through [`SECURITY.md`](SECURITY.md), not public issues.

## License

MIT. See [`LICENSE`](LICENSE).
