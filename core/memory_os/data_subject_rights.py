"""
Data subject rights (Phase 22): the compliance target named this phase
is GDPR (see docs/GDPR_COMPLIANCE.md for the full article-by-article
mapping of what this codebase provides against what GDPR actually
requires, and what stays an organizational responsibility no code can
discharge). This module is the part GDPR itself calls a technical
measure, not a policy: Articles 15 (right of access), 17 (right to
erasure), and 20 (data portability) as real, callable operations over
`MemoryObject.data_subject_ids` (Phase 22's other addition).

Deliberately regime-agnostic in its own name and code: a "data subject"
and their personal data are GDPR's own terms (Article 4(1)), but nothing
here imports or depends on GDPR-specific vocabulary beyond the
docstrings. A CCPA "right to delete" / "right to know" request needs the
exact same two operations.
"""

from __future__ import annotations

from .models import MemoryObject
from .storage import StorageAdapter


def find_memories_for_data_subject(storage: StorageAdapter, data_subject_id: str) -> list[MemoryObject]:
    """Every memory whose `data_subject_ids` names this person."""
    return [m for m in storage.list_all() if data_subject_id in m.data_subject_ids]


def export_data_subject(storage: StorageAdapter, data_subject_id: str) -> list[dict]:
    """Article 15 (right of access) / Article 20 (data portability):
    every memory referencing this data subject, as plain
    JSON-serializable dicts -- the same round-trippable shape
    backup.py's export_memories() already uses, since "portable" means
    the same thing in both cases."""
    return [m.model_dump(mode="json") for m in find_memories_for_data_subject(storage, data_subject_id)]


def erase_data_subject(storage: StorageAdapter, data_subject_id: str) -> int:
    """Article 17 (right to erasure): genuinely deletes -- not
    retention.py's FORGOTTEN marker. Phase 21's tenant retention sweep
    keeps history on purpose (Step 35's "a memory never silently
    disappears"); an Article 17 request is GDPR's own deliberate
    exception to that default. A specific person's personal data must
    actually be removable on request, not merely marked inactive and
    still sitting there. Returns how many memories were deleted."""
    memories = find_memories_for_data_subject(storage, data_subject_id)
    for memory in memories:
        storage.delete(memory.id)
    return len(memories)
