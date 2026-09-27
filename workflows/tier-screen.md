# Tier Screen — Optional Laya Cross-Check for Phase 2

An optional, local, deterministic-to-invoke step Phase 2 (Tier Resolution)
may call on a fact that's genuinely ambiguous. It runs a small,
non-autoregressive classifier — [Laya](https://huggingface.co/convaiinnovations/laya)
— over the candidate fact and returns calibrated numbers for the same three
questions Phase 2's own resolution procedure already asks by hand. This is a
second, independent signal to check Phase 2's own reading against, never a
replacement for it. Laya has read only the flattened text it's handed here —
not the surrounding conversation, not the codebase — so it is not more
trustworthy than Claude's own Phase 2 judgment; it is a cheap, fast
cross-check, nothing more.

## Why this exists

Phase 2 is explicitly a runtime judgment call (see `SKILL.md` and
`tests/README.md`) — the resolution procedure has Claude ask itself three
plain-language questions ("does this stop being true when the task ends?",
"is this a structural choice future work must respect?", "is this a standing
rule?") and pick a tier. That judgment can drift under context pressure in a
long session, the same failure mode a long consolidation pass or a crowded
conversation creates for any single-pass reasoning call. Laya scores the
same three-way tier question, plus whether the fact contradicts an existing
Tier 2 entry or duplicates something already recorded, in one fast local
forward pass with calibrated probabilities — not a softmax dressed up as
confidence.

## When to call it

Only when Phase 2 is genuinely uncertain about a fact's tier, or before
marking an existing ADR `superseded` on a contradiction it isn't fully sure
about. Do not call it reflexively on every Phase 2 write — most facts are
unambiguous (a bug fix is obviously Tier 1, a stated "always/never" rule is
obviously Tier 3), and this step costs real wall-clock time (see
`scripts/README.md`'s Known Limitations — several seconds on ordinary CPU
hardware, longer on first use while the model downloads). If `scripts/`'s
dependencies were never installed (see below), skip this step entirely and
proceed with Phase 2's own resolution procedure unassisted — that procedure
is complete and sufficient on its own; this step only sharpens it.

## What you do, in order

1. Resolve the script path:
   `<repo root>/scripts/tier_screen.py` — the path is relative to wherever
   this Smarana repo's files were loaded from (uploaded Skill files, or a
   cloned/synced local copy), not a fixed absolute path.
2. Write the JSON object `{"candidate_text": "<the new fact, verbatim>",
   "existing_context": "<a flattened plain-text digest of the currently
   active Tier 2 entries and all Tier 3 rules that could plausibly relate to
   this fact>"}` to a scratch file. Omit `existing_context` (or leave it
   empty) when nothing plausibly related exists yet, such as on a nearly
   empty `MEMORY.md`. Do not pipe raw JSON through a shell heredoc —
   quotes and newlines in the candidate text can break shell escaping;
   write it as a file instead.
3. Run it: `python "<script path>" "<scratch file path>"`. If that fails
   with a shell-level "command not found" (not a Python traceback — the
   script catches its own errors internally and always prints JSON), retry
   once with `python3` before concluding no interpreter is available.
4. The script always prints exactly one line of JSON to stdout, whether or
   not Laya loaded successfully — parse it.
5. If the script's own output couldn't be produced at all (interpreter
   genuinely missing, permission error), treat this step as unavailable and
   proceed with Phase 2's own resolution procedure unassisted. Never invent
   a plausible-looking result to fill the gap — an honestly skipped
   cross-check is strictly better than a fabricated one.

## Reading the result

```json
{
  "model": "laya-english (convaiinnovations/laya)",
  "tier_placement": {
    "choice": "tier2_architecture_decision",
    "probabilities": {"tier1_active_execution": 0.05, "tier2_architecture_decision": 0.88, "tier3_domain_rule": 0.07},
    "confidence": 0.83
  },
  "contradicts_existing_decision": {"probability": 0.61, "flagged": false},
  "duplicate_or_noop": {"probability": 0.04, "flagged": false},
  "flag_threshold": 0.85,
  "latency_ms": 1840.2,
  "error": null
}
```

- **`tier_placement.choice`** agreeing with Phase 2's own reading is not
  worth mentioning — that's the expected case. **Disagreeing** is worth a
  second look at the fact before finalizing the tier, not an automatic
  override: Phase 2's own procedure has read the actual conversation this
  fact came from, and Laya has only read the one-line digest it was handed.
- **`contradicts_existing_decision.flagged: true`** (probability at or above
  `flag_threshold`) is a prompt to re-check whether the candidate fact really
  should mark an existing Tier 2 entry `superseded` per Phase 2 step 6 —
  confirm against the actual existing entry's text before acting on it.
- **`duplicate_or_noop.flagged: true`** is a prompt to check whether writing
  this fact would actually change `MEMORY.md` at all — if it wouldn't, this
  Phase 2 write can resolve as a no-op, consistent with the idempotency
  guarantee described in `README.md`.
- **`error` non-null** means the screen didn't run (Laya not installed,
  model load failed, or inference failed) — treat it exactly like the
  script never having been called, and proceed with Phase 2's own
  resolution procedure unassisted. Do not surface the raw error text as if
  it were a finding about the memory content itself.

## What this is not

Not a replacement for Phase 2's resolution procedure, not a second opinion
that outranks Claude's own reading of the conversation, and not something to
call on every write. It is a fast, cheap, optional numeric cross-check for
the genuinely ambiguous case — nothing here changes what gets written to
`MEMORY.md` by itself. Phase 4's persistence handshake still runs exactly as
described in `workflows/mcp-handshake.md` regardless of whether this step
ran, was skipped, or errored.
