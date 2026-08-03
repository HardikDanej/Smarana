# Contributing to Smṛti

Thanks for taking the time. This document covers how to get set up, what the review bar is, and the few constraints that are non-negotiable.

## Getting set up

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
python -m venv .venv && source .venv/bin/activate # macOS / Linux
```

```bash
pip install -r requirements-dev.txt
```

```bash
python -m unittest discover -s tests -v
```

All 15 tests should pass before you start, and after you finish.

## What this repository is

Smṛti is primarily a **specification**, not a program. `SKILL.md`, `workflows/*.md`, and `schemas/memory-schema.json` are the product; the Python under `tests/` exists only to prove that the deterministic parts of that specification are internally consistent and actually enforceable.

That shapes what a good change looks like:

- **A change to the spec is the real change.** If you alter behaviour in `SKILL.md` or a workflow, the tests must change with it, in the same commit.
- **`tests/smriti_lib.py` is a reference implementation, not a library.** Nothing should import it outside `tests/`. Keep it readable over clever — it doubles as executable documentation of the spec.
- **Phase 2 (Tier Resolution) is deliberately untested.** Classifying a freeform fact into a tier is a runtime judgment call, not a pure function. Don't add tests that stub an LLM to fake it; see [`tests/README.md`](tests/README.md).

## Invariants that must not regress

These are the guarantees the whole design rests on. A change that breaks one of these will not be merged, regardless of what else it improves:

1. `MEMORY.md` never exceeds the hard cap (120 lines / ~800 tokens).
2. Tier 3 is never garbage-collected by volume pressure — append-and-supersede only.
3. `blocked` and `in_progress` Tier 1 items never collapse, regardless of age.
4. Nothing is persisted without passing Tier Resolution first.
5. Nothing is fabricated. No invented decisions, tasks, or rules.

Each of these has a corresponding test. If you find a way to violate one that the suite doesn't catch, that's a bug worth reporting on its own.

## Schema changes

`schemas/memory-schema.json` is a contract with every `MEMORY.md` already in the wild.

- Additive, optional fields → minor version bump.
- Anything that invalidates an existing file → major bump, plus a documented migration path in `CHANGELOG.md`.
- `schema_version` is a `const` in the schema. If you change the object shape, change that const, and say so in the changelog.

## Commits and pull requests

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Branch off `main`, keep one logical change per pull request.
- Update `CHANGELOG.md` under an `## [Unreleased]` heading as part of your change, not afterwards.
- CI must be green. It runs the suite on Python 3.10 through 3.13.

## Reporting problems

Bugs and feature requests go through the issue templates. Security-relevant reports do **not** — see [`SECURITY.md`](SECURITY.md).
