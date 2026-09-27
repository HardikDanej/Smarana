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
│   ├── server.py                  # Remote memory MCP server (streamable HTTP)
│   ├── oauth_provider.py          # Minimal OAuth 2.1 authorization server for the Connector flow
│   ├── memory_index.py            # Semantic search over aged-out memory (local Chroma vector store)
│   └── README.md                  # Setup: run, tunnel, connect as a claude.ai Connector
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
    ├── smarana_lib.py              # Reference implementation of the deterministic scaffolding
    ├── test_pipeline.py           # Schema, GC, hard cap, idempotency
    ├── test_tier_screen.py        # Input-parsing/error-handling contract for tier_screen.py
    ├── test_sakshi.py             # Sākṣī: parsing, briefing, detectors, hook contract
    └── README.md                  # What's tested, what isn't, and why
```

## Installation

See [`docs/project-setup-guide.md`](docs/project-setup-guide.md) for the full walkthrough. Short version:

1. Paste the Custom Instructions block from the setup guide into your Claude Project's settings.
2. Upload a seed `MEMORY.md` to that Project's Knowledge. See [`examples/MEMORY.md`](examples/MEMORY.md) for a populated reference.
3. Upload this repo's `SKILL.md`, `schemas/`, and `workflows/` files as the Skill itself, or reference them however your Claude Project's Skill-loading mechanism expects.
4. Repeat per Project. Nothing here is shared across Projects. That isolation is native to Claude Projects, not something this system adds.

That's the whole install. Everything past step 4, the server, Sākṣī, the Laya cross-check, is optional, and each one has its own short README with its own install steps.

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

Schema validated against Draft-07 JSON Schema. The deterministic parts of the pipeline (schema conformance, hard-cap enforcement, aged-history collapse, usage-based retention, verified-completion gate enforcement, idempotency) are covered by an automated suite in [`tests/`](tests/): 80 tests, 79 passing and 1 skipped when `laya` is actually installed. Phase 2 (Tier Resolution) is a runtime judgment call, not a pure function, and stays out of scope for automated testing; see [`tests/README.md`](tests/README.md). `scripts/tier_screen.py`'s Laya cross-check has its own suite (12 tests) covering input parsing and error handling only. Real inference was verified by hand against this README's own worked example, at roughly 3–10 seconds per call on CPU-only hardware; see [`scripts/README.md`](scripts/README.md) for the honest latency numbers and the checkpoint's known calibration caveats. Sākṣī has its own suite (`tests/test_sakshi.py`, 39 tests) and was checked live against a headless Claude Code session; see [`sakshi/README.md`](sakshi/README.md). The remote memory server's OAuth flow has its own end-to-end smoke test, `server/test_oauth_flow.py`, run manually against a live tunnel rather than in CI. The server's indexing and search logic has its own automated suite in CI, including a real round-trip against a live local vector store, not a mock.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Security reports go through [`SECURITY.md`](SECURITY.md), not public issues.

## License

MIT. See [`LICENSE`](LICENSE).
