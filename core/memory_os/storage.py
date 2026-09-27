"""
The storage adapter interface (Plan Step 10, narrowed to what Phase 8
actually needs).

Step 10 lists a fuller interface: store/get/update/delete/search/query/
related/timeline/archive. This phase implements store/get/update/delete/
search/list_all only:

- `related()` and `timeline()` are retrieval-layer concerns (Steps 43-44)
  built on top of `list_all()` -- see retrieval.py -- not storage
  primitives. A storage adapter shouldn't need to know what "related"
  means; that's exactly the kind of logic Step 9 says belongs above the
  storage layer, not inside it.
- `query()` (structured/metadata queries) and `archive()` (lifecycle
  transition) aren't scheduled until later phases. They are deliberately
  left off this Protocol rather than stubbed with fake behavior.

Protocol, not ABC, for the same reason as LLMProvider: swapping SQLite
for Postgres or a graph store later is a matter of a new class
satisfying this shape, never a core code change.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import MemoryObject


@runtime_checkable
class StorageAdapter(Protocol):
    def store(self, memory: MemoryObject) -> None: ...

    def get(self, memory_id: str) -> MemoryObject | None: ...

    def update(self, memory: MemoryObject) -> None: ...

    def delete(self, memory_id: str) -> None: ...

    def search(self, query: str, top_k: int = 10) -> list[MemoryObject]:
        """Keyword/full-text search over stored memory content."""
        ...

    def list_all(self) -> list[MemoryObject]: ...
