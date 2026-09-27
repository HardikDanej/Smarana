# Sākṣī — the watcher (v0)

> **साक्षी**, *"the witness."* It watches every step the orchestrator, agents and sub-agents take, and speaks up only when Smaraṇa already knows something they're about to re-derive.

Sākṣī is a set of Claude Code hooks. It is **not** an LLM and makes **no model calls**: watching costs zero tokens. The only tokens it adds are the short notes and briefs it injects, and every one of those is logged so the net effect can be measured rather than assumed.

## What v0 does

| When | Hook | What happens |
|---|---|---|
| The orchestrator dispatches a sub-agent | `PreToolUse` (Agent tool) | The dispatch prompt is queued so it can be matched to the sub-agent. |
| The sub-agent starts | `SubagentStart` | It gets a **cold-start brief** from `MEMORY.md`, capped at ~300 tokens: all Tier 3 rules, up to 4 active ADRs ranked by keyword overlap with its task, and the parent's in-progress or blocked tasks. Superseded ADRs and the changelog are never briefed. |
| An agent is about to re-read a file | `PreToolUse` (Read) | If it's the same file and range, and the file hasn't changed (checked through edit tracking *and* mtime, so a `sed -i` counts), the agent is told it already has it. |
| The same call is about to run a 3rd time | `PreToolUse` | If nothing was edited in between, the agent gets a loop note that includes the start of the last result. |
| Any tool call finishes | `PostToolUse` | One line goes to `events.jsonl`: agent, tool, input hash, output size, and whether it was a repeat. |
| Context gets compacted | `PreCompact` | Read tracking resets, because the agent no longer holds those reads verbatim. |

Each agent (the main session and each sub-agent) is tracked separately, because each one has its own context window.

## Modes

Set with `SAKSHI_MODE`:

- `advise` (default): inject notes and briefs.
- `observe`: log everything, including what *would* have fired, and inject nothing. This is the baseline half of an A/B run.
- `block`: like `advise`, but an unchanged re-read is denied outright. This is the only case where the saving is certain, so it's the only one the ledger counts as `avoided_tokens_est`.

Other variables: `SAKSHI_DIR` (data dir, default `<project>/.sakshi`) and `SAKSHI_MEMORY` (default `<project>/MEMORY.md`).

## Install

Copy the block from [`settings.example.json`](settings.example.json) into the `.claude/settings.json` (or `settings.local.json`) of the project where your agent workflow runs, and replace `<path-to-smarana>`. You need Python 3.10+ on `PATH`. It uses only the standard library.

The hook always exits 0. If anything inside it fails, the error goes to `.sakshi/errors.log` and the session carries on as if Sākṣī weren't installed.

## Measure it

1. Run a real multi-agent workflow with `SAKSHI_MODE=observe`.
2. Run the same workflow again with `SAKSHI_MODE=advise`.
3. Run `python <path-to-smarana>/sakshi/report.py --dir <project>/.sakshi`.

The report shows, per session: tool calls, repeated calls, sub-agents briefed, interventions, tokens injected, and **real API usage** summed from the session transcript and its sub-agent transcripts (deduplicated by message id). Compare total input and output tokens between the two runs. One pair of runs is noisy, because the model doesn't take the same path twice. Treat a small difference as inconclusive.

## Verification

- `tests/test_sakshi.py` has 39 tests: parsing, brief selection and budget, the topic taxonomy and its Laya-scored cache-blending, both detectors, the hook's and `laya_score.py`'s stdin/stdout contracts run as real subprocesses, and the report's usage deduplication.
- It was checked live on 2026-09-26 with a headless Claude Code 2.1.263 session on Haiku 4.5. The main agent received the re-read note on its second `Read`. A `general-purpose` sub-agent quoted the injected brief, including ADR-005, which was selected by keyword match against its dispatch prompt. That run also confirmed the dispatch tool is named `Agent` with a `subagent_type` field, and that sub-agent transcripts live under `<session>/subagents/`.

## Known limits

- **It acts at tool boundaries only.** It can't interrupt a model mid-generation.
- **Advise mode doesn't save the flagged call itself.** The note arrives with the repeat and prevents the *next* ones. Only `block` saves the current re-read.
- **Keyword matching is crude.** An ADR phrased differently from the task won't rank. Laya or embedding ranking is a later step, if the numbers justify it.
- **Loop detection can't see Bash side effects.** A repeated `curl` while polling a server gets a (harmless) note.
- **Not in v0:** stall timer, stop-blocking for unverified gates, any model escalation.
