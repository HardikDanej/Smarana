# Per-Project Setup Guide

Use this every time you create a new Claude Project that should have its own isolated memory. Takes about 2 minutes.

## 1. Paste into the Project's Custom Instructions

Go to Project → Settings → Custom Instructions, and paste:

```
This project uses the Smaraṇa Skill for persistent state.

- MEMORY.md lives in THIS project's Knowledge/Files — nowhere else.
- At the start of every conversation in this project, check Knowledge for MEMORY.md and load it before responding to anything substantive.
- Run the Smaraṇa pipeline (Ingestion -> Tier Resolution -> Compression -> Persistence Handshake) whenever a task finishes, an architectural decision is made, or I say "save state" / "update memory" / "checkpoint".
- No MCP filesystem/memory server is connected here, so persistence is artifact-mode: when memory changes, output the full updated MEMORY.md in a single fenced code block and tell me to replace the old copy in this Project's Knowledge. Do not skip this — memory that isn't re-uploaded is lost next session.
- Never invent tasks, decisions, or rules I haven't actually stated or that aren't visible in the codebase/files I've shared here.
```

This is intentionally short. It's a pointer to the Skill, not a restatement of it. `SKILL.md` carries the detailed tier logic and compression rules; Claude loads that when triggered.

## 2. Upload a seed MEMORY.md

Create a file named `MEMORY.md` with this starting content and upload it to the Project's Knowledge/Files. This is the *only* copy: don't also paste it into Custom Instructions, keep the two separate.

```markdown
# MEMORY.md — <replace with this project's name>
Last updated: <today's date, ISO-8601>

## Tier 3 — Domain Rules & User Preferences
- <any standing constraints you already know — leave empty if none yet>

## Tier 2 — System Architecture & Decisions
- [ADR-001] <today> — Project initialized. Rationale: <why this project exists / what it's for>. Status: active

## Tier 1 — Active Execution
- [todo] Define first milestone

## Compressed Changelog
```

If you already know the stack, constraints, or first task, fill those in now instead of leaving placeholders. The `initialize-memory` workflow expects real content, not empty scaffolding, wherever you already have the answer. See `examples/MEMORY.md` for what a matured file looks like after several sessions.

## 3. Upload whatever else this project actually needs

Anything Claude should treat as ground truth for this specific project goes in Knowledge alongside `MEMORY.md`: schema dumps, API contracts, style guides, prior docs. `MEMORY.md` is the *only* file the memory engine writes to. Everything else is static reference material it reads but never modifies.

## 3b. Optional: switch on real MCP mode

By default (step 1's Custom Instructions text) this Project runs in
artifact mode — you paste `MEMORY.md` back into Knowledge by hand after
every save. If you've deployed the Smaraṇa memory server (see
[`../server/README.md`](../server/README.md)) and added it as a Connector
in claude.ai, drop the artifact-mode line from step 1's Custom Instructions
and replace it with:

```
An MCP memory server is connected here. Use it in MCP mode: on every
Persistence Handshake, call write_file(project="<this Project's exact
name>", content=<rendered MEMORY.md>) and, at session start, call
read_file(project="<this Project's exact name>") instead of searching
Knowledge for MEMORY.md. Do not also maintain a MEMORY.md copy in
Knowledge once MCP mode is on — the server is the single source of truth.
```

Use the *exact* Project name as the `project` argument, consistently,
every session — the server uses it to keep this Project's memory isolated
from every other Project connected to the same server.

## 4. Repeat per project

Every new Project = new Custom Instructions paste (identical, or lightly adjusted) + a fresh seed `MEMORY.md`. Nothing here is shared across Projects unless you deliberately copy a file over. That isolation is what Claude Projects already guarantees natively.
