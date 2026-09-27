"""
Filesystem object store (Plan Step 90): the first concrete ObjectStore.

Content-addressed by design: the reference IS the sha256 of the bytes,
so storing the same file twice is a no-op (the second `put()` returns
the same reference without writing a second copy) and a caller can
verify integrity themselves by re-hashing what `get()` returns. No
metadata database, no directory structure beyond `root/<hash>` -- a
production object store is expected to layer that on top; inventing it
here would be exactly the kind of scope this dev-scale adapter doesn't
need.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class ObjectNotFoundError(KeyError):
    """Raised by get() for a reference this store never received."""


class FilesystemObjectStore:
    """Implements memory_os.object_store.ObjectStore."""

    def __init__(self, root: "str | Path"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self._path_for(digest)
        if not path.exists():
            path.write_bytes(data)
        return digest

    def get(self, object_ref: str) -> bytes:
        path = self._path_for(object_ref)
        if not path.exists():
            raise ObjectNotFoundError(object_ref)
        return path.read_bytes()

    def _path_for(self, digest: str) -> Path:
        return self.root / digest
