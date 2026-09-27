# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Sākṣī v0, a zero-token watcher** (`sakshi/`): Claude Code hooks that watch the orchestrator, agents and sub-agents without any model calls. A sub-agent gets a ~300-token cold-start brief from `MEMORY.md` at `SubagentStart` (Tier 3 rules, the active ADRs that match its dispatch prompt by keyword, and the parent's open tasks). An agent about to re-read an unchanged file, or to repeat an identical call a third time, gets a short note. Every tool call goes to `.sakshi/events.jsonl`, and every intervention goes to `.sakshi/ledger.jsonl`. `SAKSHI_MODE=observe` logs only, for A/B baselines. `block` denies unchanged re-reads. `sakshi/report.py` summarises a session, including real API usage read from its transcripts.
- `tests/test_sakshi.py` (39 tests, stdlib only). The hook contract was also verified live against a headless Claude Code session; see `sakshi/README.md`.

## [2.5.0] — 2026-09-26

### Added

- **Optional Laya-based cross-check for Phase 2 (Tier Resolution)** (`scripts/tier_screen.py`, invoked via the new `workflows/tier-screen.md`), adapted from the same pattern used elsewhere for a "local calibrated classifier as a second signal on an LLM judgment call." Laya (https://huggingface.co/convaiinnovations/laya) is a small, non-autoregressive classifier that answers typed questions in one fast local forward pass with calibrated probabilities instead of a softmax — no text generation, so no hallucination risk. `tier_screen.py` asks it three questions in one call: which of the three tiers a candidate fact belongs in (a `choice` question, mirroring Phase 2's own three-way resolution procedure), whether it contradicts an existing Tier 2 entry, and whether it duplicates something already recorded. It never decides anything by itself — Phase 2's own resolution procedure remains authoritative, and this step is only called when a tier call is genuinely ambiguous, never reflexively on every write. `SKILL.md` Phase 2 gained a step describing when to call it and how to weigh disagreement (a prompt to double-check, never an automatic override, since Laya has read only the flattened fact text it's given, not the conversation).
- `scripts/requirements.txt` and `scripts/README.md` — the same "real, optional dependency weight" disclosure pattern used for `server/`'s `chromadb` addition. The script degrades to a clean `{"error": "..."}` response with every field null if `laya` was never installed, and Phase 2 simply proceeds unassisted in that case.
- `tests/test_tier_screen.py` (12 tests) covering the script's input-parsing and error-handling contract via a substituted fake `laya` module — offline, in milliseconds, no model download. Consistent with this repo's existing rule that only the deterministic parts of the pipeline are covered by the automated suite; real inference was verified manually against this README's own worked Tier 2 example (Redis → Postgres session storage) and correctly scored `tier2_architecture_decision` at 0.66 probability.

### Changed

- `schema_version` remains `2.0.0` — this feature writes nothing new to `MEMORY.md`'s schema, it only informs the Phase 2 judgment call before a write happens.

### Known limitations

- Laya's own model card and its published benchmark cite ~33ms/question on GPU. On CPU-only hardware (no CUDA), real measured latency for this script's three-question batch was 3–10 seconds, well above even the model card's own ~200ms/question CPU figure — disclosed honestly in `scripts/README.md` rather than repeating the marketing number.
- The `convaiinnovations/laya` checkpoint warns on load that some of its internal option buckets ship miscalibrated temperatures. `workflows/tier-screen.md` treats its output as a cross-check to weigh, not ground truth, for exactly this reason.

## [2.4.0] — 2026-09-02

### Added

- **Semantic search over aged-out memory** (`search_memory` tool on `server/`), adapted from [`claude-mem`](https://github.com/thedotmack/claude-mem)'s hybrid semantic/keyword retrieval approach. `write_file` now indexes each project's superseded/deprecated Tier 2 ADRs and Compressed Changelog entries — the detail that's already been compressed away to stay under the 120-line cap — into a local Chroma vector store (`server/data/<project>/vector_index/`). `search_memory(project, query, top_k)` queries it by meaning rather than exact keyword. Live Tier 1/2/3 content is deliberately not indexed; a plain `read_file` already covers it in full. Uses Chroma's default local embedding model (no API key, no per-query cost); the model (~80MB) downloads once from Hugging Face's CDN on first use and runs offline afterward.
- `SKILL.md` Phase 1 gained a step describing when to call `search_memory` — only as a fallback when the live file doesn't answer something asked, never reflexively every turn.

### Changed

- `server/requirements.txt` gained `chromadb` — a real dependency-weight increase (`onnxruntime` and friends), flagged in `server/README.md`'s Known Limitations.
- CI's `server-tests` job now also runs `test_memory_index.py` and caches the downloaded embedding model between runs.

## [2.3.0] — 2026-09-01

### Added

- **Verified-completion gates on Tier 1 tasks** (`tier1_active_tasks[].gate`), adapted from the [`unlazy`](https://github.com/Leonxlnx/unlazy) skill's gate-contract pattern. An optional `{check, expect, verified, verified_at, evidence}` object: when a task's outcome is genuinely checkable by a command, a `check`/`expect` pair can be attached, and `status: done` is only reachable once that check has actually been run and `verified: true` recorded — never as a self-report. Enforced structurally, not just by instruction: `schemas/memory-schema.json` uses a Draft-07 `if/then` constraint that rejects any state where a gated task claims `done` without `verified: true`. `evidence` records a short fingerprint (exit code, output length/hash) — raw output is never persisted, mirroring `unlazy`'s own rule. Gates are entirely opt-in; a task with no `gate` behaves exactly as before this feature existed.

### Changed

- `schema_version` remains `2.0.0` — `gate` is optional and additive; existing `MEMORY.md` files validate unchanged.

## [2.2.0] — 2026-08-08

### Added

- **Remote memory MCP server** (`server/`) — gives Smaraṇa a real `MCP` persistence mode instead of only the artifact (copy-paste) fallback. Exposes `read_file`/`write_file`/`list_files`/`list_projects` over streamable HTTP, keyed per `project` so one server instance holds isolated memory for many Claude Projects.
- **Real OAuth 2.1 on the memory server** (`server/oauth_provider.py`) — dynamic client registration (RFC 7591), PKCE (RFC 7636), and a password-gated login page, so claude.ai's Connector flow ends at an actual credential check instead of the tunnel URL being the only protection. Falls back to no auth when `SMARANA_PUBLIC_HOST`/`SMARANA_LOGIN_PASSWORD` aren't set.
- **Provenance tags** — `tier2_architecture_log[].source` and `tier1_active_tasks[].source`: a short free-text note on which conversation/session produced the entry.
- **Usage-based retention for Tier 2** — `tier2_architecture_log[].last_referenced`. A superseded ADR that keeps getting cited again in later sessions resets its own collapse eligibility instead of aging out on a flat 7-day-from-creation timer.
- **Structured supersedes link** — `tier2_architecture_log[].superseded_by`, the back-reference counterpart to the existing `supersedes` field. Both fields are now set on both sides of a supersession in the same write, making "what replaced X" and "what did Y replace" both directly queryable instead of requiring a parse of `rationale` prose.

### Changed

- `schema_version` remains `2.0.0` — every field above is optional and additive; existing `MEMORY.md` files validate unchanged.

## [2.1.0] — 2026-08-03

### Changed

- **Renamed the project to Smaraṇa** (Sanskrit, "that which is remembered"). Previously "Project Memory Engine".
  - `SKILL.md` frontmatter `name` is now `smarana`.
  - `tests/pme_lib.py` is now `tests/smarana_lib.py`.
  - Schema `$id` is now `https://internal/smarana/memory-schema.json`.
  - The on-disk memory file is still `MEMORY.md`, and the schema shape is unchanged — existing memory files remain valid without migration.

### Fixed

- `tests/test_pipeline.py` now works when run from the repository root, matching the command the README documents. It previously only imported correctly when run from inside `tests/`.
- Removed a stray, unrelated "gluten-free" line from the Tier 3 rules in `examples/MEMORY.md`, replaced with a rule coherent with the example's auth-migration scenario.

### Added

- Contributor scaffolding: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue and pull-request templates.
- Continuous integration on GitHub Actions, running the test suite across Python 3.10–3.13.
- `requirements-dev.txt` pinning the test-time dependency.

## [2.0.0] — Initial public release

- 4-phase pipeline: Ingestion/Probe, Tier Resolution, Compression/GC, Persistence Handshake.
- 3-tier taxonomy: Active Execution, System Architecture & Decisions, Domain Rules & User Preferences.
- MCP-first persistence with Markdown-artifact fallback (`workflows/mcp-handshake.md`).
- Bootstrap routine for first-run initialization (`workflows/initialize-memory.md`).
- Consolidation routine enforcing a 120-line / ~800-token hard cap via dedup, aged-history collapse, and rationale compression (`workflows/consolidate-memory.md`).
- Structural contract for all memory objects (`schemas/memory-schema.json`), validated against Draft-07 JSON Schema.
- Idempotency check on writes: no-op runs produce no output.
- Tier 3 is exempt from volume-based pruning; append-and-supersede only.

The `schema_version` field tracks the `MEMORY.md` object shape and remains at `2.0.0` — the 2.1.0 release changed no schema fields.
