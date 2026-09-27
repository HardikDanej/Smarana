from datetime import datetime, timezone

from memory_os import MemoryScope, SemanticType, SourceType
from memory_os.models import MemoryObject


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _memory(**overrides) -> MemoryObject:
    defaults = dict(
        content="Project Alpha moved to GCP.",
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def test_event_time_is_valid_from():
    memory = _memory(valid_from=_dt("2026-01-01"))
    assert memory.event_time == _dt("2026-01-01")


def test_event_time_is_none_when_valid_from_unset():
    assert _memory().event_time is None


def test_knowledge_time_prefers_observed_at():
    memory = _memory(
        valid_from=_dt("2026-01-01"),
        observed_at=_dt("2026-03-01"),
    )
    assert memory.knowledge_time == _dt("2026-03-01")


def test_knowledge_time_falls_back_to_created_at_when_observed_at_unset():
    memory = _memory()
    assert memory.knowledge_time == memory.created_at


def test_plan_step_56_worked_example():
    # "Actual migration: January 2026. Memory learned: March 2026.
    # Fact valid: January 2026 -> present."
    memory = _memory(
        valid_from=_dt("2026-01-01"),
        valid_until=None,
        observed_at=_dt("2026-03-01"),
    )
    assert memory.event_time == _dt("2026-01-01")
    assert memory.knowledge_time == _dt("2026-03-01")
    assert memory.event_time < memory.knowledge_time
