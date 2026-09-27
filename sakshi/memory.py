"""
Reads a Smarana MEMORY.md and builds the compact cold-start brief a sub-agent
gets injected at SubagentStart.

Pure stdlib, no model calls, no jsonschema import: this runs inside a hook on
every sub-agent dispatch, so it has to be fast and it must never fail loudly.
It parses the rendered Markdown (the format tests/smarana_lib.py renders and
examples/MEMORY.md shows), not the JSON state, because MEMORY.md is what a
real project actually has on disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BRIEF_TOKEN_BUDGET = 300
MAX_ADRS = 4
# How much a perfect topic-similarity match (1.0) is worth in the same units
# as a literal keyword-overlap count. Chosen so it can pull a well-matched
# but differently-worded ADR into the "matched" pool (score > 0) without
# ever outranking an ADR that shares several literal words with the prompt.
TOPIC_SIMILARITY_WEIGHT = 3.0

_ADR_RE = re.compile(
    r"^\[(?P<id>[^\]]+)\]\s+(?P<date>\d{4}-\d{2}-\d{2})\s+[—-]+\s+(?P<body>.*)$"
)
_TASK_RE = re.compile(r"^\[(?P<status>todo|in_progress|blocked|done)\]\s+(?P<text>.*)$")
_STATUS_RE = re.compile(r"Status:\s*(?P<status>[a-z_]+)", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_\-]{2,}")

# Words that carry no signal for matching a dispatch prompt to an ADR.
_STOPWORDS = frozenset(
    """
    the and for with that this from into onto over under about after before
    are was were been being have has had not but you your our their them they
    its it's any all can could should would will must may might use using used
    what when where which who why how than then there here also only just very
    each such some more most other make made new one two per via etc status
    active rationale source decision decided superseded supersedes adr task
    agent subagent please need needs want wants find check run file files
    """.split()
)


@dataclass
class Adr:
    id: str
    date: str
    text: str
    status: str


@dataclass
class Memory:
    project: str = ""
    last_updated: str = ""
    rules: list[str] = field(default_factory=list)
    adrs: list[Adr] = field(default_factory=list)
    tasks: list[tuple[str, str]] = field(default_factory=list)  # (status, text)


def approx_tokens(text: str) -> int:
    """~4 chars per token. Good enough for a budget cap and a ledger estimate."""
    return (len(text) + 3) // 4


def parse_memory(markdown: str) -> Memory:
    mem = Memory()
    section = None
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("# MEMORY.md"):
            mem.project = line.split("—", 1)[-1].strip() if "—" in line else ""
            continue
        if line.lower().startswith("last updated:"):
            mem.last_updated = line.split(":", 1)[1].strip()
            continue
        if line.startswith("## "):
            heading = line.lower()
            if "tier 3" in heading:
                section = "t3"
            elif "tier 2" in heading:
                section = "t2"
            elif "tier 1" in heading:
                section = "t1"
            else:
                section = None  # Compressed Changelog etc. is never briefed
            continue
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        if not item or item.startswith("<"):  # template placeholders
            continue
        if section == "t3":
            mem.rules.append(item)
        elif section == "t2":
            m = _ADR_RE.match(item)
            if not m:
                continue
            status_m = _STATUS_RE.search(m["body"])
            status = status_m["status"].lower() if status_m else "active"
            mem.adrs.append(Adr(m["id"], m["date"], m["body"], status))
        elif section == "t1":
            m = _TASK_RE.match(item)
            if m:
                mem.tasks.append((m["status"], m["text"]))
    return mem


def load_memory(path: Path) -> Memory | None:
    try:
        return parse_memory(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def keywords(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def select_adrs(mem: Memory, dispatch_text: str, topics_cache: dict | None = None) -> list[Adr]:
    """Active ADRs ranked by relevance to the dispatch prompt.

    The primary signal is still literal keyword overlap, exactly as before.
    When `topics_cache` is given (Sakshi's optional Laya-scored topic cache —
    see topics.py and laya_score.py), an ADR whose cached topic distribution
    is stale (its text changed since it was scored) or missing altogether
    contributes zero from this term and ranks exactly as it did without the
    cache; this keeps behaviour unchanged for any project that hasn't opted
    into scoring, or hasn't scored a given ADR yet. Where a cache entry is
    fresh, topic similarity with the prompt can pull a differently-worded but
    conceptually related ADR into the matched pool, which plain keyword
    overlap alone would have missed entirely.

    With no prompt to match against (or nothing matched at all), fall back to
    the most recent active ADRs: a sub-agent with zero architectural context
    is exactly the cold-start case this exists to prevent.
    """
    active = [a for a in mem.adrs if a.status == "active"]
    if not active:
        return []
    # Local import: topics.py imports `keywords` from this module, so this
    # side of the dependency must stay lazy to avoid a circular import at
    # module load time. See topics.py's own docstring.
    from sakshi import topics

    wanted = keywords(dispatch_text)
    prompt_topics = topics.classify_text(dispatch_text) if topics_cache else {}
    scored = []
    for a in active:
        score = float(len(wanted & keywords(a.text)))
        cached = (topics_cache or {}).get(a.id)
        if cached and cached.get("hash") == topics.hash_text(a.text):
            score += TOPIC_SIMILARITY_WEIGHT * topics.topic_similarity(
                prompt_topics, cached.get("topics") or {}
            )
        scored.append((score, a.date, a))
    matched = [s for s in scored if s[0] > 0]
    pool = matched if matched else scored
    pool.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [a for _, _, a in pool[:MAX_ADRS]]


def build_brief(mem: Memory, dispatch_text: str = "", budget: int = BRIEF_TOKEN_BUDGET,
                topics_cache: dict | None = None) -> str:
    """The injected text. Empty string means there is nothing worth injecting."""
    adrs = select_adrs(mem, dispatch_text, topics_cache)
    open_tasks = [(s, t) for s, t in mem.tasks if s in ("in_progress", "blocked")]
    if not (mem.rules or adrs or open_tasks):
        return ""

    def render(rules: list[str], adr_list: list[Adr], tasks: list[tuple[str, str]]) -> str:
        stamp = f", updated {mem.last_updated}" if mem.last_updated else ""
        out = [
            f"[Sakshi brief from Smarana MEMORY.md{stamp}] Context the parent session "
            "already holds, so you don't need to re-derive it. Entries are dated; "
            "verify anything that looks stale before relying on it."
        ]
        if rules:
            out.append("Standing rules (non-negotiable):")
            out += [f"- {r}" for r in rules]
        if adr_list:
            out.append("Relevant decisions:")
            out += [f"- [{a.id}] {a.date}: {a.text}" for a in adr_list]
        if tasks:
            out.append("Parent's open work:")
            out += [f"- [{s}] {t}" for s, t in tasks]
        return "\n".join(out)

    rules, adr_list, tasks = list(mem.rules), list(adrs), list(open_tasks)
    text = render(rules, adr_list, tasks)
    # Shed the least load-bearing content first: tasks, then the weakest ADRs.
    # Tier 3 rules go last, because they are the ones a sub-agent can't guess.
    while approx_tokens(text) > budget and (tasks or adr_list or len(rules) > 1):
        if tasks:
            tasks.pop()
        elif adr_list:
            adr_list.pop()
        else:
            rules.pop()
        text = render(rules, adr_list, tasks)
    if approx_tokens(text) > budget:
        text = text[: budget * 4 - 3] + "..."
    return text
