## What this changes

<!-- One or two sentences. Link the issue this closes, if there is one. -->

Closes #

## Why

<!-- The problem being solved. If this is a spec change, say what was ambiguous or wrong before. -->

## Invariant check

Smaraṇa's five invariants are listed in [CONTRIBUTING.md](../blob/main/CONTRIBUTING.md). Confirm this change preserves each, or explain below which one it deliberately changes and why.

- [ ] `MEMORY.md` still never exceeds the hard cap (120 lines / ~800 tokens)
- [ ] Tier 3 is still never garbage-collected by volume pressure
- [ ] `blocked` and `in_progress` items still never collapse, regardless of age
- [ ] Nothing is persisted without passing Tier Resolution first
- [ ] Nothing is fabricated — no invented tasks, decisions, or rules

## Checklist

- [ ] `python -m unittest discover -s tests -v` passes locally
- [ ] Spec changes (`SKILL.md`, `workflows/*.md`) come with matching test changes in the same commit
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] Schema changes bump `schema_version` and document a migration path
- [ ] Commits follow Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`)
