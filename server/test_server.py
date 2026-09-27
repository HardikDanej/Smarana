"""
Automated tests for server.py's tool logic: path-traversal guards on
_resolve, read_file/write_file/list_files/list_projects round-tripping, and
a regression test for the empty-string SMARANA_DATA_ROOT bug we hit and
fixed by hand while testing manually.

Deliberately does NOT test the OAuth flow — that has its own end-to-end
smoke test (test_oauth_flow.py) against a live tunnel, since OAuth's
issuer/redirect URLs are inherently about a real public origin, not
something worth faking here.

Run with (from inside server/):
    ../.venv/Scripts/python -m unittest test_server -v      # Windows
    ../.venv/bin/python -m unittest test_server -v          # macOS/Linux
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Module-level env setup MUST happen before `import server`, since server.py
# reads these at import time. Explicitly blanking SMARANA_PUBLIC_HOST/
# SMARANA_LOGIN_PASSWORD keeps this hermetic even if a real server/.env
# exists on the machine running the tests (load_dotenv does not override
# already-set os.environ values).
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="smarana-test-data-"))
os.environ["SMARANA_DATA_ROOT"] = str(_TMP_ROOT)
os.environ["SMARANA_PUBLIC_HOST"] = ""
os.environ["SMARANA_LOGIN_PASSWORD"] = ""

import server  # noqa: E402  (import must follow the env setup above)


def tearDownModule():
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


class TestResolve(unittest.TestCase):
    def test_rejects_traversal_in_project_name(self):
        for bad in ["..", "../escape", "a/b", "a\\b", ""]:
            with self.assertRaises(ValueError, msg=f"project={bad!r} should have been rejected"):
                server._resolve(bad, "MEMORY.md")

    def test_rejects_traversal_in_filename(self):
        for bad in ["..", "../escape", "a/b", "a\\b", ""]:
            with self.assertRaises(ValueError, msg=f"filename={bad!r} should have been rejected"):
                server._resolve("resolve-valid-project", bad)

    def test_accepts_ordinary_project_and_filename(self):
        path = server._resolve("resolve-ordinary-project", "MEMORY.md")
        self.assertEqual(path.name, "MEMORY.md")
        self.assertEqual(path.parent, (_TMP_ROOT / "resolve-ordinary-project").resolve())

    def test_project_name_with_space_is_valid(self):
        """Real Claude Project names contain spaces, e.g. "The War Room" —
        must not be rejected as traversal."""
        path = server._resolve("The War Room", "MEMORY.md")
        self.assertEqual(path.parent.name, "The War Room")


class TestReadWriteFile(unittest.TestCase):
    def test_read_missing_file_returns_empty_string(self):
        self.assertEqual(server.read_file(project="rw-never-written"), "")

    def test_write_then_read_roundtrips_exactly(self):
        content = "# MEMORY.md\nhello\nmultiple lines\n"
        result = server.write_file(project="rw-roundtrip", content=content)
        self.assertIn("wrote", result)
        self.assertEqual(server.read_file(project="rw-roundtrip"), content)

    def test_write_overwrites_previous_content(self):
        server.write_file(project="rw-overwrite", content="first version")
        server.write_file(project="rw-overwrite", content="second version")
        self.assertEqual(server.read_file(project="rw-overwrite"), "second version")

    def test_custom_filename_is_independent_of_default(self):
        server.write_file(project="rw-custom-filename", content="notes content", filename="notes.md")
        self.assertEqual(
            server.read_file(project="rw-custom-filename", filename="notes.md"), "notes content"
        )
        # the default MEMORY.md was never written for this project
        self.assertEqual(server.read_file(project="rw-custom-filename"), "")


class TestListFiles(unittest.TestCase):
    def test_empty_for_project_that_was_never_written(self):
        self.assertEqual(server.list_files(project="list-files-never-created"), [])

    def test_lists_written_file(self):
        server.write_file(project="list-files-one", content="x")
        self.assertEqual(server.list_files(project="list-files-one"), ["MEMORY.md"])

    def test_lists_multiple_files_sorted(self):
        server.write_file(project="list-files-multi", content="a", filename="b.md")
        server.write_file(project="list-files-multi", content="c", filename="a.md")
        self.assertEqual(server.list_files(project="list-files-multi"), ["a.md", "b.md"])


class TestListProjects(unittest.TestCase):
    def test_includes_project_after_write(self):
        server.write_file(project="list-projects-marker", content="x")
        self.assertIn("list-projects-marker", server.list_projects())

    def test_excludes_project_never_written(self):
        self.assertNotIn("list-projects-definitely-not-created", server.list_projects())


class TestDataRootEnvHandling(unittest.TestCase):
    """Regression test for the bug we hit and fixed by hand: an env var
    that's PRESENT but set to an empty string is not the same as an ABSENT
    env var. `os.environ.get(key, default)` only applies `default` in the
    absent case — an empty string sails through unchanged and was silently
    resolving DATA_ROOT to server/ itself instead of server/data/."""

    def setUp(self):
        self._original = os.environ.get("SMARANA_DATA_ROOT")

    def tearDown(self):
        if self._original is None:
            os.environ.pop("SMARANA_DATA_ROOT", None)
        else:
            os.environ["SMARANA_DATA_ROOT"] = self._original

    def test_empty_string_env_value_falls_back_to_default(self):
        os.environ["SMARANA_DATA_ROOT"] = ""
        result = server._resolve_data_root()
        expected_default = (Path(server.__file__).parent / "data").resolve()
        self.assertEqual(result, expected_default)

    def test_absent_env_value_falls_back_to_default(self):
        os.environ.pop("SMARANA_DATA_ROOT", None)
        result = server._resolve_data_root()
        expected_default = (Path(server.__file__).parent / "data").resolve()
        self.assertEqual(result, expected_default)

    def test_real_path_env_value_is_honored(self):
        real_path = str(_TMP_ROOT)
        os.environ["SMARANA_DATA_ROOT"] = real_path
        result = server._resolve_data_root()
        self.assertEqual(result, Path(real_path).resolve())


class TestSearchMemoryIntegration(unittest.TestCase):
    """Proves the actual wiring — write_file indexing aged-out content,
    search_memory finding it — through the real server functions, not just
    memory_index.py in isolation."""

    def test_write_file_indexes_and_search_memory_finds_it(self):
        content = (
            "## Tier 2 — System Architecture & Decisions\n"
            "- [ADR-020] 2026-08-01 — Session-cookie auth. Status: superseded (by ADR-021)\n"
        )
        result = server.write_file(project="search-integration", content=content)
        self.assertIn("indexed 1 aged-out line(s)", result)

        hits = server.search_memory(project="search-integration", query="session cookies", top_k=3)
        self.assertEqual(len(hits), 1)
        self.assertIn("ADR-020", hits[0])

    def test_search_memory_empty_for_unindexed_project(self):
        hits = server.search_memory(project="search-integration-never-written", query="anything")
        self.assertEqual(hits, [])

    def test_write_file_with_no_indexable_content_reports_no_index_note(self):
        result = server.write_file(project="search-integration-plain", content="# just a title\n")
        self.assertNotIn("indexed", result)

    def test_search_memory_rejects_traversal_in_project(self):
        with self.assertRaises(ValueError):
            server.search_memory(project="../escape", query="x")


if __name__ == "__main__":
    unittest.main()
