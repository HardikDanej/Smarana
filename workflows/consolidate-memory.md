# Memory Consolidation & Pruning Routine

Runs when any Phase 3 threshold in `SKILL.md` is met: Tier 1 item count > 30, turn count since last persistence > 15, or an architectural pivot just occurred. Operates on the in-memory draft before Phase 4 writes it — never edits a persisted file directly.

## Priority Order

Prune in this order and stop as soon as the file is back under cap. Do not skip ahead to a later step while an earlier one still has candidates — cheaper, safer reductions come first:

1. Deduplicate
2. Collapse aged Tier 1 (and superseded Tier 2) history into the Changelog
3. Compress Tier 2 rationale text
4. Tier 3 is never pruned by volume — see Hard Constraints

## Step 1 — Deduplicate

Merge overlapping or restated rules and decisions into one canonical line:

- Two Tier 3 rules expressing the same constraint in different words → keep the more precise phrasing, drop the other.
- Two Tier 2 ADRs describing the same decision at different times → keep the latest, mark it `active`, mark the earlier one `superseded`. Set the link on both sides: the new ADR's `supersedes` gets the old ADR's `id`, the old ADR's `superseded_by` gets the new ADR's `id`. Do not delete the superseded entry here — that happens once it ages out in Step 2.
- Two Tier 1 tasks describing the same underlying work with different wording → merge into one, keeping the more advanced status (`in_progress` beats `todo`, `blocked` beats both until unblocked). Keep whichever `source` is more specific; if both are equally specific, keep the earlier one.

## Step 2 — Collapse Aged History

Any Tier 1 entry with `status: done` and `updated` older than 7 days is removed from its tier and folded into `compressed_changelog`.

**Tier 2 uses usage-based retention, not a flat timer.** A `status: superseded` entry is eligible for collapse once 7 days have passed since whichever is more recent: its `date`, or its `last_referenced` (if set). An ADR that keeps getting cited — someone asks "why did we move off X," a later decision explicitly builds on it — has its `last_referenced` bumped by Phase 1 each time that happens (see `SKILL.md` Phase 1, step 6), which resets its collapse eligibility. An ADR nobody mentions again ages out on the plain 7-day-from-`date` schedule, same as before this feature existed. This only applies to entries already `superseded` — an `active` ADR is never collapsed by this step regardless of age or reference activity.

Group by 7-day window and write exactly 2 lines per window — one line for what shipped, one line for what changed structurally — skipping whichever line has nothing to report for that window.

**Format:**
```
[YYYY-MM-DD to YYYY-MM-DD]: <what was completed, in one line>
[YYYY-MM-DD to YYYY-MM-DD]: <what architecturally changed, in one line — only if Tier 2 items collapsed too>
```

**Worked example:**

Before — Tier 1 entries aging out:
```
- [done, 2026-07-13] Migrate auth middleware to JWT
- [done, 2026-07-15] Fix session race condition in login flow
- [done, 2026-07-18] Add refresh-token rotation
```
Tier 2 entry superseded in the same window:
```
- [ADR-003] superseded — "Session-cookie auth" → replaced by ADR-006
```

After — Compressed Changelog:
```
- [2026-07-13 to 2026-07-18]: Completed JWT auth migration, including refresh-token rotation and a login race-condition fix.
- [2026-07-13 to 2026-07-18]: Replaced session-cookie auth (ADR-003) with JWT-based auth (ADR-006).
```

Four source lines (three Tier 1 + one Tier 2) become two lines. That ratio is the expected outcome — if a 7-day window only produces one line's worth of content, write one line, not two padded ones.

## Step 3 — Compress Tier 2 Rationale

For ADRs that remain `active` (not yet eligible for collapse) but whose `rationale` field runs long, cut it to the single sentence that lets a future session avoid re-litigating the decision. Do not touch `decision` — only `rationale` is compressible; the decision text itself must stay exact and unabridged.

## Hard Constraints

- **Tier 3 is never pruned for space.** If the file still exceeds cap after Steps 1–3, that means Tier 2 or Tier 1 still hold prunable content — re-run Steps 1–2 more aggressively before Tier 3 is ever touched.
- **Hard cap:** the resulting `MEMORY.md` must not exceed **120 lines or ~800 tokens** (approximate token count via word count × 1.3). Re-check after every step and stop as soon as the file is under cap rather than over-pruning.
- **Never collapse a `blocked` or `in_progress` Tier 1 item**, regardless of age. Only `done` items age into the changelog.

## Output

Return the pruned, deduplicated, capped draft to Phase 4 for the persistence handshake. Do not write directly from this routine.
