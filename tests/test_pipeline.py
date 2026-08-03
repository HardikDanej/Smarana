"""
Functional test harness for the deterministic scaffolding described in
SKILL.md and workflows/*.md.

Run with:
    python3 -m unittest tests/test_pipeline.py -v

Scope: this tests the parts of the pipeline that are deterministic and
therefore verifiable without an LLM in the loop:
  - schema conformance at every phase boundary
  - initialize-memory.md's bootstrap skeleton
  - consolidate-memory.md's dedup / collapse / hard-cap enforcement,
    checked against the exact worked example in that file
  - the Hard Constraint that blocked/in_progress items never collapse
  - mcp-handshake.md's idempotency check

It does NOT test Phase 2 (Tier Resolution) as a classifier, since which tier
a freeform fact belongs to is a runtime judgment call, not a pure function.
"""

import sys
import unittest
from pathlib import Path

# Allow this file to be run either from inside tests/ or from the repo root
# (python -m unittest tests/test_pipeline.py), which is what the README documents.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from smriti_lib import (
    approx_token_count,
    consolidate,
    empty_state,
    is_noop,
    line_count,
    load_schema,
    render_markdown,
    validate,
)


class TestSchema(unittest.TestCase):
    def test_schema_itself_is_valid_draft7(self):
        import jsonschema

        jsonschema.Draft7Validator.check_schema(load_schema())


class TestInitialize(unittest.TestCase):
    """Mirrors workflows/initialize-memory.md Step 2 + Step 3."""

    def test_bootstrap_skeleton_validates(self):
        state = empty_state("Test Project", "2026-08-03T09:00:00Z")
        validate(state)  # raises on failure

    def test_bootstrap_has_all_four_arrays_even_if_empty(self):
        state = empty_state("Test Project", "2026-08-03T09:00:00Z")
        for key in (
            "tier3_domain_rules",
            "tier2_architecture_log",
            "tier1_active_tasks",
            "compressed_changelog",
        ):
            self.assertIn(key, state)

    def test_bootstrap_never_fabricates_a_tier3_rule(self):
        state = empty_state("Test Project", "2026-08-03T09:00:00Z")
        self.assertEqual(state["tier3_domain_rules"], [])


class TestConsolidateWorkedExample(unittest.TestCase):
    """
    Reproduces the exact worked example in workflows/consolidate-memory.md
    Step 2 and checks the output matches: three Tier 1 dones + one superseded
    Tier 2 ADR, collapsing into exactly two changelog lines.
    """

    def setUp(self):
        self.state = {
            "schema_version": "2.0.0",
            "project_name": "Auth Migration",
            "last_updated": "2026-07-19T00:00:00Z",
            "tier3_domain_rules": [],
            "tier2_architecture_log": [
                {
                    "id": "ADR-003",
                    "date": "2026-07-13",
                    "decision": "Session-cookie auth.",
                    "rationale": "Fastest path to a working login flow.",
                    "status": "superseded",
                    "supersedes": None,
                },
                {
                    "id": "ADR-006",
                    "date": "2026-07-18",
                    "decision": "JWT-based auth.",
                    "rationale": "Needed stateless auth for horizontal scaling.",
                    "status": "active",
                },
            ],
            "tier1_active_tasks": [
                {"task": "Migrate auth middleware to JWT", "status": "done", "updated": "2026-07-13"},
                {"task": "Fix session race condition in login flow", "status": "done", "updated": "2026-07-15"},
                {"task": "Add refresh-token rotation", "status": "done", "updated": "2026-07-18"},
            ],
            "compressed_changelog": [],
        }

    def test_pre_state_validates(self):
        validate(self.state)

    def test_collapse_produces_two_lines_from_four_source_items(self):
        # today is far enough past the newest item (2026-07-18) to trigger
        # the >7-day aging rule
        today = "2026-07-26"

        # Force the cap check to trip regardless of natural size, isolating
        # the collapse logic itself (over_cap gating is tested separately).
        import smriti_lib

        original_over_cap = smriti_lib.over_cap
        smriti_lib.over_cap = lambda s: True
        try:
            result = consolidate(self.state, today)
        finally:
            smriti_lib.over_cap = original_over_cap

        self.assertEqual(len(result["compressed_changelog"]), 2)
        self.assertEqual(len(result["tier1_active_tasks"]), 0)
        self.assertEqual(len(result["tier2_architecture_log"]), 1)
        self.assertEqual(result["tier2_architecture_log"][0]["id"], "ADR-006")
        validate(result)

    def test_result_validates_against_schema(self):
        import smriti_lib

        original_over_cap = smriti_lib.over_cap
        smriti_lib.over_cap = lambda s: True
        try:
            result = consolidate(self.state, "2026-07-26")
        finally:
            smriti_lib.over_cap = original_over_cap
        validate(result)


