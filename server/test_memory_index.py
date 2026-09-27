"""
Tests for memory_index.py.

TestExtractIndexableLines needs no dependency beyond memory_index's own
regex logic. TestIndexAndSearch actually exercises chromadb end to end
(local, no network after the one-time embedding-model download) — real
round-trip proof, not a mock.

Run with (from inside server/):
    ../.venv/Scripts/python -m unittest test_memory_index -v
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import memory_index

SAMPLE_MEMORY_MD = """# MEMORY.md — Example Project
Last updated: 2026-07-20T09:15:00Z

## Tier 3 — Domain Rules & User Preferences
- Always use named exports, never default exports, in this codebase.

## Tier 2 — System Architecture & Decisions
- [ADR-005] 2026-07-19 — Adopted refresh-token rotation on top of JWT auth. Status: active
- [ADR-006] 2026-07-19 — Replaced session-cookie auth with JWT-based auth. Status: active (supersedes ADR-003)
- [ADR-003] 2026-07-13 — Session-cookie auth. Status: superseded (by ADR-006)

## Tier 1 — Active Execution
- [in_progress] Add rate limiting to the refresh-token endpoint
- [todo] Write integration tests for the rotation flow

## Compressed Changelog
- [2026-07-13 to 2026-07-18]: Completed JWT auth migration, including refresh-token rotation.
- [2026-07-13 to 2026-07-18]: Replaced session-cookie auth (ADR-003) with JWT-based auth (ADR-006).
"""


class TestExtractIndexableLines(unittest.TestCase):
    def test_includes_superseded_tier2_adr(self):
        lines = memory_index.extract_indexable_lines(SAMPLE_MEMORY_MD)
        self.assertTrue(any("ADR-003" in line for line in lines))

    def test_excludes_active_tier2_adrs(self):
        lines = memory_index.extract_indexable_lines(SAMPLE_MEMORY_MD)
        self.assertFalse(any(line.startswith("- [ADR-005]") for line in lines))
        self.assertFalse(any(line.startswith("- [ADR-006]") for line in lines))

    def test_includes_all_changelog_lines(self):
        lines = memory_index.extract_indexable_lines(SAMPLE_MEMORY_MD)
        changelog_lines = [l for l in lines if l.startswith("- [2026-07-13 to 2026-07-18]")]
        self.assertEqual(len(changelog_lines), 2)

    def test_excludes_tier1_and_tier3(self):
        lines = memory_index.extract_indexable_lines(SAMPLE_MEMORY_MD)
        self.assertFalse(any("named exports" in line for line in lines))
        self.assertFalse(any("rate limiting" in line for line in lines))
        self.assertFalse(any("integration tests" in line for line in lines))

    def test_empty_content_returns_empty_list(self):
        self.assertEqual(memory_index.extract_indexable_lines(""), [])

    def test_content_with_no_matching_sections_returns_empty_list(self):
        content = "# MEMORY.md — P\n\n## Tier 1 — Active Execution\n- [todo] something\n"
        self.assertEqual(memory_index.extract_indexable_lines(content), [])


class TestIndexAndSearch(unittest.TestCase):
    """Real round-trip against a live local Chroma store — no mocking."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="smarana-index-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_search_finds_semantically_related_superseded_adr(self):
        content = """## Tier 2 — System Architecture & Decisions
- [ADR-003] 2026-07-13 — Session-cookie auth for login. Status: superseded (by ADR-006)
- [ADR-009] 2026-07-14 — Switched the payment provider from Stripe to Adyen. Status: superseded (by ADR-010)

## Compressed Changelog
- [2026-07-13 to 2026-07-18]: Deployed a new caching layer for the product catalog.
"""
        indexed = memory_index.index_content(self.tmp_dir, content)
        self.assertEqual(indexed, 3)

        results = memory_index.search(self.tmp_dir, "why did we stop using session cookies", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("ADR-003", results[0])

    def test_search_on_never_indexed_project_returns_empty(self):
        results = memory_index.search(self.tmp_dir, "anything", top_k=5)
        self.assertEqual(results, [])

    def test_reindexing_unchanged_content_does_not_duplicate(self):
        content = "## Compressed Changelog\n- [2026-07-13 to 2026-07-18]: Shipped the thing.\n"
        memory_index.index_content(self.tmp_dir, content)
        memory_index.index_content(self.tmp_dir, content)

        results = memory_index.search(self.tmp_dir, "shipped the thing", top_k=10)
        self.assertEqual(len(results), 1)

    def test_indexing_no_matching_content_is_a_noop(self):
        content = "## Tier 1 — Active Execution\n- [todo] nothing indexable here\n"
        indexed = memory_index.index_content(self.tmp_dir, content)
        self.assertEqual(indexed, 0)
        self.assertEqual(memory_index.search(self.tmp_dir, "nothing indexable", top_k=5), [])


if __name__ == "__main__":
    unittest.main()
