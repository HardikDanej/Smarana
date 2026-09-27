#!/usr/bin/env python3
"""
Summarise what Sakshi saw and did, per session, so an A/B run can be judged
on numbers instead of on the claim that it helps.

    python sakshi/report.py                     # every session in <cwd>/.sakshi
    python sakshi/report.py --dir path/.sakshi  # a different data dir
    python sakshi/report.py --session <id>      # one session only
    python sakshi/report.py --json              # machine-readable

Two sources:
  events.jsonl / ledger.jsonl   written by the hooks (tool calls, repeats, interventions)
  the session transcripts       real API usage (input, cache, output tokens), read from the
                                transcript_path the hooks recorded, plus any sub-agent
                                transcripts stored alongside it

The ledger's avoided_tokens_est is only filled in where the saving is certain
(a blocked re-read). The value of a brief or a loop note can't be known from
one run; compare total usage between a SAKSHI_MODE=observe run and an
advise run of the same workflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def transcript_usage(transcript: str | None, session: str) -> dict | None:
    """Sum message usage across the main transcript and its sub-agent transcripts.

    A single API response can be written as several transcript lines (one per
    content block), all carrying the same usage, so usage is deduplicated by
    message id before summing.
    """
    if not transcript:
        return None
    main = Path(transcript)
    files = [main] if main.exists() else []
    side_dir = main.with_suffix("")  # <session>.jsonl -> <session>/
    if side_dir.is_dir():
        files += sorted(side_dir.rglob("*.jsonl"))
    if not files:
        return None
    totals = defaultdict(int)
    seen = set()
    for f in files:
        for rec in read_jsonl(f):
            msg = rec.get("message")
            if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                continue
            mid = msg.get("id") or rec.get("requestId") or rec.get("uuid")
            if mid in seen:
                continue
            seen.add(mid)
            u = msg["usage"]
            for k in ("input_tokens", "cache_creation_input_tokens",
                      "cache_read_input_tokens", "output_tokens"):
                totals[k] += int(u.get(k) or 0)
            totals["api_calls"] += 1
    totals["transcript_files"] = len(files)
    return dict(totals)


def summarise(data_dir: Path, only_session: str | None = None) -> dict:
    events = read_jsonl(data_dir / "events.jsonl")
    ledger = read_jsonl(data_dir / "ledger.jsonl")
    sessions: dict[str, dict] = {}

    def s(sid):
        return sessions.setdefault(sid, {
            "modes": set(), "transcript": None, "tool_calls": 0, "tool_response_tokens": 0,
            "repeat_calls": 0, "repeat_response_tokens": 0, "subagents": 0,
            "subagents_matched_dispatch": 0, "agents": set(),
            "interventions": defaultdict(int), "would_be_interventions": defaultdict(int),
            "injected_tokens": 0, "avoided_tokens_est": 0,
        })

    for e in events:
        sid = e.get("session")
        if only_session and sid != only_session:
            continue
        r = s(sid)
        r["modes"].add(e.get("mode"))
        r["transcript"] = r["transcript"] or e.get("transcript")
        if e.get("event") == "tool":
            r["tool_calls"] += 1
            r["agents"].add(e.get("agent_id"))
            r["tool_response_tokens"] += e.get("response_tokens", 0)
            if e.get("repeat"):
                r["repeat_calls"] += 1
                r["repeat_response_tokens"] += e.get("response_tokens", 0)
        elif e.get("event") == "subagent_start":
            r["subagents"] += 1
            r["subagents_matched_dispatch"] += int(bool(e.get("matched_dispatch")))

    for l in ledger:
        sid = l.get("session")
        if only_session and sid != only_session:
            continue
        r = s(sid)
        if l.get("applied"):
            r["interventions"][l["kind"]] += 1
            r["injected_tokens"] += l.get("injected_tokens", 0)
            r["avoided_tokens_est"] += l.get("avoided_tokens_est", 0)
        else:
            r["would_be_interventions"][l["kind"]] += 1

    out = {}
    for sid, r in sessions.items():
        r["usage"] = transcript_usage(r["transcript"], sid)
        r["modes"] = sorted(m for m in r["modes"] if m)
        r["agents"] = len(r["agents"])
        r["interventions"] = dict(r["interventions"])
        r["would_be_interventions"] = dict(r["would_be_interventions"])
        out[sid] = r
    return out


def render(report: dict) -> str:
    if not report:
        return "No Sakshi data found."
    lines = []
    for sid, r in report.items():
        lines.append(f"Session {sid}  mode={'/'.join(r['modes']) or '?'}")
        lines.append(f"  tool calls           {r['tool_calls']} across {r['agents']} agent context(s)")
        lines.append(f"  tool output tokens   ~{r['tool_response_tokens']:,}")
        lines.append(f"  repeated calls       {r['repeat_calls']} (~{r['repeat_response_tokens']:,} tokens of output)")
        lines.append(f"  sub-agents started   {r['subagents']} ({r['subagents_matched_dispatch']} matched to a dispatch prompt)")
        if r["interventions"]:
            kinds = ", ".join(f"{k}={v}" for k, v in sorted(r["interventions"].items()))
            lines.append(f"  interventions        {kinds}")
            lines.append(f"  tokens injected      ~{r['injected_tokens']:,}")
            lines.append(f"  tokens avoided (certain) ~{r['avoided_tokens_est']:,}")
        if r["would_be_interventions"]:
            kinds = ", ".join(f"{k}={v}" for k, v in sorted(r["would_be_interventions"].items()))
            lines.append(f"  would have fired     {kinds}  (observe mode)")
        u = r["usage"]
        if u:
            total_in = u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
            lines.append(
                f"  API usage            {u['api_calls']} calls, input {total_in:,} "
                f"(fresh {u['input_tokens']:,}, cache write {u['cache_creation_input_tokens']:,}, "
                f"cache read {u['cache_read_input_tokens']:,}), output {u['output_tokens']:,}"
            )
        else:
            lines.append("  API usage            transcript not found")
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--dir", default=".sakshi", help="Sakshi data dir (default ./.sakshi)")
    ap.add_argument("--session", help="limit to one session id")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    report = summarise(Path(args.dir), args.session)
    if args.json:
        print(json.dumps(report, indent=2, default=list))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
