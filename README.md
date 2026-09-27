# Smaraṇa

> **स्मरण**: Sanskrit, *"the act of remembering."* Not the archive itself. The act of pulling the right piece of it back into use at the right moment.

Claude Projects forget everything between sessions, or they remember everything and drown in it. Neither works. Smaraṇa gives a Claude Project real memory: sorted by how often it actually changes, capped so it never grows into a file nobody reads, and rebuilt the same deterministic way every time.

## How it works

Every memory operation runs the same state machine:

```
[Phase 1: Ingestion/Probe] → [Phase 2: Tier Resolution] → [Phase 3: Compression/GC] → [Phase 4: Persistence Handshake]
```

State gets sorted into three tiers, by how often it changes:

| Tier | Holds | Volatility |
|---|---|---|
| **1: Active Execution** | Current tasks, in-flight bugs, uncommitted state | High. Pruned every GC pass. |
| **2: System Architecture & Decisions** | Tech stack choices, ADRs, why something was built this way | Medium. Superseded, never silently deleted. |
| **3: Domain Rules & User Preferences** | Standing rules ("always X, never Y") | Low. Append-and-supersede only, never garbage-collected by volume. |

The result gets written to `MEMORY.md`, either through an MCP filesystem/memory server if one's connected, or as a Markdown artifact you paste into the Project's Knowledge if not. The file stays under 120 lines, roughly 800 tokens. Anything that ages out collapses into a two-line changelog entry instead of vanishing.

## What's optional on top of that

Four things sit on top of the core pipeline. None of them are required. Each one degrades cleanly to "nothing happens" if you skip it.

**Verified-completion gates.** A Tier 1 task can carry a `check`/`expect` command pair. It only reaches `status: done` once that check has actually run and passed, never on a confident self-report. The schema itself rejects a `done` task that skipped verification.

