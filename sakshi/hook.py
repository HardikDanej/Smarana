#!/usr/bin/env python3
"""
Sakshi hook entry point. Claude Code runs this for every configured hook
event, passing the event JSON on stdin; see sakshi/README.md for the
settings.json block.

Contract: this script always exits 0 and never prints anything but a valid
hookSpecificOutput JSON object (or nothing). Any internal failure is written
to <data dir>/errors.log and the session carries on exactly as if Sakshi
weren't installed.

Environment:
  SAKSHI_MODE    advise (default) — inject notes and briefs
                 observe          — log events and would-be interventions, inject nothing
                                    (use this for the baseline half of an A/B run)
                 block            — like advise, but deny an unchanged re-read outright
  SAKSHI_DIR     data dir, default <project>/.sakshi
  SAKSHI_MEMORY  MEMORY.md to brief from, default <project>/MEMORY.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sakshi import detectors, memory, topics  # noqa: E402
from sakshi.store import Store, now_iso  # noqa: E402

PENDING_KEY = "pending"
PENDING_MAX_AGE_S = 600


def _project_dir(event: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())


def _config(event: dict) -> tuple[str, Store, Path]:
    project = _project_dir(event)
    mode = os.environ.get("SAKSHI_MODE", "advise").strip().lower()
    if mode not in ("advise", "observe", "block"):
        mode = "advise"
    data = Path(os.environ.get("SAKSHI_DIR") or project / ".sakshi")
    mem = Path(os.environ.get("SAKSHI_MEMORY") or project / "MEMORY.md")
    return mode, Store(data), mem


def _agent(event: dict) -> tuple[str, str]:
    return event.get("agent_id") or "main", event.get("agent_type") or "main"


def _emit(event_name: str, **fields) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event_name, **fields}}))


def _ledger(store: Store, event: dict, mode: str, kind: str, injected: str,
            avoided: int = 0, applied: bool = True, **extra) -> None:
    agent_id, agent_type = _agent(event)
    store.append("ledger.jsonl", {
        "ts": now_iso(), "session": event.get("session_id"), "agent_id": agent_id,
        "agent_type": agent_type, "mode": mode, "kind": kind, "applied": applied,
        "injected_tokens": memory.approx_tokens(injected) if applied else 0,
        "avoided_tokens_est": avoided if applied else 0, **extra,
    })


# --- handlers -------------------------------------------------------------

def on_pre_tool_use(event: dict, mode: str, store: Store, mem_path: Path) -> None:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    session = event.get("session_id", "")

    if tool in detectors.AGENT_TOOLS:
        # Remember what the sub-agent is being asked to do, so SubagentStart
        # (which doesn't carry the prompt) can match ADRs against it.
        with store.locked(session, PENDING_KEY) as (state, save):
            if state is None:
                return
            queue = [p for p in state.get("queue", []) if time.time() - p["t"] < PENDING_MAX_AGE_S]
            queue.append({
                "t": time.time(),
                "type": tool_input.get("subagent_type") or "general-purpose",
                "text": f"{tool_input.get('description', '')}\n{tool_input.get('prompt', '')}",
            })
            state["queue"] = queue
            save(state)
        return

    agent_id, _ = _agent(event)
    with store.locked(session, agent_id) as (state, save):
        if state is None:
            return
        finding = detectors.check(state, tool, tool_input)
        save(state)
    if not finding:
        return

    if mode == "observe":
        _ledger(store, event, mode, finding.kind, finding.note, applied=False, tool=tool)
        return
    if mode == "block" and finding.kind == "reread":
        _ledger(store, event, mode, "reread_blocked", finding.note,
                avoided=finding.avoidable_tokens, tool=tool)
        _emit("PreToolUse", permissionDecision="deny", permissionDecisionReason=finding.note)
        return
    _ledger(store, event, mode, finding.kind, finding.note, tool=tool)
    _emit("PreToolUse", additionalContext=finding.note)


def on_post_tool_use(event: dict, mode: str, store: Store, mem_path: Path) -> None:
    tool = event.get("tool_name", "")
    agent_id, agent_type = _agent(event)
    session = event.get("session_id", "")
    with store.locked(session, agent_id) as (state, save):
        if state is None:
            return
        fields = detectors.record(state, tool, event.get("tool_input") or {},
                                  event.get("tool_response"))
        save(state)
    store.append("events.jsonl", {
        "ts": now_iso(), "session": session, "agent_id": agent_id, "agent_type": agent_type,
        "event": "tool", "tool": tool, "mode": mode,
        "transcript": event.get("transcript_path"), **fields,
    })


def on_subagent_start(event: dict, mode: str, store: Store, mem_path: Path) -> None:
    session = event.get("session_id", "")
    agent_type = event.get("agent_type") or "general-purpose"

    dispatch_text = ""
    with store.locked(session, PENDING_KEY) as (state, save):
        if state is not None:
            queue = [p for p in state.get("queue", []) if time.time() - p["t"] < PENDING_MAX_AGE_S]
            for i, p in enumerate(queue):  # oldest matching dispatch first
                if p["type"] == agent_type:
                    dispatch_text = queue.pop(i)["text"]
                    break
            state["queue"] = queue
            save(state)
    if not dispatch_text:
        cfg = event.get("subagent_config") or {}
        dispatch_text = str(cfg.get("instructions") or cfg.get("prompt") or "")

    store.append("events.jsonl", {
        "ts": now_iso(), "session": session, "agent_id": event.get("agent_id"),
        "agent_type": agent_type, "event": "subagent_start", "mode": mode,
        "transcript": event.get("transcript_path"), "matched_dispatch": bool(dispatch_text),
    })

    mem = memory.load_memory(mem_path)
    if mem is None:
        return
    # Zero-latency read of whatever laya_score.py has cached out of band (see
    # sakshi/README.md's "Laya-scored decision ranking"). Empty {} — the
    # common case for a project that hasn't opted in, or hasn't run it yet —
    # falls straight back to build_brief's plain keyword-overlap ranking.
    topics_cache = topics.load_adr_topics(store.root)
    brief = memory.build_brief(mem, dispatch_text, topics_cache=topics_cache)
    if not brief:
        return
    if mode == "observe":
        _ledger(store, event, mode, "brief", brief, applied=False)
        return
    _ledger(store, event, mode, "brief", brief)
    _emit("SubagentStart", additionalContext=brief)


def on_pre_compact(event: dict, mode: str, store: Store, mem_path: Path) -> None:
    agent_id, _ = _agent(event)
    with store.locked(event.get("session_id", ""), agent_id) as (state, save):
        if state is None:
            return
        detectors.reset_context(state)
        save(state)


HANDLERS = {
    "PreToolUse": on_pre_tool_use,
    "PostToolUse": on_post_tool_use,
    "SubagentStart": on_subagent_start,
    "PreCompact": on_pre_compact,
}


def main() -> int:
    store = None
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        mode, store, mem_path = _config(event)
        handler = HANDLERS.get(event.get("hook_event_name", ""))
        if handler:
            handler(event, mode, store, mem_path)
    except Exception as exc:  # the one place a broad catch is the point
        if store is not None:
            store.log_error(f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
