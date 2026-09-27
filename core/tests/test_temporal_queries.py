from datetime import datetime, timedelta, timezone

from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import MemoryScope, SemanticType, SourceType, mark_superseded
from memory_os.models import MemoryObject
from memory_os.retrieval import TemporalRetriever


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def test_valid_now_finds_a_memory_with_no_expiry():
    db = SQLiteAdapter()
    memory = _memory("Project Alpha uses GCP.", valid_from=datetime.now(timezone.utc) - timedelta(days=1))
    db.store(memory)

    results = TemporalRetriever(db).valid_now()

    assert any(r.memory.id == memory.id for r in results)


def test_valid_now_excludes_an_expired_memory():
    db = SQLiteAdapter()
    expired = _memory(
        "Project Alpha used AWS.",
        valid_from=datetime.now(timezone.utc) - timedelta(days=100),
        valid_until=datetime.now(timezone.utc) - timedelta(days=50),
    )
    db.store(expired)

    results = TemporalRetriever(db).valid_now()

    assert not any(r.memory.id == expired.id for r in results)


def test_changed_between_finds_a_transition_that_started_in_the_window():
    db = SQLiteAdapter()
    # Step 57: "What changed between January and June?"
    started_in_window = _memory("Project Alpha adopted GCP.", valid_from=_dt("2026-03-01"))
    started_before_window = _memory("Project Alpha adopted AWS.", valid_from=_dt("2025-01-01"))
    db.store(started_in_window)
    db.store(started_before_window)

    results = TemporalRetriever(db).changed_between(_dt("2026-01-01"), _dt("2026-06-01"))

    ids = {r.memory.id for r in results}
    assert started_in_window.id in ids
    assert started_before_window.id not in ids


def test_changed_between_finds_a_transition_that_ended_in_the_window():
    db = SQLiteAdapter()
    ended_in_window = _memory(
        "Project Alpha stopped using AWS.",
        valid_from=_dt("2025-01-01"),
        valid_until=_dt("2026-04-01"),
    )
    db.store(ended_in_window)

    results = TemporalRetriever(db).changed_between(_dt("2026-01-01"), _dt("2026-06-01"))

    assert any(r.memory.id == ended_in_window.id for r in results)


def test_changed_between_is_open_ended_when_no_end_given():
    db = SQLiteAdapter()
    recent = _memory("Project Alpha adopted GCP.", valid_from=_dt("2026-06-01"))
    db.store(recent)

    results = TemporalRetriever(db).changed_between(_dt("2026-01-01"))

    assert any(r.memory.id == recent.id for r in results)


def test_previous_state_walks_one_hop_back_via_supersedes():
    db = SQLiteAdapter()
    old = _memory("Project Alpha uses AWS.")
    new = _memory("Project Alpha uses GCP.")
    updated_old, updated_new = mark_superseded(old, new)
    db.store(updated_old)
    db.store(updated_new)

    previous = TemporalRetriever(db).previous_state(updated_new.id)

    assert previous is not None
    assert previous.id == updated_old.id


def test_previous_state_is_none_for_a_memory_with_no_prior_version():
    db = SQLiteAdapter()
    memory = _memory("A first-ever fact.")
    db.store(memory)

    assert TemporalRetriever(db).previous_state(memory.id) is None
