"""
Retention sweep (Phase 21): gives a TenantProfile's RetentionPolicy real
teeth. `sweep_expired_memories()` marks a tenant's memories past their
retention window FORGOTTEN (Step 11's lifecycle state) -- it never
deletes, the same "a memory never silently disappears" rule Step 35's
supersession already established. A caller wanting the row physically
gone still has that: FORGOTTEN plus PolicyEngine.can_delete(), Step 80's
existing question, not a new one this module invents.

This is a plain function, not a scheduler -- no cron, no background
task. A deployer calls it periodically (an external cron job, a
scheduled task) the same way they'd run any other maintenance job; this
codebase doesn't take on scheduling infrastructure to support it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import LifecycleState
from .profiles import TenantProfile
from .storage import StorageAdapter


def sweep_expired_memories(
    storage: StorageAdapter, profile: TenantProfile, as_of: "datetime | None" = None
) -> int:
    """Marks every not-already-forgotten memory belonging to
    `profile.tenant_id` FORGOTTEN if it's older than the profile's
    retention window. A profile with no retention window
    (`default_retention_days=None`) sweeps nothing. Returns how many
    memories were swept."""
    if profile.retention.default_retention_days is None:
        return 0

    now = as_of if as_of is not None else datetime.now(timezone.utc)
    cutoff_seconds = profile.retention.default_retention_days * 86400
    swept = 0
    for memory in storage.list_all():
        if memory.tenant_id != profile.tenant_id:
            continue
        if memory.lifecycle_state == LifecycleState.FORGOTTEN:
            continue
        age_seconds = (now - memory.created_at).total_seconds()
        if age_seconds >= cutoff_seconds:
            storage.update(memory.new_version(lifecycle_state=LifecycleState.FORGOTTEN))
            swept += 1
    return swept
