"""
Reference implementation of the deterministic parts of the Smṛti pipeline:
schema validation, rendering, consolidation/GC, and the idempotency check.

This does NOT implement Phase 2 (Tier Resolution) as an LLM would: deciding
which tier a new, freeform fact belongs to is a judgment call Claude makes at
runtime, not a deterministic function. Everything here operates on
already-classified, schema-shaped data and tests the parts of the spec that
ARE deterministic and therefore ARE testable: does the hard cap actually get
enforced, does aged history actually collapse the way consolidate-memory.md
says it should, is a no-op run actually a no-op, does every intermediate
state actually validate against the schema.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "memory-schema.json"
HARD_CAP_LINES = 120
HARD_CAP_TOKENS = 800  # approximated as word_count * 1.3, per consolidate-memory.md


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate(state: dict, schema: dict | None = None) -> None:
    """Raises jsonschema.ValidationError if state does not conform."""
    schema = schema or load_schema()
    jsonschema.validate(state, schema)


def empty_state(project_name: str, when: str) -> dict:
    """The skeleton produced by workflows/initialize-memory.md, Step 2."""
    return {
        "schema_version": "2.0.0",
        "project_name": project_name,
        "last_updated": when,
        "tier3_domain_rules": [],
        "tier2_architecture_log": [],
        "tier1_active_tasks": [{"task": "Define first milestone", "status": "todo"}],
        "compressed_changelog": [],
    }


def render_markdown(state: dict) -> str:
    """Renders a state object into the canonical MEMORY.md template from SKILL.md."""
    lines = [f"# MEMORY.md — {state['project_name']}", f"Last updated: {state['last_updated']}", ""]

    lines.append("## Tier 3 — Domain Rules & User Preferences")
    if state["tier3_domain_rules"]:
        lines += [f"- {rule}" for rule in state["tier3_domain_rules"]]
    lines.append("")

    lines.append("## Tier 2 — System Architecture & Decisions")
    for adr in state["tier2_architecture_log"]:
        suffix = ""
        if adr.get("superseded_by"):
            suffix = f" (superseded by {adr['superseded_by']})"
        elif adr.get("supersedes"):
            suffix = f" (supersedes {adr['supersedes']})"
        line = (
            f"- [{adr['id']}] {adr['date']} — {adr['decision']} "
            f"Rationale: {adr['rationale']}. Status: {adr['status']}{suffix}"
        )
        if adr.get("source"):
            line += f" Source: {adr['source']}."
        if adr.get("last_referenced"):
            line += f" Last referenced: {adr['last_referenced']}."
        lines.append(line)
    lines.append("")

    lines.append("## Tier 1 — Active Execution")
    for task in state["tier1_active_tasks"]:
        if task["status"] == "blocked":
            line = f"- [blocked] {task['task']} — reason: {task.get('blocked_reason', '')}"
        else:
            line = f"- [{task['status']}] {task['task']}"
        if task.get("source"):
            line += f" (source: {task['source']})"
        lines.append(line)
    lines.append("")

    lines.append("## Compressed Changelog")
    for entry in state["compressed_changelog"]:
        lines.append(f"- [{entry['range']}]: {entry['summary']}")

    return "\n".join(lines) + "\n"


def line_count(markdown: str) -> int:
    return len(markdown.splitlines())


def approx_token_count(markdown: str) -> float:
    return len(markdown.split()) * 1.3


def over_cap(state: dict) -> bool:
    md = render_markdown(state)
    return line_count(md) > HARD_CAP_LINES or approx_token_count(md) > HARD_CAP_TOKENS


def _days_between(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def consolidate(state: dict, today: str) -> dict:
    """
    Implements workflows/consolidate-memory.md:
      1. Deduplicate
      2. Collapse aged Tier 1 (done, >7 days) into the Compressed Changelog.
         Tier 2 uses usage-based retention: a superseded ADR collapses once
         7 days have passed since max(date, last_referenced) — an ADR that
         keeps getting cited resets its own collapse eligibility.
         Grouped by 7-day window, max 2 lines per window.
      3. Compress Tier 2 rationale for remaining active ADRs (best-effort here:
         truncate to the first sentence).
      Tier 3 is never touched by volume pressure (Hard Constraint).
    Stops as soon as the file is back under cap; does not over-prune.
    """
    s = copy.deepcopy(state)

    # --- Step 1: Deduplicate ---
    seen_rules = []
    for rule in s["tier3_domain_rules"]:
        if rule not in seen_rules:
            seen_rules.append(rule)
    s["tier3_domain_rules"] = seen_rules

    seen_tasks: dict[str, dict] = {}
    rank = {"todo": 0, "in_progress": 1, "blocked": 2, "done": 3}
    for task in s["tier1_active_tasks"]:
        key = task["task"]
        if key not in seen_tasks:
            seen_tasks[key] = task
        else:
            existing = seen_tasks[key]
            # in_progress/blocked outrank todo; done only wins if nothing active
            if task["status"] == "blocked" or (
                task["status"] == "in_progress" and existing["status"] == "todo"
            ):
                seen_tasks[key] = task
    s["tier1_active_tasks"] = list(seen_tasks.values())

    if over_cap(s):
        # --- Step 2: Collapse aged history ---
        done_old = [
            t for t in s["tier1_active_tasks"]
            if t["status"] == "done" and t.get("updated") and _days_between(t["updated"], today) > 7
        ]
        superseded_old = [
            a for a in s["tier2_architecture_log"]
            if a["status"] == "superseded"
            and _days_between(a.get("last_referenced") or a["date"], today) > 7
        ]

        if done_old or superseded_old:
            dates = [t["updated"] for t in done_old] + [a["date"] for a in superseded_old]
            window = f"{min(dates)} to {max(dates)}"

            if done_old:
                shipped = "; ".join(t["task"] for t in done_old)
                s["compressed_changelog"].append(
                    {"range": window, "summary": f"Completed: {shipped}."[:240]}
                )
            if superseded_old:
                changed = "; ".join(
                    f"{a['decision']} ({a['id']})" for a in superseded_old
                )
                s["compressed_changelog"].append(
                    {"range": window, "summary": f"Superseded: {changed}."[:240]}
                )

            done_keys = {t["task"] for t in done_old}
            s["tier1_active_tasks"] = [
                t for t in s["tier1_active_tasks"] if t["task"] not in done_keys
            ]
            superseded_ids = {a["id"] for a in superseded_old}
            s["tier2_architecture_log"] = [
                a for a in s["tier2_architecture_log"] if a["id"] not in superseded_ids
            ]

    if over_cap(s):
        # --- Step 3: Compress Tier 2 rationale for remaining active ADRs ---
        for adr in s["tier2_architecture_log"]:
            if adr["status"] == "active":
                first_sentence = adr["rationale"].split(".")[0].strip()
                if first_sentence:
                    adr["rationale"] = first_sentence + "."

    return s


def is_noop(old_state: dict, new_state: dict) -> bool:
    """Phase 4 idempotency check: no tier had a net diff."""
    keys = [
        "tier3_domain_rules",
        "tier2_architecture_log",
        "tier1_active_tasks",
        "compressed_changelog",
    ]
    return all(old_state[k] == new_state[k] for k in keys)