**A Laya cross-check on Tier Resolution.** [Laya](https://huggingface.co/convaiinnovations/laya) is a small, local, non-autoregressive classifier: no text generation, no API call, no hallucination risk. `scripts/tier_screen.py` asks it the same tier/contradiction/duplicate questions Phase 2 already asks by hand, and returns calibrated probabilities in one forward pass. It never decides anything. Phase 2's own resolution procedure stays authoritative; disagreement is a reason to look again, not an override.

**Semantic search over what's already aged out.** Superseded ADRs and compressed changelog entries get indexed into a local vector store. `search_memory` finds the right one by meaning instead of requiring the exact original wording. Live tiers stay a plain file read, this only helps with what's already been summarized down to a couple of terse lines.

**Sākṣī, a zero-token watcher.** A set of Claude Code hooks for multi-agent workflows. It makes no model calls itself: it briefs a new sub-agent from `MEMORY.md` so it doesn't start cold, flags an unchanged re-read, and logs everything so the actual token effect can be measured instead of assumed. It can optionally use the same Laya model, out of band, to tag ADRs by topic so a differently-worded task can still find the right one. See [`sakshi/README.md`](sakshi/README.md).

## How portable this actually is

The storage layer doesn't belong to Claude. `server/` speaks MCP over plain HTTP for Claude, and a plain JSON REST surface for everyone else, a CRM, an ERP, a codebase with no LLM in it at all. `memory-schema.json` is ordinary JSON Schema. Any client that can make an HTTP request can read and write this memory now, not just an MCP-capable one.

It's also no longer just storage. `write_file` enforces the schema and the hard cap server-side, via `server/engine.py`: a malformed write gets rejected with a real reason, and an oversized one gets consolidated before it's persisted. That enforcement used to live entirely in `SKILL.md`'s prose, which meant it only held when the caller was an LLM that read and followed that prose well. Now it holds for any caller, because the server itself checks.

Tier Resolution, the actual judgment call of which tier a fact belongs in, still isn't a pure function anywhere in this repo. But it's no longer only available as prose a model has to read. `classify_fact` wraps the same local Laya classifier Claude's own Phase 2 optionally cross-checks against, exposed as a real endpoint: a CRM webhook or an ERP script can call it directly and get a calibrated tier decision back, no LLM reasoning over `SKILL.md` required. It's a small, local, non-autoregressive model, not a full reasoning engine, so treat its call the way Claude already does: a strong signal, not an unappealable verdict.

What's still genuinely not done: no other LLM besides Claude has been tested against `SKILL.md`'s reasoning, and there's no real integration example yet for a specific CRM or ERP, just the REST routes they'd need. Track both in [`CHANGELOG.md`](CHANGELOG.md).

## Repository structure

```
smarana/
├── SKILL.md                       # Orchestrator: the pipeline, the tier rules, the file map
├── schemas/
│   └── memory-schema.json         # Structural contract every MEMORY.md write validates against
├── workflows/
│   ├── initialize-memory.md       # Bootstrap when no MEMORY.md exists yet
│   ├── consolidate-memory.md      # Dedup, collapse, hard-cap enforcement
│   ├── mcp-handshake.md           # MCP-first, artifact-fallback write logic
│   └── tier-screen.md             # Optional Laya-based cross-check for Phase 2
├── scripts/
│   ├── tier_screen.py             # Local Laya calibrated classifier for Phase 2
│   ├── requirements.txt           # laya, opt-in dependency
│   └── README.md                  # Usage, install, known limitations
├── examples/
│   └── MEMORY.md                  # A populated, schema-valid example
├── docs/
│   └── project-setup-guide.md     # Copy-paste setup steps for a new Claude Project
├── server/
│   ├── server.py                  # Remote memory server: MCP + plain REST, both enforced through engine.py
│   ├── engine.py                  # Schema validation, rendering, consolidation/GC (promoted from tests/)
│   ├── oauth_provider.py          # Minimal OAuth 2.1 authorization server for the Connector flow
│   ├── memory_index.py            # Semantic search over aged-out memory (local Chroma vector store)
│   └── README.md                  # Setup, tool/REST reference, known limits
├── sakshi/
│   ├── hook.py                    # Zero-token watcher: one entry point for all Claude Code hook events
│   ├── memory.py                  # MEMORY.md parser + cold-start brief builder
│   ├── topics.py                  # Fixed topic taxonomy, keyword fallback, cache reader
│   ├── laya_score.py              # Out-of-band Laya scoring of ADRs by topic, cached to disk
│   ├── detectors.py                # Re-read and loop detectors
│   ├── store.py                   # Event log, ledger, locked per-agent state
│   ├── report.py                  # Per-session summary incl. real transcript token usage
│   └── README.md                  # Install, modes, how to measure, known limits
└── tests/
    ├── test_pipeline.py           # Schema, GC, hard cap, idempotency (imports server/engine.py)
    ├── test_tier_screen.py        # Input-parsing/error-handling contract for tier_screen.py
    ├── test_sakshi.py             # Sākṣī: parsing, briefing, detectors, hook contract
    └── README.md                  # What's tested, what isn't, and why
```

## Installation

There are two ways to run this, and which one you want depends on what you're actually trying to do.

### Quickstart: one Project, no server

The fastest way to see it work. Nothing to deploy, nothing to host.

1. Paste the Custom Instructions block from [`docs/project-setup-guide.md`](docs/project-setup-guide.md) into your Claude Project's settings.
2. Upload a seed `MEMORY.md` to that Project's Knowledge. See [`examples/MEMORY.md`](examples/MEMORY.md) for a populated reference.
3. Upload this repo's `SKILL.md`, `schemas/`, and `workflows/` files as the Skill itself.
4. Repeat per Project. Memory isn't shared across Projects in this mode, matching how Claude Projects already isolate Knowledge.

In this mode, Claude writes `MEMORY.md` as an artifact and you paste it back into Knowledge by hand after each session. It works, but you're the sync step.

### The real thing: a running memory server

`server/` is a small MCP server. Claude reads and writes `MEMORY.md` directly, over a live connection, no copy-paste step, no you-are-the-sync-step. One deploy serves every Project you have, each one keyed by name and isolated from the others. It ships with real OAuth 2.1 in front of it, so a leaked tunnel URL isn't the only thing standing between the outside world and your memory. This is what actually makes it a memory system instead of a save file you manage yourself. See [`server/README.md`](server/README.md) to run it.

### On top of the server

Once the server's up, three more things come with it or bolt on for free:

- **Semantic search over aged-out memory.** Ships with the server, nothing extra to install. Finds a superseded ADR by what it meant, not its exact original wording.
- **A Laya cross-check on Tier Resolution.** `pip install -r scripts/requirements.txt`, see [`scripts/README.md`](scripts/README.md). Optional, local, no API key.
- **Sākṣī, the zero-token watcher.** A handful of Claude Code hooks for multi-agent workflows. See [`sakshi/README.md`](sakshi/README.md).

None of these are required to get value from day one, and the quickstart above is a legitimate way to use this long-term if you only ever run one Project. But if you're deciding how seriously to take this system, the server is the real answer. Start there.

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
- Tier 3 is never garbage-collected by volume pressure. It's superseded only by an explicit, contradicting user statement.

## Status

Schema validated against Draft-07 JSON Schema. The deterministic parts of the pipeline (schema conformance, hard-cap enforcement, aged-history collapse, usage-based retention, verified-completion gate enforcement, idempotency) are covered by an automated suite in [`tests/`](tests/): 80 tests, 79 passing and 1 skipped when `laya` is actually installed. Phase 2 (Tier Resolution) is a runtime judgment call, not a pure function, and stays out of scope for automated testing; see [`tests/README.md`](tests/README.md). `scripts/tier_screen.py`'s Laya cross-check has its own suite (12 tests) covering input parsing and error handling only. Real inference was verified by hand against this README's own worked example, at roughly 3–10 seconds per call on CPU-only hardware; see [`scripts/README.md`](scripts/README.md) for the honest latency numbers and the checkpoint's known calibration caveats. Sākṣī has its own suite (`tests/test_sakshi.py`, 39 tests) and was checked live against a headless Claude Code session; see [`sakshi/README.md`](sakshi/README.md). The remote memory server's OAuth flow has its own end-to-end smoke test, `server/test_oauth_flow.py`, run manually against a live tunnel rather than in CI. The server's indexing and search logic has its own automated suite in CI, including a real round-trip against a live local vector store, not a mock. `write_file`'s schema/hard-cap enforcement and `classify_fact` have their own suite in `server/test_server.py` (29 tests total, up from 20), and were also verified manually end to end against a running server with `curl`, no MCP client: a malformed write rejected, an oversized write auto-consolidated, and a real Laya classification returned over plain REST.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Security reports go through [`SECURITY.md`](SECURITY.md), not public issues.

## License

MIT. See [`LICENSE`](LICENSE).