class TestHardConstraints(unittest.TestCase):
    def test_blocked_item_never_collapses_regardless_of_age(self):
        state = empty_state("P", "2026-01-01T00:00:00Z")
        state["tier1_active_tasks"] = [
            {"task": "Old blocked thing", "status": "blocked", "blocked_reason": "waiting on vendor", "updated": "2020-01-01"}
        ]
        import smriti_lib

        original_over_cap = smriti_lib.over_cap
        smriti_lib.over_cap = lambda s: True
        try:
            result = consolidate(state, "2026-08-03")
        finally:
            smriti_lib.over_cap = original_over_cap

        self.assertEqual(len(result["tier1_active_tasks"]), 1)
        self.assertEqual(result["tier1_active_tasks"][0]["status"], "blocked")

    def test_in_progress_item_never_collapses_regardless_of_age(self):
        state = empty_state("P", "2026-01-01T00:00:00Z")
        state["tier1_active_tasks"] = [
            {"task": "Old in-progress thing", "status": "in_progress", "updated": "2020-01-01"}
        ]
        import smriti_lib

        original_over_cap = smriti_lib.over_cap
        smriti_lib.over_cap = lambda s: True
        try:
            result = consolidate(state, "2026-08-03")
        finally:
            smriti_lib.over_cap = original_over_cap

        self.assertEqual(len(result["tier1_active_tasks"]), 1)

    def test_tier3_never_pruned_by_volume(self):
        state = empty_state("P", "2026-01-01T00:00:00Z")
        state["tier3_domain_rules"] = [f"Rule number {i}" for i in range(50)]
        import smriti_lib

        original_over_cap = smriti_lib.over_cap
        smriti_lib.over_cap = lambda s: True
        try:
            result = consolidate(state, "2026-08-03")
        finally:
            smriti_lib.over_cap = original_over_cap

        self.assertEqual(len(result["tier3_domain_rules"]), 50)


class TestHardCapEnforcement(unittest.TestCase):
    def test_synthetic_oversized_state_is_reduced(self):
        """Build a state well over 120 lines and confirm consolidate() cuts it down."""
        state = empty_state("Big Project", "2026-08-03T00:00:00Z")
        state["tier1_active_tasks"] = [
            {"task": f"Shipped feature {i}", "status": "done", "updated": "2026-07-01"}
            for i in range(80)
        ]
        state["tier2_architecture_log"] = [
            {
                "id": f"ADR-{i:03d}",
                "date": "2026-07-01",
                "decision": f"Old decision {i}, later replaced.",
                "rationale": "No longer relevant.",
                "status": "superseded",
                "supersedes": None,
            }
            for i in range(1, 40)
        ]

        md_before = render_markdown(state)
        self.assertGreater(line_count(md_before), 120)

        result = consolidate(state, "2026-08-03")
        md_after = render_markdown(result)

        self.assertLessEqual(line_count(md_after), 120)
        self.assertLessEqual(approx_token_count(md_after), 800)
        validate(result)

    def test_does_not_over_prune_when_already_under_cap(self):
        state = empty_state("Small Project", "2026-08-03T00:00:00Z")
        before = render_markdown(state)
        result = consolidate(state, "2026-08-03")
        after = render_markdown(result)
        self.assertEqual(before, after)


class TestIdempotency(unittest.TestCase):
    """Mirrors mcp-handshake.md Step 4."""

    def test_running_consolidate_twice_is_a_noop_the_second_time(self):
        state = empty_state("P", "2026-08-03T00:00:00Z")
        first_pass = consolidate(state, "2026-08-03")
        second_pass = consolidate(first_pass, "2026-08-03")
        self.assertTrue(is_noop(first_pass, second_pass))

    def test_is_noop_detects_a_real_change(self):
        state = empty_state("P", "2026-08-03T00:00:00Z")
        changed = consolidate(state, "2026-08-03")
        changed["tier1_active_tasks"].append({"task": "New thing", "status": "todo"})
        self.assertFalse(is_noop(state, changed))


class TestExampleFile(unittest.TestCase):
    """Confirms examples/MEMORY.md (as a hand-authored reference object) still validates."""

    def test_populated_example_validates(self):
        state = {
            "schema_version": "2.0.0",
            "project_name": "Example Project",
            "last_updated": "2026-07-20T09:15:00Z",
            "tier3_domain_rules": [
                "Always use named exports, never default exports, in this codebase.",
                "Never log raw token values or PII, in any environment, including local dev.",
            ],
            "tier2_architecture_log": [
                {"id": "ADR-005", "date": "2026-07-19", "decision": "Adopted refresh-token rotation on top of JWT auth.", "rationale": "Short-lived access tokens without rotation forced re-logins too often.", "status": "active"},
                {"id": "ADR-006", "date": "2026-07-19", "decision": "Replaced session-cookie auth with JWT-based auth.", "rationale": "Needed stateless auth for horizontal scaling.", "status": "active"},
                {"id": "ADR-003", "date": "2026-07-13", "decision": "Session-cookie auth.", "rationale": "Fastest path to a working login flow for the MVP.", "status": "superseded", "supersedes": None},
            ],
            "tier1_active_tasks": [
                {"task": "Add rate limiting to the refresh-token endpoint", "status": "in_progress"},
                {"task": "Write integration tests for the rotation flow", "status": "todo"},
                {"task": "Deploy to staging", "status": "blocked", "blocked_reason": "waiting on infra team to provision the Redis instance"},
            ],
            "compressed_changelog": [
                {"range": "2026-07-13 to 2026-07-18", "summary": "Completed JWT auth migration, including refresh-token rotation and a login race-condition fix."},
                {"range": "2026-07-13 to 2026-07-18", "summary": "Replaced session-cookie auth (ADR-003) with JWT-based auth (ADR-006)."},
            ],
        }
        validate(state)


if __name__ == "__main__":
    unittest.main()
