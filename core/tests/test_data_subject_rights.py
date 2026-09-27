"""
Phase 22 (compliance target: GDPR): data subject rights.
Articles 15 (access), 17 (erasure), 20 (portability).
"""

import json

from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import MemoryScope, SemanticType, SourceType
from memory_os.data_subject_rights import (
    erase_data_subject,
    export_data_subject,
    find_memories_for_data_subject,
)
from memory_os.models import MemoryObject


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


def test_data_subject_ids_defaults_to_empty():
    memory = _memory("An ordinary memory with no named data subject.")
    assert memory.data_subject_ids == []


def test_find_memories_for_data_subject_matches_only_tagged_memories():
    db = SQLiteAdapter()
    patient_note = _memory("Patient prefers morning appointments.", data_subject_ids=["patient-123"])
    staff_note = _memory("Clinic closes early on Fridays.")
    db.store(patient_note)
    db.store(staff_note)

    found = find_memories_for_data_subject(db, "patient-123")

    assert [m.id for m in found] == [patient_note.id]


def test_find_memories_for_data_subject_with_no_matches_is_empty():
    db = SQLiteAdapter()
    db.store(_memory("Unrelated note."))
    assert find_memories_for_data_subject(db, "nobody-registered") == []


def test_a_memory_can_name_more_than_one_data_subject():
    db = SQLiteAdapter()
    joint_note = _memory("Couple's shared appointment.", data_subject_ids=["patient-1", "patient-2"])
    db.store(joint_note)

    assert find_memories_for_data_subject(db, "patient-1") == find_memories_for_data_subject(db, "patient-2")


def test_export_data_subject_returns_portable_json():
    db = SQLiteAdapter()
    memory = _memory("Patient prefers morning appointments.", data_subject_ids=["patient-123"])
    db.store(memory)

    exported = export_data_subject(db, "patient-123")

    json.dumps(exported)  # must not raise
    assert exported[0]["content"] == memory.content
    assert exported[0]["id"] == memory.id


def test_erase_data_subject_genuinely_deletes_not_just_forgets():
    db = SQLiteAdapter()
    memory = _memory("Patient prefers morning appointments.", data_subject_ids=["patient-123"])
    db.store(memory)

    erased = erase_data_subject(db, "patient-123")

    assert erased == 1
    assert db.get(memory.id) is None  # gone, not merely FORGOTTEN


def test_erase_data_subject_only_removes_that_persons_memories():
    db = SQLiteAdapter()
    patient_note = _memory("Patient A's note.", data_subject_ids=["patient-a"])
    other_note = _memory("Patient B's note.", data_subject_ids=["patient-b"])
    db.store(patient_note)
    db.store(other_note)

    erase_data_subject(db, "patient-a")

    assert db.get(patient_note.id) is None
    assert db.get(other_note.id) is not None


def test_erase_data_subject_with_no_matches_erases_nothing():
    db = SQLiteAdapter()
    memory = _memory("Unrelated note.")
    db.store(memory)

    erased = erase_data_subject(db, "nobody-registered")

    assert erased == 0
    assert db.get(memory.id) is not None
