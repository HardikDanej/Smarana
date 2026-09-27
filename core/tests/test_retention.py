"""Phase 21: retention sweep."""

from datetime import datetime, timedelta, timezone

from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import LifecycleState, MemoryScope, SemanticType, SourceType
from memory_os.models import MemoryObject
from memory_os.profiles import ApplicationType, BusinessType, Industry, RetentionPolicy, TenantProfile
from memory_os.retention import sweep_expired_memories


def _memory(content: str, tenant_id: str, created_at: datetime, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
        tenant_id=tenant_id,
        created_at=created_at,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def _now():
    return datetime.now(timezone.utc)


def test_sweep_marks_expired_memories_forgotten():
    db = SQLiteAdapter()
    profile = TenantProfile.for_industry(
        "tenant-a", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B,
        retention=RetentionPolicy(default_retention_days=30),
    )
    old = _memory("old note", "tenant-a", created_at=_now() - timedelta(days=60))
    db.store(old)

    swept = sweep_expired_memories(db, profile)

    assert swept == 1
    assert db.get(old.id).lifecycle_state == LifecycleState.FORGOTTEN


def test_sweep_leaves_memories_within_the_retention_window_alone():
    db = SQLiteAdapter()
    profile = TenantProfile.for_industry(
        "tenant-a", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B,
        retention=RetentionPolicy(default_retention_days=30),
    )
    recent = _memory("recent note", "tenant-a", created_at=_now() - timedelta(days=5))
    db.store(recent)

    swept = sweep_expired_memories(db, profile)

    assert swept == 0
    assert db.get(recent.id).lifecycle_state != LifecycleState.FORGOTTEN


def test_sweep_only_touches_the_profiles_own_tenant():
    db = SQLiteAdapter()
    profile = TenantProfile.for_industry(
        "tenant-a", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B,
        retention=RetentionPolicy(default_retention_days=30),
    )
    old_a = _memory("tenant a old note", "tenant-a", created_at=_now() - timedelta(days=60))
    old_b = _memory("tenant b old note", "tenant-b", created_at=_now() - timedelta(days=60))
    db.store(old_a)
    db.store(old_b)

    swept = sweep_expired_memories(db, profile)

    assert swept == 1
    assert db.get(old_a.id).lifecycle_state == LifecycleState.FORGOTTEN
    assert db.get(old_b.id).lifecycle_state != LifecycleState.FORGOTTEN


def test_sweep_never_deletes_only_marks_forgotten():
    db = SQLiteAdapter()
    profile = TenantProfile.for_industry(
        "tenant-a", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B,
        retention=RetentionPolicy(default_retention_days=30),
    )
    old = _memory("old note", "tenant-a", created_at=_now() - timedelta(days=60))
    db.store(old)

    sweep_expired_memories(db, profile)

    assert db.get(old.id) is not None  # still there, not physically deleted


def test_sweep_does_not_re_sweep_already_forgotten_memories():
    db = SQLiteAdapter()
    profile = TenantProfile.for_industry(
        "tenant-a", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B,
        retention=RetentionPolicy(default_retention_days=30),
    )
    already_forgotten = _memory(
        "already gone", "tenant-a", created_at=_now() - timedelta(days=90),
        lifecycle_state=LifecycleState.FORGOTTEN,
    )
    db.store(already_forgotten)

    swept = sweep_expired_memories(db, profile)

    assert swept == 0


def test_no_retention_window_sweeps_nothing():
    db = SQLiteAdapter()
    profile = TenantProfile.for_industry("tenant-a", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B)
    assert profile.retention.default_retention_days is None
    old = _memory("very old note", "tenant-a", created_at=_now() - timedelta(days=3650))
    db.store(old)

    swept = sweep_expired_memories(db, profile)

    assert swept == 0
    assert db.get(old.id).lifecycle_state != LifecycleState.FORGOTTEN


def test_as_of_parameter_makes_the_sweep_deterministic():
    db = SQLiteAdapter()
    profile = TenantProfile.for_industry(
        "tenant-a", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B,
        retention=RetentionPolicy(default_retention_days=30),
    )
    created = _now() - timedelta(days=20)
    memory = _memory("note", "tenant-a", created_at=created)
    db.store(memory)

    # 20 days old as of "created + 10 days" -- still within the 30-day window.
    swept_early = sweep_expired_memories(db, profile, as_of=created + timedelta(days=10))
    assert swept_early == 0

    # 20 days old as of "created + 40 days" -- 60 days old by then, expired.
    swept_late = sweep_expired_memories(db, profile, as_of=created + timedelta(days=40))
    assert swept_late == 1
