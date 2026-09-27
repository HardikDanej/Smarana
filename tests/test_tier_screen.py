"""
Tests for scripts/tier_screen.py — the optional local Laya cross-check
described in workflows/tier-screen.md and SKILL.md Phase 2.

Run with:
    python3 -m unittest tests/test_tier_screen.py -v

Scope: this tests the script's deterministic input-parsing and
error-handling contract only — the same "always emit one line of valid
JSON, never crash, never fabricate a result" guarantee the Sot Engi
gate-screen precedent established for this pattern. It substitutes a fake
`laya` module via `sys.modules` so these tests run offline, in
milliseconds, with no model download and no real inference — consistent
with this repo's existing rule that only the deterministic parts of the
pipeline are covered by the automated suite (see tests/README.md).
Verifying real Laya inference is a manual step; see scripts/README.md.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

# Allow this file to be run either from inside tests/ or from the repo root,
# matching test_pipeline.py's own convention.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tier_screen  # noqa: E402


class FakeAgent:
    """Stand-in for laya.load(...)'s return value."""

    def __init__(self, answers=None, raise_on_predict=None):
        self._answers = answers or {}
        self._raise_on_predict = raise_on_predict

    def predict(self, state, questions):
        if self._raise_on_predict is not None:
            raise self._raise_on_predict
        return {"answers": self._answers}


def fake_laya_module(agent=None, raise_on_load=None):
    fake = mock.MagicMock()
    if raise_on_load is not None:
        fake.load.side_effect = raise_on_load
    else:
        fake.load.return_value = agent or FakeAgent()
    return fake


