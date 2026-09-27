"""
Phase 20 (Plan Step 99): adapter certification. Every check in
conformance.CONFORMANCE_CHECKS runs against both real StorageAdapter
implementations this codebase ships -- not proof they're identical
inside, proof they're behaviorally interchangeable at the Protocol
boundary, which is the actual contract the plan's own gap list named as
missing.
"""

import pytest

from adapters.sqlite_adapter import SQLiteAdapter
from conformance import CONFORMANCE_CHECKS
from conformance.storage_adapter import assert_satisfies_storage_adapter_protocol


def _sqlite_factory():
    return SQLiteAdapter()


def _postgres_factory():
    import psycopg2

    from adapters.postgres_adapter import PostgresAdapter

    try:
        db = PostgresAdapter(host="localhost", dbname="memory_os_dev", user="memory_os", password="memory_os_dev")
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable for conformance testing: {exc}")
        return None
    with db._conn.cursor() as cur:
        cur.execute("TRUNCATE memories, relationships")
    return db


@pytest.mark.parametrize("make_adapter", [_sqlite_factory, _postgres_factory], ids=["sqlite", "postgres"])
@pytest.mark.parametrize("check", CONFORMANCE_CHECKS, ids=[c.__name__ for c in CONFORMANCE_CHECKS])
def test_conformance_check(check, make_adapter):
    check(make_adapter)


def test_a_deliberately_broken_adapter_fails_certification():
    # Positive control, same discipline as the isolation gate scripts:
    # prove the suite can actually catch a real violation before trusting
    # a clean run above. A stub that never persists anything should fail
    # the very first round-trip check.
    class BrokenAdapter:
        def store(self, memory):
            pass

        def get(self, memory_id):
            return None

        def update(self, memory):
            pass

        def delete(self, memory_id):
            pass

        def search(self, query, top_k=10):
            return []

        def list_all(self):
            return []

    assert_satisfies_storage_adapter_protocol(BrokenAdapter)  # shape is fine
    with pytest.raises(AssertionError):
        for check in CONFORMANCE_CHECKS:
            check(BrokenAdapter)
