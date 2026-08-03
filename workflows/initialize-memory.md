# Memory Initialization Routine

Runs when Phase 1 of `SKILL.md` finds no existing `MEMORY.md` in either `MCP` or `ARTIFACT` persistence mode. This is a bootstrap, not a rewrite — it never runs against a project that already has state; that path belongs to `consolidate-memory.md`.

## Step 1 — Determine Whether to Probe

Check the current conversation and environment for enough signal to fill the template without asking:

- Project or repo name already stated, or visible in open files → use it.
- Tech stack already visible (`package.json`, imports, prior messages) → use it.
- No explicit standing rules stated yet → leave Tier 3 minimal. Do not invent constraints to fill space.

Only ask the user directly if the project's scope is genuinely unclear after checking available context. Ask at most once, combined into a single pass:

- "What's the project, and what's the core stack?"
- "Any non-negotiable conventions I should lock in from the start — style guide, naming, testing rules?"

If the user has already supplied this earlier in the conversation, skip the questions entirely and proceed to Step 2.

## Step 2 — Build the Skeleton

Populate the canonical template from `SKILL.md` with:

- **Tier 3 — Domain Rules & User Preferences:** the stated stack and any constraints given so far. An empty list is valid — never fabricate a rule just to populate this section.
- **Tier 2 — System Architecture & Decisions:** the initial setup decision(s) that produced the project's current state (e.g., "Initialized as a Next.js 15 + Postgres project"), each written as a proper ADR: `id` starting at `ADR-001`, `date` = today, `status: active`.
- **Tier 1 — Active Execution:** the immediate next step(s) as stated or clearly inferable from the current task. If nothing has been stated yet, a single item is enough: "Define first milestone."
- **Compressed Changelog:** empty array — there is nothing to collapse yet.

## Step 3 — Validate

Check the draft against `schemas/memory-schema.json` before handing it off:

- All four top-level arrays are present, even if empty.
- Every Tier 2 entry has a well-formed `ADR-###` id.
- Every Tier 1 entry has a `status` in `{todo, in_progress, blocked, done}`.
- `last_updated` is a valid ISO-8601 timestamp and `project_name` is non-empty.

## Step 4 — Hand Off to Persistence

Do not write the file directly from this routine. Return the validated draft to Phase 4 and execute `workflows/mcp-handshake.md`, which performs the actual `MCP` or `ARTIFACT` write.

## Step 5 — Confirm

Report back in one line what was initialized, e.g.: "Initialized MEMORY.md — 1 ADR, 1 open task, no standing rules yet." Do not re-print the whole file in chat if it was persisted via MCP; only surface the full content when `PERSISTENCE_MODE = ARTIFACT` required showing it for copy-paste into Project Knowledge.
