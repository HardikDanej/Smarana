"""
Failure injection (Plan Step 94): a StorageAdapter wrapper that can be
told to fail on demand, so the rest of the system's behavior under a
real storage outage is provable, not assumed. "Reliability" isn't shown
by assuming failures don't happen -- it's shown by making one happen on
purpose and checking what the caller sees is a clear, typed error, never
silently wrong or missing data.

Wraps any StorageAdapter -- SQLite, Postgres, a future one -- generically.
It imports no vendor library itself and makes no storage-technology
choice of its own, so it lives here rather than in core/adapters, the
same reasoning metrics.py and backup.py's functions follow: a tool that
operates on the Protocol is not a vendor choice.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import MemoryObject
from .storage import StorageAdapter


class StorageFailure(Exception):
    """Raised by FailureInjectingStorageAdapter in place of whatever the
    real adapter would have raised -- a caller testing resilience depends
    on this one typed exception regardless of which real adapter sits
    underneath the injector."""


@dataclass
class _FailurePlan:
    methods: frozenset
    fail_after: int
    fail_count: "int | None"


class FailureInjectingStorageAdapter:
    """Implements memory_os.storage.StorageAdapter by delegating to a
    real one, except when a failure has been armed for the method being
    called. `_maybe_fail` runs before the wrapped adapter is ever
    touched, so an injected failure never partially executes against the
    real store -- the point being that a failed call leaves the
    underlying data exactly as it was before the call, provably (see
    `test_reliability.py::test_a_failed_store_never_reaches_the_real_adapter`)."""

    def __init__(self, wrapped: StorageAdapter):
        self._wrapped = wrapped
        self._plan: "_FailurePlan | None" = None
        self._calls: dict = {}

    def inject_failure(self, *methods: str, fail_after: int = 0, fail_count: "int | None" = None) -> None:
        """Arms a failure on the named StorageAdapter methods.
        `fail_after`: how many calls to that method succeed first (0 =
        fail immediately). `fail_count`: how many consecutive calls fail
        before it starts succeeding again (None = a permanent outage,
        never recovers on its own)."""
        self._plan = _FailurePlan(methods=frozenset(methods), fail_after=fail_after, fail_count=fail_count)
        self._calls = {m: 0 for m in methods}

    def clear_failure(self) -> None:
        self._plan = None
        self._calls = {}

    def _maybe_fail(self, method: str) -> None:
        if self._plan is None or method not in self._plan.methods:
            return
        call_number = self._calls.get(method, 0)
        self._calls[method] = call_number + 1
        if call_number < self._plan.fail_after:
            return
        calls_into_window = call_number - self._plan.fail_after
        if self._plan.fail_count is not None and calls_into_window >= self._plan.fail_count:
            return
        raise StorageFailure(f"injected failure on {method}() (call #{call_number + 1})")

    def store(self, memory: MemoryObject) -> None:
        self._maybe_fail("store")
        self._wrapped.store(memory)

    def get(self, memory_id: str) -> "MemoryObject | None":
        self._maybe_fail("get")
        return self._wrapped.get(memory_id)

    def update(self, memory: MemoryObject) -> None:
        self._maybe_fail("update")
        self._wrapped.update(memory)

    def delete(self, memory_id: str) -> None:
        self._maybe_fail("delete")
        self._wrapped.delete(memory_id)

    def search(self, query: str, top_k: int = 10) -> list[MemoryObject]:
        self._maybe_fail("search")
        return self._wrapped.search(query, top_k=top_k)

    def list_all(self) -> list[MemoryObject]:
        self._maybe_fail("list_all")
        return self._wrapped.list_all()
