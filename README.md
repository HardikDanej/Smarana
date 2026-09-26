# Smaraṇa

> **स्मरण** — Sanskrit, *"remembrance, recollection, the act of remembering."* Where *śruti* is what is heard fresh in the moment, smaraṇa is the calling back to mind of what was retained.

A tier-aware memory system for Claude Projects. It gives a Claude Project persistent, structured state across sessions instead of an ever-growing, unsorted context dump.

Most attempts at "give Claude memory" fail in one of two ways: everything gets remembered until the file is useless, or nothing gets remembered and every session starts from zero. Smaraṇa solves that with a 3-tier taxonomy, a deterministic 4-phase pipeline, and a hard cap that forces compression instead of unbounded growth.

## How it works

Every memory operation runs the same state machine:

```
[Phase 1: Ingestion/Probe] → [Phase 2: Tier Resolution] → [Phase 3: Compression/GC] → [Phase 4: Persistence Handshake]
```

State is sorted into three tiers, by volatility:

| Tier | Holds | Volatility |
|---|---|---|
| **1 — Active Execution** | Current tasks, in-flight bugs, uncommitted state | High. Pruned every GC pass. |
| **2 — System Architecture & Decisions** | Tech stack choices, ADRs, "why we built it this way" | Medium. Superseded, never silently deleted. |
| **3 — Domain Rules & User Preferences** | Non-negotiable standing rules ("always X, never Y") | Low. Append-and-supersede only, never garbage-collected by volume. |

The result persists to `MEMORY.md`, written either through an MCP filesystem/memory server if one is connected, or as a Markdown artifact you paste into the Project's Knowledge if not. The file is capped at 120 lines / ~800 tokens; anything that ages out collapses into a two-line changelog entry instead of disappearing.

Tier 1 tasks can optionally carry a **verified-completion gate** — a `check`/`expect` command pair adapted from the [`unlazy`](https://github.com/Leonxlnx/unlazy) skill's gate-contract pattern. A gated task can only reach `status: done` once that check has actually been run and passed; a confident self-report isn't enough, and the schema itself rejects a `done` task whose gate wasn't verified. Most tasks won't have one — it's opt-in for outcomes a command can genuinely decide.

When connected via `server/`, Smaraṇa also gets **semantic search over its own aged-out history** — an idea adapted from [`claude-mem`](https://github.com/thedotmack/claude-mem)'s hybrid retrieval approach. Superseded ADRs and Compressed Changelog entries (the detail that's already been compressed away to stay under the cap) are indexed into a local, free vector store; `search_memory` finds the right one by meaning instead of requiring the exact original wording. Live tiers stay a plain file read — this only helps with what's already been summarized down to a couple of terse lines.

## Repository structure

```
smarana/
├── SKILL.md                       # Orchestrator: the pipeline, the tier rules, the file map
├── schemas/
│   └── memory-schema.json         # Structural contract every MEMORY.md write validates against
├── workflows/
│   ├── initialize-memory.md       # Bootstrap when no MEMORY.md exists yet
│   ├── consolidate-memory.md      # Dedup, collapse, hard-cap enforcement
│   └── mcp-handshake.md           # MCP-first, artifact-fallback write logic
├── examples/
│   └── MEMORY.md                  # A populated, schema-valid example
├── docs/
│   └── project-setup-guide.md     # Copy-paste setup steps for a new Claude Project
├── server/
│   ├── server.py                  # Remote memory MCP server (streamable HTTP)
│   ├── oauth_provider.py          # Minimal OAuth 2.1 authorization server for the Connector flow
│   ├── memory_index.py            # Semantic search over aged-out memory (local Chroma vector store)
│   ├── test_client.py             # Manual smoke test: read/write/list against a running server
│   ├── test_oauth_flow.py         # Manual smoke test: full OAuth flow against a live tunnel
│   ├── test_server.py             # Automated: tool logic, DATA_ROOT regression, search integration
│   ├── test_memory_index.py       # Automated: extraction logic + a real Chroma round-trip
│   └── README.md                  # Setup: run, tunnel, connect as a claude.ai Connector
└── tests/
    ├── smarana_lib.py              # Reference implementation of the deterministic scaffolding
    ├── test_pipeline.py           # Test harness: schema, GC, hard cap, idempotency
    └── README.md                  # What's tested, what isn't, and why
```

## Installation

See [`docs/project-setup-guide.md`](docs/project-setup-guide.md) for the full walkthrough. Short version:

1. Paste the Custom Instructions block from the setup guide into your Claude Project's settings.
2. Upload a seed `MEMORY.md` to that Project's Knowledge (see [`examples/MEMORY.md`](examples/MEMORY.md) for a populated reference).
3. Upload this repo's `SKILL.md`, `schemas/`, and `workflows/` files as the Skill itself, or reference them however your Claude Project's Skill-loading mechanism expects.
4. Repeat per Project. Nothing here is shared across Projects; that isolation is native to Claude Projects.

## Development

The deterministic parts of the pipeline have an automated test suite:

```bash
pip install -r requirements-dev.txt
```

```bash
python -m unittest discover -s tests -v
```

## Non-negotiable rules

- Nothing is persisted without passing Tier Resolution first.
- `MEMORY.md` never exceeds the hard cap.
- Nothing is fabricated: no invented decisions, no invented tasks, no invented rules. Memory reflects ground truth, not inference.
- Tier 3 is never garbage-collected by volume pressure. It is superseded only by an explicit, contradicting user statement.

## Status

Schema validated against Draft-07 JSON Schema. Pipeline logic reviewed for internal consistency across all five Skill files. The deterministic parts of the pipeline (schema conformance, hard-cap enforcement, aged-history collapse, usage-based retention, verified-completion gate enforcement, idempotency) are covered by an automated test suite in [`tests/`](tests/), 29/29 passing. Phase 2 (Tier Resolution) is a runtime judgment call, not a pure function, and is out of scope for automated testing; see [`tests/README.md`](tests/README.md) — this includes the act of actually running a gate's `check` command, though the schema-level guarantee that a gated task can't reach `done` without `verified: true` is itself fully tested. The remote memory server's OAuth flow (`server/`) has its own end-to-end smoke test, `server/test_oauth_flow.py`, run manually against a live tunnel rather than in CI. The server's indexing/search logic (`server/memory_index.py`) has its own automated suite in CI, including a real round-trip against a live local vector store, not a mock. Version `2.4.0`.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Security reports go through [`SECURITY.md`](SECURITY.md), not public issues.

## License

MIT. See [`LICENSE`](LICENSE).
