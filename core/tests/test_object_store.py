"""Phase 17 (Plan Step 90): object/file memory."""

import pytest

from adapters.filesystem_object_store import FilesystemObjectStore, ObjectNotFoundError
from memory_os import MemoryScope, Modality, SemanticType, SourceType
from memory_os.models import MemoryObject
from memory_os.object_store import ObjectStore


def test_put_and_get_round_trips(tmp_path):
    store = FilesystemObjectStore(tmp_path)
    data = b"the actual file bytes"

    ref = store.put(data)

    assert store.get(ref) == data


def test_storing_identical_bytes_twice_is_content_addressed(tmp_path):
    store = FilesystemObjectStore(tmp_path)
    data = b"same bytes both times"

    first_ref = store.put(data)
    second_ref = store.put(data)

    assert first_ref == second_ref
    assert len(list(tmp_path.iterdir())) == 1


def test_different_bytes_get_different_references(tmp_path):
    store = FilesystemObjectStore(tmp_path)
    ref_a = store.put(b"file A")
    ref_b = store.put(b"file B")
    assert ref_a != ref_b


def test_get_unknown_reference_raises(tmp_path):
    store = FilesystemObjectStore(tmp_path)
    with pytest.raises(ObjectNotFoundError):
        store.get("not-a-real-reference")


def test_filesystem_object_store_satisfies_the_protocol(tmp_path):
    assert isinstance(FilesystemObjectStore(tmp_path), ObjectStore)


def test_memory_object_can_reference_a_stored_file(tmp_path):
    # The worked example this step exists for: a FILES-modality memory
    # whose real content lives in an ObjectStore, not in `content` --
    # content stays a human-readable caption.
    store = FilesystemObjectStore(tmp_path)
    ref = store.put(b"%PDF-1.4 fake pdf bytes")

    memory = MemoryObject(
        content="Q3 budget spreadsheet, uploaded by finance.",
        semantic_type=SemanticType.KNOWLEDGE,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.DOCUMENT,
        modality=Modality.FILES,
        object_ref=ref,
    )

    assert memory.object_ref == ref
    assert store.get(memory.object_ref) == b"%PDF-1.4 fake pdf bytes"


def test_object_ref_defaults_to_none_for_ordinary_text_memories():
    memory = MemoryObject(
        content="An ordinary text memory.",
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    assert memory.object_ref is None
