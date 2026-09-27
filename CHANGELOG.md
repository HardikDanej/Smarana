# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Renamed the project to Smaraṇa** (Sanskrit, "remembrance, recollection, the act of remembering"). Previously "Smṛti".
  - `SKILL.md` frontmatter `name` is now `smarana`.
  - `tests/smriti_lib.py` is now `tests/smarana_lib.py`.
  - Schema `$id` is now `https://internal/smarana/memory-schema.json`.
  - `server/`'s env vars are now `SMARANA_DATA_ROOT`, `SMARANA_HOST`, `SMARANA_PORT`, `SMARANA_PUBLIC_HOST`, `SMARANA_LOGIN_PASSWORD` (previously `SMRITI_*`).
  - `server/oauth_provider.py`'s `SmritiOAuthProvider` is now `SmaranaOAuthProvider`; the MCP server name is now `smarana-memory`.
  - The on-disk memory file is still `MEMORY.md`, and the schema shape is unchanged — existing memory files remain valid without migration.
  - The GitHub repository itself (`github.com/hardikdanej/smriti`) is unchanged; this rename covers the project's identifiers and prose only.

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

- **Remote memory MCP server** (`server/`) — gives Smṛti a real `MCP` persistence mode instead of only the artifact (copy-paste) fallback. Exposes `read_file`/`write_file`/`list_files`/`list_projects` over streamable HTTP, keyed per `project` so one server instance holds isolated memory for many Claude Projects.
- **Real OAuth 2.1 on the memory server** (`server/oauth_provider.py`) — dynamic client registration (RFC 7591), PKCE (RFC 7636), and a password-gated login page, so claude.ai's Connector flow ends at an actual credential check instead of the tunnel URL being the only protection. Falls back to no auth when `SMRITI_PUBLIC_HOST`/`SMRITI_LOGIN_PASSWORD` aren't set.
- **Provenance tags** — `tier2_architecture_log[].source` and `tier1_active_tasks[].source`: a short free-text note on which conversation/session produced the entry.
- **Usage-based retention for Tier 2** — `tier2_architecture_log[].last_referenced`. A superseded ADR that keeps getting cited again in later sessions resets its own collapse eligibility instead of aging out on a flat 7-day-from-creation timer.
- **Structured supersedes link** — `tier2_architecture_log[].superseded_by`, the back-reference counterpart to the existing `supersedes` field. Both fields are now set on both sides of a supersession in the same write, making "what replaced X" and "what did Y replace" both directly queryable instead of requiring a parse of `rationale` prose.

### Changed

- `schema_version` remains `2.0.0` — every field above is optional and additive; existing `MEMORY.md` files validate unchanged.

## [2.1.0] — 2026-08-03

### Changed

- **Renamed the project to Smṛti** (Sanskrit, "that which is remembered"). Previously "Project Memory Engine".
  - `SKILL.md` frontmatter `name` is now `smriti`.
  - `tests/pme_lib.py` is now `tests/smriti_lib.py`.
  - Schema `$id` is now `https://internal/smriti/memory-schema.json`.
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
