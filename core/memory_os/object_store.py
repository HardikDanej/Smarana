"""
Object storage interface (Plan Step 90): binary/file memory.

`MemoryObject.content` is a `str` -- right for the text-shaped memory
every earlier phase dealt with, but `Modality` (Step 7) already names
types that aren't text at all: FILES, BINARY_OBJECT, IMAGE, AUDIO,
VIDEO. Nothing before this phase gave those modalities anywhere to put
the actual bytes; `content` had to stand in for a caption/description at
best, with the real file living nowhere the system knew about.

ObjectStore is a Protocol, the same shape as every other core interface
(LLMProvider, Embedder, Encryptor, StorageAdapter): memory_os names the
capability -- store bytes, get them back by an opaque reference --
without importing a concrete blob-storage technology.
FilesystemObjectStore (core/adapters) is the first implementation; an
S3-backed one later is a drop-in swap, the same way OpenAIProvider would
swap in for ClaudeProvider.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStore(Protocol):
    def put(self, data: bytes) -> str:
        """Stores raw bytes, returns an opaque reference string a
        MemoryObject's `object_ref` can hold."""
        ...

    def get(self, object_ref: str) -> bytes:
        """Raises KeyError (or a subclass) if object_ref is unknown."""
        ...