class TestLoadPayload(unittest.TestCase):
    """load_payload never touches laya at all -- pure input handling."""

    def test_missing_file_reports_error(self):
        payload, err = tier_screen.load_payload(["tier_screen.py", "/no/such/file.json"])
        self.assertIsNone(payload)
        self.assertIn("could not read input file", err)

    def test_invalid_json_reports_error(self, tmp_path=None):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            path = f.name
        try:
            payload, err = tier_screen.load_payload(["tier_screen.py", path])
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertIsNone(payload)
        self.assertIn("invalid JSON input", err)

    def test_empty_file_is_empty_object_not_an_error(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("")
            path = f.name
        try:
            payload, err = tier_screen.load_payload(["tier_screen.py", path])
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertIsNone(err)
        self.assertEqual(payload, {})

    def test_valid_json_file_round_trips(self):
        import tempfile
        obj = {"candidate_text": "Always use named exports.", "existing_context": ""}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(obj, f)
            path = f.name
        try:
            payload, err = tier_screen.load_payload(["tier_screen.py", path])
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertIsNone(err)
        self.assertEqual(payload, obj)


class TestRunScreenDegradedMode(unittest.TestCase):
    """run_screen must degrade to the empty-result shape on every failure
    mode, and never raise."""

    def test_laya_not_importable(self):
        with mock.patch.dict(sys.modules, {"laya": None}):
            result = tier_screen.run_screen({"candidate_text": "x"})
        self.assertIsNone(result["tier_placement"])
        self.assertIsNone(result["contradicts_existing_decision"]["probability"])
        self.assertFalse(result["contradicts_existing_decision"]["flagged"])
        self.assertIsNone(result["duplicate_or_noop"]["probability"])
        self.assertIn("laya not importable", result["error"])
        self.assertEqual(result["flag_threshold"], tier_screen.FLAG_THRESHOLD)

    def test_laya_load_failure(self):
        fake = fake_laya_module(raise_on_load=RuntimeError("checkpoint fetch failed"))
        with mock.patch.dict(sys.modules, {"laya": fake}):
            result = tier_screen.run_screen({"candidate_text": "x"})
        self.assertIsNone(result["tier_placement"])
        self.assertIn("laya model load failed", result["error"])

    def test_laya_inference_failure(self):
        agent = FakeAgent(raise_on_predict=RuntimeError("OOM"))
        fake = fake_laya_module(agent=agent)
        with mock.patch.dict(sys.modules, {"laya": fake}):
            result = tier_screen.run_screen({"candidate_text": "x"})
        self.assertIsNone(result["tier_placement"])
        self.assertIn("laya inference failed", result["error"])


class TestRunScreenSuccess(unittest.TestCase):
    """run_screen must correctly translate a well-formed laya response into
    this script's own output contract."""

    def test_tier_placement_and_cross_checks_parsed(self):
        answers = {
            "tier_placement": {
                "type": "choice",
                "choice": "tier2_architecture_decision",
                "probabilities": {
                    "tier1_active_execution": 0.05,
                    "tier2_architecture_decision": 0.88,
                    "tier3_domain_rule": 0.07,
                },
                "confidence": 0.83,
            },
            "contradicts_existing_decision": {"type": "noul", "noul": 0.91},
            "duplicate_or_noop": {"type": "noul", "noul": 0.02},
        }
        fake = fake_laya_module(agent=FakeAgent(answers=answers))
        with mock.patch.dict(sys.modules, {"laya": fake}):
            result = tier_screen.run_screen(
                {"candidate_text": "Switched session storage to Postgres.",
                 "existing_context": "[ADR-002] Session storage: Redis."}
            )

        self.assertIsNone(result["error"])
        self.assertEqual(result["tier_placement"]["choice"], "tier2_architecture_decision")
        self.assertEqual(
            result["tier_placement"]["probabilities"]["tier2_architecture_decision"], 0.88
        )
        self.assertEqual(result["contradicts_existing_decision"]["probability"], 0.91)
        self.assertTrue(result["contradicts_existing_decision"]["flagged"])
        self.assertEqual(result["duplicate_or_noop"]["probability"], 0.02)
        self.assertFalse(result["duplicate_or_noop"]["flagged"])
        self.assertIsInstance(result["latency_ms"], float)

    def test_flag_threshold_boundary_is_inclusive(self):
        answers = {
            "tier_placement": {"choice": "tier1_active_execution", "probabilities": {}, "confidence": 0.5},
            "contradicts_existing_decision": {"noul": tier_screen.FLAG_THRESHOLD},
            "duplicate_or_noop": {"noul": tier_screen.FLAG_THRESHOLD - 0.0001},
        }
        fake = fake_laya_module(agent=FakeAgent(answers=answers))
        with mock.patch.dict(sys.modules, {"laya": fake}):
            result = tier_screen.run_screen({"candidate_text": "x"})

        self.assertTrue(result["contradicts_existing_decision"]["flagged"])
        self.assertFalse(result["duplicate_or_noop"]["flagged"])

    def test_missing_candidate_text_does_not_crash(self):
        fake = fake_laya_module(agent=FakeAgent(answers={}))
        with mock.patch.dict(sys.modules, {"laya": fake}):
            result = tier_screen.run_screen({})
        self.assertIsNone(result["error"])
        self.assertIsNone(result["tier_placement"])


class TestMainEndToEnd(unittest.TestCase):
    """main() ties load_payload + run_screen together and always emits
    exactly one JSON line via emit()."""

    def test_main_emits_error_json_on_bad_path(self):
        printed = []
        with mock.patch.object(tier_screen, "emit", printed.append):
            tier_screen.main(["tier_screen.py", "/no/such/file.json"])
        self.assertEqual(len(printed), 1)
        self.assertIn("could not read input file", printed[0]["error"])
        self.assertIsNone(printed[0]["tier_placement"])

    def test_main_runs_screen_on_valid_input(self):
        import tempfile
        obj = {"candidate_text": "Fix null pointer in checkout.ts."}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(obj, f)
            path = f.name

        answers = {
            "tier_placement": {"choice": "tier1_active_execution", "probabilities": {}, "confidence": 0.7},
            "contradicts_existing_decision": {"noul": 0.01},
            "duplicate_or_noop": {"noul": 0.01},
        }
        fake = fake_laya_module(agent=FakeAgent(answers=answers))

        printed = []
        try:
            with mock.patch.dict(sys.modules, {"laya": fake}), \
                 mock.patch.object(tier_screen, "emit", printed.append):
                tier_screen.main(["tier_screen.py", path])
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(len(printed), 1)
        self.assertIsNone(printed[0]["error"])
        self.assertEqual(printed[0]["tier_placement"]["choice"], "tier1_active_execution")


if __name__ == "__main__":
    unittest.main()
