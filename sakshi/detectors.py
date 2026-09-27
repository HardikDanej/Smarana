"""
Zero-token detectors. Pure functions over one agent's state dict: no I/O
except an os.stat on a file path, no model calls.

State shape (one per agent context window, persisted by store.Store):

    {
      "step":  int,                              # completed tool calls so far
      "calls": {hash: {tool, count, first_step, last_step, tokens, head}},
      "reads": {path: {step, tokens, hash, mtime}},
      "edits": {path: step},
      "noted": {"<kind>:<hash>": count_when_noted}
    }

Two findings in v0:

  reread  the agent is about to Read a file it already read, with the same
          offset/limit, and the file hasn't changed since (checked by both
          edit tracking and mtime, so a `sed -i` through Bash still counts
          as a change).
  loop    the same non-mutating tool call, with identical input, is about to
          run a third time with no file edited by this agent in between.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

LOOP_THRESHOLD = 3  # the Nth identical call is the one that gets a note
RENOTE_EVERY = 3    # after a note, stay quiet for this many more repeats
HEAD_CHARS = 160

READ_TOOLS = frozenset({"Read"})
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
AGENT_TOOLS = frozenset({"Agent", "Task"})
# Tools where repetition is normal or the call itself is the side effect.
LOOP_IGNORE = EDIT_TOOLS | AGENT_TOOLS | frozenset(
    {"TodoWrite", "TaskOutput", "TaskStop", "ReadNotifications", "AskUserQuestion",
     "ScheduleWakeup", "Monitor", "SendMessage", "ToolSearch"}
)


@dataclass
class Finding:
    kind: str           # "reread" | "loop"
    note: str           # text shown to the agent
    avoidable_tokens: int  # tokens a blocked call would have saved (reread only)
    key: str


def call_hash(tool: str, tool_input) -> str:
    blob = json.dumps([tool, tool_input], sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def norm_path(p: str) -> str:
    return os.path.normcase(os.path.normpath(p)) if p else ""


def _file_path(tool_input) -> str:
    if not isinstance(tool_input, dict):
        return ""
    return norm_path(tool_input.get("file_path") or tool_input.get("notebook_path") or "")


def _mtime(path: str):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def response_text(tool_response) -> str:
    if isinstance(tool_response, str):
        return tool_response
    try:
        return json.dumps(tool_response, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(tool_response)


def _display(tool_input) -> str:
    """The path as the agent wrote it (norm_path lowercases on Windows), trimmed from the left."""
    raw = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    return raw if len(raw) <= 80 else "..." + raw[-77:]


def check(state: dict, tool: str, tool_input) -> Finding | None:
    """Run before a tool call. Never mutates state except the `noted` map."""
    h = call_hash(tool, tool_input)
    noted = state.setdefault("noted", {})

    if tool in READ_TOOLS:
        path = _file_path(tool_input)
        prev = state.get("reads", {}).get(path)
        if prev and prev.get("hash") == h:
            edited_since = state.get("edits", {}).get(path, -1) > prev["step"]
            mtime = _mtime(path)
            changed_on_disk = mtime is not None and prev.get("mtime") is not None and mtime != prev["mtime"]
            if not edited_since and not changed_on_disk:
                key = f"reread:{h}"
                count = state.get("calls", {}).get(h, {}).get("count", 1)
                if key in noted and count < noted[key] + RENOTE_EVERY:
                    return None
                noted[key] = count
                return Finding(
                    kind="reread",
                    note=(
                        f"[Sakshi] You already read `{_display(tool_input)}` at step {prev['step']} of this "
                        f"agent (~{prev['tokens']} tokens) and it hasn't changed since. That content "
                        "should still be in your context; reuse it rather than reading it again."
                    ),
                    avoidable_tokens=int(prev.get("tokens", 0)),
                    key=key,
                )
        return None

    if tool in LOOP_IGNORE:
        return None
    prev = state.get("calls", {}).get(h)
    if not prev or prev["count"] + 1 < LOOP_THRESHOLD:
        return None
    edits = state.get("edits", {})
    if edits and max(edits.values()) > prev["last_step"]:
        return None  # something changed since the last identical call; rerunning is legit
    key = f"loop:{h}"
    if key in noted and prev["count"] < noted[key] + RENOTE_EVERY:
        return None
    noted[key] = prev["count"]
    head = prev.get("head", "").replace("\n", " ")
    return Finding(
        kind="loop",
        note=(
            f"[Sakshi] This exact {tool} call is about to run again ({prev['count'] + 1} times in "
            f"this agent, first at step {prev['first_step']}) with no file edited in between. "
            f"Last result began: \"{head}\". Unless you expect a different outcome this time, "
            "try a different approach."
        ),
        avoidable_tokens=0,
        key=key,
    )


def record(state: dict, tool: str, tool_input, tool_response) -> dict:
    """Run after a tool call completes. Mutates state; returns the event fields."""
    step = state.get("step", 0) + 1
    state["step"] = step
    h = call_hash(tool, tool_input)
    text = response_text(tool_response)
    tokens = (len(text) + 3) // 4

    calls = state.setdefault("calls", {})
    c = calls.get(h)
    if c:
        c["count"] += 1
        c["last_step"] = step
        c["tokens"] = tokens
        c["head"] = text[:HEAD_CHARS]
    else:
        calls[h] = {"tool": tool, "count": 1, "first_step": step, "last_step": step,
                    "tokens": tokens, "head": text[:HEAD_CHARS]}

    path = _file_path(tool_input)
    if tool in READ_TOOLS and path:
        state.setdefault("reads", {})[path] = {"step": step, "tokens": tokens, "hash": h,
                                               "mtime": _mtime(path)}
    if tool in EDIT_TOOLS and path:
        state.setdefault("edits", {})[path] = step

    return {"step": step, "hash": h, "response_tokens": tokens,
            "repeat": calls[h]["count"] > 1, "path": path or None}


def reset_context(state: dict) -> None:
    """After compaction the agent no longer holds earlier reads verbatim."""
    state["reads"] = {}
    state["noted"] = {}
