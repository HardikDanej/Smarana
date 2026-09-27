# MCP Handshake & Persistence Fallback Routine

Runs at Phase 4 of every pipeline execution in `SKILL.md`. Takes the finalized draft — from Phase 2 directly, or post-consolidation from Phase 3 — and commits it, preferring MCP over the artifact fallback.

## Step 1 — Confirm Persistence Mode

Use the `PERSISTENCE_MODE` established during Phase 1. Do not re-probe unless the available tool list has visibly changed mid-session (e.g., a connector was added or removed).

## Step 2 — MCP Path (`PERSISTENCE_MODE == MCP`)

1. Validate the draft against `schemas/memory-schema.json` in-memory before any write. Reject and re-run the relevant Phase 2/3 step if a required field is missing rather than writing invalid state.
2. Detect which MCP surface is available and use its native call:

| Available tool namespace | Write call | Read call (Phase 1) |
|---|---|---|
| `mcp__filesystem__*` (generic single-root server) | `write_file(path="MEMORY.md", content=<rendered markdown>)` | `read_file(path="MEMORY.md")` |
| `mcp__filesystem__*` (Smaraṇa memory server, see `server/README.md`) | `write_file(project=<this Claude Project's name>, content=<rendered markdown>)` | `read_file(project=<this Claude Project's name>)` |
| `mcp__memory__*` (knowledge-graph style) | `create_entities` / `add_observations`, mapped tier-by-tier — one entity per Tier 2 ADR, one per Tier 1 task, a single `project_rules` entity holding Tier 3 | `read_graph()` |

When the connected server exposes a `project` parameter (multi-tenant
servers, including `server/`), pass the exact Claude Project name as
`project` on every call so state stays isolated per Project on a single
shared server. Single-root filesystem servers scoped to one directory per
connection don't need this — omit `project` if the tool signature doesn't
accept it.

`server/`'s Smaraṇa memory server also exposes `search_memory(project, query,
top_k)` — semantic search over aged-out history (superseded ADRs,
Compressed Changelog entries) that a plain `read_file` can no longer show
in full. This is a Phase 1 retrieval concern, not a write-path one; see
`SKILL.md` Phase 1 for when to call it. Not every `mcp__filesystem__*`
server has this tool — check the tool list before relying on it, and treat
its absence as normal, not an error.

3. For `mcp__filesystem__*`, render the schema-valid draft into the canonical Markdown template from `SKILL.md` before writing. For `mcp__memory__*`, map each schema array to entities and observations instead of writing raw Markdown.
4. Write silently. Do not print the full file contents into the chat — MCP mode means the user never has to see or paste anything. Confirm with a single line, e.g., "Memory updated — 2 tasks closed, 1 new ADR."
5. **On write failure** (tool error, auth failure, timeout): retry once. On a second failure, fall through to Step 3 (`ARTIFACT` path) for this run only, and flag the failure in one line so the user can check the connector.

## Step 3 — Artifact Path (`PERSISTENCE_MODE == ARTIFACT`)

1. Render the draft into the canonical Markdown template.
2. Output it as a single fenced Markdown code block titled `MEMORY.md` — nothing else inside the block, so it can be copied wholesale.
3. Follow the block with exactly one line telling the user what to do with it:
   > Paste this into your Project Knowledge (or Files) as `MEMORY.md`, replacing the previous version.
4. Do not add extra commentary, a diff explanation, or a re-summary below that line. The code block plus the one instruction is the complete output of this phase.

## Step 4 — Idempotency Check

Before either path writes, compare the draft against the last-known state loaded in Phase 1. If nothing actually changed — no tier had a net diff — skip the write entirely and surface no message. A no-op run must be invisible to the user.

## Decision Logic (reference)

```
if PERSISTENCE_MODE == MCP:
    validate(draft, memory-schema.json)
    if mcp__filesystem__* available:
        write_file("MEMORY.md", render_markdown(draft))
    elif mcp__memory__* available:
        sync_graph(draft)
    else:
        PERSISTENCE_MODE = ARTIFACT   # tools vanished mid-session
        goto ARTIFACT
    on_failure -> retry_once -> on_second_failure -> goto ARTIFACT

if PERSISTENCE_MODE == ARTIFACT:
    output_codeblock(render_markdown(draft), title="MEMORY.md")
    output_single_line_instruction()
```
