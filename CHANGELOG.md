# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
