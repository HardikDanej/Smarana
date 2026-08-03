# Tests

Run from the repository root with:

```bash
pip install -r requirements-dev.txt
```

```bash
python -m unittest discover -s tests -v
```

`smriti_lib.py` is a reference implementation of the deterministic scaffolding described in `SKILL.md` and `workflows/*.md`: schema validation, Markdown rendering, consolidation/GC, and the idempotency check.

## What's covered

- The schema itself is valid Draft-07.
- `initialize-memory.md`'s bootstrap skeleton validates and never fabricates a Tier 3 rule.
- `consolidate-memory.md`'s worked example (three done Tier 1 tasks + one superseded ADR collapsing into two changelog lines) is reproduced exactly and asserted against.
- The Hard Constraints: `blocked` and `in_progress` items never collapse regardless of age; Tier 3 is never pruned by volume.
- The 120-line / ~800-token hard cap actually gets enforced on a synthetic oversized state, and consolidation does not over-prune a state that's already under cap.
- `mcp-handshake.md`'s idempotency check: running consolidation twice produces no further diff, and a real change is correctly detected as not a no-op.
- The populated `examples/MEMORY.md` reference object validates against the schema.

## What's not covered

Phase 2, Tier Resolution, isn't a pure function. Deciding which tier a new, freeform fact belongs to is a judgment call Claude makes at runtime using the resolution procedure in `SKILL.md`, not something a deterministic test can assert against without an LLM in the loop. This harness starts from already-classified data and tests everything downstream of that judgment call.
