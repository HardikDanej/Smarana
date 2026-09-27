#!/usr/bin/env python3
"""
Scores every active ADR in MEMORY.md against Sakshi's fixed topic taxonomy
(topics.py) using Laya, and caches the result to disk so the hot dispatch
path (hook.py's SubagentStart handler, via memory.select_adrs) never has to
call a model: it just reads this cache.

This is meant to run out of band, triggered by a MEMORY.md change — wire it
as a `FileChanged` hook matching `MEMORY.md` in settings.json (see
settings.example.json), ideally with `"async": true` so it doesn't block the
turn that just edited the file. It can also be run by hand, e.g. once after
first installing `laya`, to backfill the cache before any change triggers it:

    python sakshi/laya_score.py

Like hook.py, this always exits 0. If `laya` isn't installed, or a project
has no MEMORY.md yet, it's a clean no-op — Sakshi's ranking simply keeps
using plain keyword overlap, exactly as before this file existed. Nothing
here changes the actual Tier Resolution pipeline; it only feeds Sakshi's own
brief-selection heuristic.

Cost is real and paid here, not on the hot path: per scripts/README.md's own
measurement, a Laya call takes roughly 3-10 seconds on CPU-only hardware.
Only ADRs whose text changed since they were last scored (checked by hash)
are re-scored, so a small MEMORY.md edit costs one Laya call, not one per
ADR.

Environment: same as hook.py — CLAUDE_PROJECT_DIR / SAKSHI_DIR / SAKSHI_MEMORY.
Reads one JSON event object from stdin if stdin isn't a TTY (the FileChanged
hook contract), and ignores it otherwise so `python sakshi/laya_score.py`
works as a plain manual command too.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sakshi import memory, topics  # noqa: E402
from sakshi.store import Store, now_iso  # noqa: E402

TOPIC_QUESTION_INSTRUCTIONS = (
    "A structural or technical decision (an ADR) from a project's memory needs "
    "to be tagged by topic, so a future task touching a related area can be "
    "briefed with it even when that task is phrased differently from the "
    "decision itself. Given the decision and its rationale below, which topic "
    "does it relate to most?"
)


def _read_event() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        return {}


def _config(event: dict) -> tuple[Store, Path]:
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())
    data = Path(os.environ.get("SAKSHI_DIR") or project / ".sakshi")
    mem = Path(os.environ.get("SAKSHI_MEMORY") or project / "MEMORY.md")
    return Store(data), mem


def score_adr(agent, adr_text: str) -> dict[str, float] | None:
    """One Laya call, one ADR. Returns a topic->probability dict, or None on
    any failure — the caller treats that exactly like "not scored yet"."""
    question = {
        "topic": {
            "type": "choice",
            "instructions": TOPIC_QUESTION_INSTRUCTIONS,
            "criteria": topics.laya_criteria(),
        }
    }
    try:
        result = agent.predict({"decision": adr_text}, question)
    except Exception:
        return None
    answers = result.get("answers", {}) if isinstance(result, dict) else {}
    probs = (answers.get("topic") or {}).get("probabilities")
    if not isinstance(probs, dict):
        return None
    # Defensive: only keep keys from our own taxonomy, in case the model
    # returns something unexpected. A stray key would otherwise sit in the
    # cache forever and never mean anything to topic_similarity's consumers.
    return {k: float(v) for k, v in probs.items() if k in topics.TOPICS and isinstance(v, (int, float))}


def run(store: Store, mem_path: Path) -> None:
    mem = memory.load_memory(mem_path)
    if mem is None:
        return  # no MEMORY.md yet; nothing to score

    active = [a for a in mem.adrs if a.status == "active"]

    try:
        import laya
    except Exception as e:
        store.log("laya_score.log", f"skipped: laya not importable: {e}")
        return
    try:
        agent = laya.load("convaiinnovations/laya")
    except Exception as e:
        store.log("laya_score.log", f"skipped: model load failed: {e}")
        return

    with store.locked(topics.GLOBAL_SESSION, topics.CACHE_KEY) as (state, save):
        if state is None:
            store.log("laya_score.log", "skipped: cache lock busy")
            return

        cache = state.get("adrs", {})
        live_ids = {a.id for a in active}
        changed = False
        scored, failed, cached_hit = 0, 0, 0
        start = time.time()

        for adr in active:
            h = topics.hash_text(adr.text)
            entry = cache.get(adr.id)
            if entry and entry.get("hash") == h:
                cached_hit += 1
                continue
            probs = score_adr(agent, adr.text)
            if not probs:
                failed += 1
                continue
            cache[adr.id] = {"hash": h, "topics": probs, "scored_at": now_iso()}
            scored += 1
            changed = True

        stale = [adr_id for adr_id in cache if adr_id not in live_ids]
        for adr_id in stale:
            del cache[adr_id]
            changed = True

        if changed:
            state["adrs"] = cache
            save(state)

        store.log(
            "laya_score.log",
            f"scored={scored} cached={cached_hit} failed={failed} "
            f"removed_stale={len(stale)} elapsed_s={round(time.time() - start, 1)}",
        )


def main() -> int:
    event = _read_event()
    store, mem_path = _config(event)
    try:
        run(store, mem_path)
    except Exception as exc:  # same ironclad contract as hook.py
        store.log_error(f"laya_score: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
