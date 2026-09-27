"""
Tests for sakshi/: MEMORY.md parsing and brief selection, the topic taxonomy
and its Laya-scored cache-blending, the two detectors, the hook's and
laya_score.py's stdin/stdout contracts end to end (as real subprocesses, the
way Claude Code runs them), and the report's arithmetic.

What this can't test: that Claude Code actually delivers these payloads and
honours the output. That was checked by hand against a live headless session;
see sakshi/README.md, "Verification". It also can't test real Laya inference
in an environment where `laya` isn't installed (this one) — LayaTopicsIntegration
proves the cache-consuming wiring with a hand-crafted cache file instead, and
LayaScoreDegradesCleanly proves the real absence is handled cleanly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from sakshi import detectors, laya_score, memory, report, topics  # noqa: E402
from sakshi.store import Store  # noqa: E402

try:
    import laya  # noqa: F401
    LAYA_INSTALLED = True
except Exception:
    LAYA_INSTALLED = False

EXAMPLE = (REPO / "examples" / "MEMORY.md").read_text(encoding="utf-8")
HOOK = REPO / "sakshi" / "hook.py"
LAYA_SCORE = REPO / "sakshi" / "laya_score.py"


class MemoryParsing(unittest.TestCase):
    def setUp(self):
        self.mem = memory.parse_memory(EXAMPLE)

    def test_tiers_parsed(self):
        self.assertEqual(self.mem.project, "Example Project")
        self.assertEqual(len(self.mem.rules), 2)
        self.assertEqual([a.id for a in self.mem.adrs], ["ADR-005", "ADR-006", "ADR-003"])
        self.assertEqual(self.mem.adrs[2].status, "superseded")
        self.assertIn(("blocked", self.mem.tasks[3][1]), self.mem.tasks)

    def test_template_placeholders_ignored(self):
        mem = memory.parse_memory("## Tier 3 — Rules\n- <any standing constraints>\n")
        self.assertEqual(mem.rules, [])

    def test_superseded_adrs_never_selected(self):
        picked = memory.select_adrs(self.mem, "session cookie auth for the MVP login")
        self.assertNotIn("ADR-003", [a.id for a in picked])

    def test_keyword_match_ranks_relevant_adr_first(self):
        picked = memory.select_adrs(self.mem, "add rotation checks to the refresh-token flow")
        self.assertEqual(picked[0].id, "ADR-005")

    def test_no_prompt_falls_back_to_recent_active(self):
        picked = memory.select_adrs(self.mem, "")
        self.assertEqual({a.id for a in picked}, {"ADR-005", "ADR-006"})

    def test_brief_contents_and_budget(self):
        brief = memory.build_brief(self.mem, "refresh token rotation")
        self.assertIn("Never log raw token values", brief)
        self.assertIn("ADR-005", brief)
        self.assertIn("[blocked] Deploy to staging", brief)
        self.assertLessEqual(memory.approx_tokens(brief), memory.BRIEF_TOKEN_BUDGET)

    def test_tight_budget_sheds_tasks_and_adrs_before_rules(self):
        brief = memory.build_brief(self.mem, "refresh token", budget=90)
        self.assertLessEqual(memory.approx_tokens(brief), 90)
        self.assertIn("Standing rules", brief)
        self.assertNotIn("Parent's open work", brief)

    def test_empty_memory_gives_no_brief(self):
        self.assertEqual(memory.build_brief(memory.parse_memory("# MEMORY.md — x\n"), "anything"), "")

    def test_no_cache_matches_v0_behaviour_exactly(self):
        prompt = "add rotation checks to the refresh-token flow"
        base = [a.id for a in memory.select_adrs(self.mem, prompt)]
        self.assertEqual(base, [a.id for a in memory.select_adrs(self.mem, prompt, topics_cache={})])
        self.assertEqual(base, [a.id for a in memory.select_adrs(self.mem, prompt, topics_cache=None)])

    def test_cached_topic_similarity_surfaces_a_differently_worded_adr(self):
        adr005 = next(a for a in self.mem.adrs if a.id == "ADR-005")
        # Shares nothing with ADR-005's actual wording, but shares "review"
        # with ADR-006's, so ADR-006 alone would already be "matched" without
        # any topic help -- ruling out the fallback-to-most-recent path as
        # the reason ADR-005 shows up below.
        prompt = "audit review of our login credential handling"
        self.assertEqual(memory.keywords(prompt) & memory.keywords(adr005.text), set())

        without_cache = [a.id for a in memory.select_adrs(self.mem, prompt)]
        self.assertNotIn("ADR-005", without_cache)

        cache = {"ADR-005": {"hash": topics.hash_text(adr005.text), "topics": {"auth_identity": 0.9}}}
        with_cache = [a.id for a in memory.select_adrs(self.mem, prompt, topics_cache=cache)]
        self.assertIn("ADR-005", with_cache)

    def test_stale_cache_entry_is_ignored(self):
        adr005 = next(a for a in self.mem.adrs if a.id == "ADR-005")
        prompt = "audit review of our login credential handling"
        cache = {"ADR-005": {"hash": "stale-does-not-match-current-text", "topics": {"auth_identity": 0.9}}}
        picked = [a.id for a in memory.select_adrs(self.mem, prompt, topics_cache=cache)]
        self.assertNotIn("ADR-005", picked)


class Topics(unittest.TestCase):
    def test_classify_text_matches_seed_words(self):
        dist = topics.classify_text("login credential handling")
        self.assertAlmostEqual(dist.get("auth_identity", 0), 1.0)

    def test_classify_text_no_signal_is_empty(self):
        self.assertEqual(topics.classify_text("xyzzy plugh corge"), {})
        self.assertEqual(topics.classify_text(""), {})

    def test_topic_similarity(self):
        self.assertEqual(topics.topic_similarity({}, {"a": 1.0}), 0.0)
        self.assertEqual(topics.topic_similarity({"a": 0.5}, {"a": 0.5}), 0.25)
        self.assertEqual(topics.topic_similarity({"a": 1.0}, {"b": 1.0}), 0.0)

    def test_hash_text_deterministic_and_distinct(self):
        self.assertEqual(topics.hash_text("x"), topics.hash_text("x"))
        self.assertNotEqual(topics.hash_text("x"), topics.hash_text("y"))

    def test_laya_criteria_covers_every_topic(self):
        self.assertEqual(set(topics.laya_criteria()), set(topics.TOPICS))

    def test_load_adr_topics_missing_cache_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(topics.load_adr_topics(Path(d)), {})


class Detectors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "a.py"
        self.file.write_text("print('hi')\n")
        self.read = {"file_path": str(self.file)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_unchanged_reread_is_flagged(self):
        st = {}
        self.assertIsNone(detectors.check(st, "Read", self.read))
        detectors.record(st, "Read", self.read, "x" * 400)
        f = detectors.check(st, "Read", self.read)
        self.assertEqual(f.kind, "reread")
        self.assertEqual(f.avoidable_tokens, 100)

    def test_reread_after_edit_is_not_flagged(self):
        st = {}
        detectors.record(st, "Read", self.read, "x")
        detectors.record(st, "Edit", {"file_path": str(self.file), "old_string": "a", "new_string": "b"}, "ok")
        self.assertIsNone(detectors.check(st, "Read", self.read))

    def test_reread_after_out_of_band_change_is_not_flagged(self):
        st = {}
        detectors.record(st, "Read", self.read, "x")
        old = os.stat(self.file).st_mtime
        os.utime(self.file, (old + 5, old + 5))  # e.g. `sed -i` through Bash
        self.assertIsNone(detectors.check(st, "Read", self.read))

    def test_partial_read_of_a_different_range_is_not_flagged(self):
        st = {}
        detectors.record(st, "Read", self.read, "x")
        self.assertIsNone(detectors.check(st, "Read", {**self.read, "offset": 50, "limit": 20}))

    def test_reread_note_is_not_repeated_every_call(self):
        st = {}
        detectors.record(st, "Read", self.read, "x")
        self.assertIsNotNone(detectors.check(st, "Read", self.read))
        detectors.record(st, "Read", self.read, "x")
        self.assertIsNone(detectors.check(st, "Read", self.read))

    def test_third_identical_call_is_a_loop(self):
        st, inp = {}, {"pattern": "TODO", "path": "src"}
        for _ in range(2):
            self.assertIsNone(detectors.check(st, "Grep", inp))
            detectors.record(st, "Grep", inp, "no matches")
        f = detectors.check(st, "Grep", inp)
        self.assertEqual(f.kind, "loop")
        self.assertIn("no matches", f.note)

    def test_rerun_after_an_edit_is_not_a_loop(self):
        st, inp = {}, {"command": "npm test"}
        detectors.record(st, "Bash", inp, "1 failing")
        detectors.record(st, "Bash", inp, "1 failing")
        detectors.record(st, "Edit", {"file_path": str(self.file)}, "ok")
        self.assertIsNone(detectors.check(st, "Bash", inp))

    def test_ignored_tools_never_loop(self):
        st, inp = {}, {"todos": []}
        for _ in range(5):
            detectors.record(st, "TodoWrite", inp, "ok")
        self.assertIsNone(detectors.check(st, "TodoWrite", inp))

    def test_compaction_forgets_reads(self):
        st = {}
        detectors.record(st, "Read", self.read, "x")
        detectors.reset_context(st)
        self.assertIsNone(detectors.check(st, "Read", self.read))


class HookContract(unittest.TestCase):
    """Runs hook.py as a subprocess with real JSON on stdin, like Claude Code does."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "MEMORY.md").write_text(EXAMPLE, encoding="utf-8")
        self.file = self.root / "a.py"
        self.file.write_text("x = 1\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, event: dict, mode: str = "advise", raw: str | None = None):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "SAKSHI_MODE": mode}
        env.pop("SAKSHI_DIR", None)
        env.pop("SAKSHI_MEMORY", None)
        payload = raw if raw is not None else json.dumps({"session_id": "s1", "cwd": str(self.root), **event})
        p = subprocess.run([sys.executable, str(HOOK)], input=payload.encode("utf-8"),
                           capture_output=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = p.stdout.decode("utf-8").strip()
        return json.loads(out)["hookSpecificOutput"] if out else None

    def ledger(self):
        return report.read_jsonl(self.root / ".sakshi" / "ledger.jsonl")

    def read_twice(self, mode):
        ev = {"tool_name": "Read", "tool_input": {"file_path": str(self.file)}}
        self.assertIsNone(self.run_hook({"hook_event_name": "PreToolUse", **ev}, mode))
        self.run_hook({"hook_event_name": "PostToolUse", **ev, "tool_response": "x = 1"}, mode)
        return self.run_hook({"hook_event_name": "PreToolUse", **ev}, mode)

    def test_dispatch_then_subagent_start_injects_matching_brief(self):
        self.assertIsNone(self.run_hook({
            "hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"subagent_type": "Explore", "description": "audit refresh",
                           "prompt": "Check the refresh-token rotation middleware"}}))
        out = self.run_hook({"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "Explore"})
        self.assertEqual(out["hookEventName"], "SubagentStart")
        self.assertIn("ADR-005", out["additionalContext"])
        self.assertEqual(self.ledger()[-1]["kind"], "brief")

    def test_reread_in_advise_mode_adds_context(self):
        out = self.read_twice("advise")
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertIn("already read", out["additionalContext"])

    def test_reread_in_block_mode_denies(self):
        out = self.read_twice("block")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertEqual(self.ledger()[-1]["kind"], "reread_blocked")
        self.assertGreater(self.ledger()[-1]["avoided_tokens_est"], 0)

    def test_observe_mode_is_silent_but_records_would_be_interventions(self):
        self.assertIsNone(self.read_twice("observe"))
        entry = self.ledger()[-1]
        self.assertFalse(entry["applied"])
        self.assertEqual(entry["injected_tokens"], 0)

    def test_subagents_have_separate_read_state(self):
        ev = {"tool_name": "Read", "tool_input": {"file_path": str(self.file)}}
        self.run_hook({"hook_event_name": "PostToolUse", **ev, "tool_response": "x"})
        self.assertIsNone(self.run_hook({"hook_event_name": "PreToolUse", **ev,
                                         "agent_id": "sub1", "agent_type": "Explore"}))

    def test_garbage_input_exits_zero_silently(self):
        self.assertIsNone(self.run_hook({}, raw="not json"))
        self.assertIsNone(self.run_hook({"hook_event_name": "SomethingNew"}))

    def test_missing_memory_file_means_no_brief(self):
        (self.root / "MEMORY.md").unlink()
        self.assertIsNone(self.run_hook({"hook_event_name": "SubagentStart", "agent_type": "Explore"}))


class LayaTopicsIntegration(unittest.TestCase):
    """Same real hook.py subprocess as HookContract, but with a hand-crafted
    topic cache -- proving the wiring end to end without needing `laya`
    itself installed. The cache's *contents* are what laya_score.py would
    have written; see LayaScoreDegradesCleanly below for the honest check of
    what happens when laya genuinely isn't available, which is this
    environment's actual state.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "MEMORY.md").write_text(EXAMPLE, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, event: dict):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "SAKSHI_MODE": "advise"}
        env.pop("SAKSHI_DIR", None)
        env.pop("SAKSHI_MEMORY", None)
        payload = json.dumps({"session_id": "s1", "cwd": str(self.root), **event})
        p = subprocess.run([sys.executable, str(HOOK)], input=payload.encode("utf-8"),
                           capture_output=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = p.stdout.decode("utf-8").strip()
        return json.loads(out)["hookSpecificOutput"] if out else None

    def write_cache(self, entries: dict) -> None:
        path = Store(self.root / ".sakshi").path_for(topics.GLOBAL_SESSION, topics.CACHE_KEY)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"adrs": entries}), encoding="utf-8")

    def test_cached_topic_similarity_reaches_the_real_brief(self):
        mem = memory.parse_memory(EXAMPLE)
        adr005 = next(a for a in mem.adrs if a.id == "ADR-005")
        self.write_cache({"ADR-005": {"hash": topics.hash_text(adr005.text),
                                      "topics": {"auth_identity": 0.9}}})
        self.assertIsNone(self.run_hook({
            "hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"subagent_type": "Explore", "description": "creds",
                           "prompt": "audit review of our login credential handling"}}))
        out = self.run_hook({"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "Explore"})
        self.assertIn("ADR-005", out["additionalContext"])

    def test_no_cache_file_at_all_behaves_like_v0(self):
        out = self.run_hook({"hook_event_name": "SubagentStart", "agent_id": "a1",
                             "agent_type": "general-purpose"})
        self.assertIn("ADR-005", out["additionalContext"])
        self.assertIn("ADR-006", out["additionalContext"])


class LayaScoreBasics(unittest.TestCase):
    """Behaviour of laya_score.py that doesn't depend on whether `laya`
    itself is installed -- both paths return before ever importing it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_score(self, stdin: bytes = b"{}"):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        env.pop("SAKSHI_DIR", None)
        env.pop("SAKSHI_MEMORY", None)
        return subprocess.run([sys.executable, str(LAYA_SCORE)], input=stdin,
                              capture_output=True, env=env, timeout=60)

    def test_no_memory_file_is_a_silent_noop(self):
        p = self.run_score()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, b"")
        self.assertFalse((self.root / ".sakshi").exists())

    def test_garbage_stdin_does_not_crash(self):
        (self.root / "MEMORY.md").write_text(EXAMPLE, encoding="utf-8")
        p = self.run_score(stdin=b"not json")
        self.assertEqual(p.returncode, 0, p.stderr)


@unittest.skipIf(LAYA_INSTALLED, "only meaningful when laya is genuinely absent")
class LayaScoreDegradesCleanly(unittest.TestCase):
    """The real degrade path in this environment: `laya` is not installed
    (confirmed by the module-level probe above), so this is an integration
    test of actual behaviour, not a mock of a hypothetical one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "MEMORY.md").write_text(EXAMPLE, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_dependency_leaves_no_cache_and_logs_why(self):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        env.pop("SAKSHI_DIR", None)
        env.pop("SAKSHI_MEMORY", None)
        p = subprocess.run([sys.executable, str(LAYA_SCORE)], input=b"{}",
                           capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, b"")
        log = (self.root / ".sakshi" / "laya_score.log").read_text(encoding="utf-8")
        self.assertIn("laya not importable", log)
        cache_path = Store(self.root / ".sakshi").path_for(topics.GLOBAL_SESSION, topics.CACHE_KEY)
        self.assertFalse(cache_path.exists())


class Report(unittest.TestCase):
    def test_counts_and_usage_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            transcript = d / "s1.jsonl"
            msg = {"message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5,
                                                     "cache_read_input_tokens": 100,
                                                     "cache_creation_input_tokens": 0}}}
            # The same API response written as two transcript lines counts once.
            transcript.write_text(json.dumps(msg) + "\n" + json.dumps(msg) + "\n")
            (d / "s1").mkdir()
            (d / "s1" / "agent-1.jsonl").write_text(json.dumps(
                {"message": {"id": "m2", "usage": {"input_tokens": 1, "output_tokens": 1}}}) + "\n")
            data = d / ".sakshi"
            data.mkdir()
            ev = {"session": "s1", "event": "tool", "mode": "advise", "agent_id": "main",
                  "transcript": str(transcript)}
            (data / "events.jsonl").write_text("\n".join(json.dumps(x) for x in [
                {**ev, "response_tokens": 50, "repeat": False},
                {**ev, "response_tokens": 50, "repeat": True},
            ]) + "\n")
            (data / "ledger.jsonl").write_text(json.dumps(
                {"session": "s1", "kind": "reread", "applied": True, "injected_tokens": 20,
                 "avoided_tokens_est": 0}) + "\n")
            r = report.summarise(data)["s1"]
            self.assertEqual(r["tool_calls"], 2)
            self.assertEqual(r["repeat_response_tokens"], 50)
            self.assertEqual(r["interventions"], {"reread": 1})
            self.assertEqual(r["usage"]["api_calls"], 2)
            self.assertEqual(r["usage"]["cache_read_input_tokens"], 100)
            self.assertIn("Session s1", report.render({"s1": r}))


if __name__ == "__main__":
    unittest.main()
