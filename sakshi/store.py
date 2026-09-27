"""
On-disk state for Sakshi: the event log, the intervention ledger, per-agent
detector state, and the queue of pending sub-agent dispatches.

Layout under the data dir (default `<cwd>/.sakshi/`):

    events.jsonl                    one line per completed tool call
    ledger.jsonl                    one line per intervention (or would-be one)
    errors.log                      hook failures; hooks themselves never fail loudly
    state/<session>/<agent>.json    detector state for one agent's context window
    state/<session>/pending.json    dispatch prompts waiting for their SubagentStart

Parallel tool calls and parallel sub-agents run their hooks concurrently, so
read-modify-write state goes through a tiny lock file. If the lock can't be
taken quickly, the caller gets None and skips the intervention: a missed
nudge is fine, a hook that stalls the session is not.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import time
from pathlib import Path

LOCK_TIMEOUT_S = 1.5
LOCK_STALE_S = 10.0


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "unknown")[:80]


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    # --- append-only logs -------------------------------------------------

    def append(self, name: str, record: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(self.root / name, "a", encoding="utf-8") as f:
            f.write(line)

    def log_error(self, message: str) -> None:
        self.log("errors.log", message)

    def log(self, name: str, message: str) -> None:
        with contextlib.suppress(OSError):
            self.root.mkdir(parents=True, exist_ok=True)
            with open(self.root / name, "a", encoding="utf-8") as f:
                f.write(f"{now_iso()} {message}\n")

    # --- locked JSON state ------------------------------------------------

    def path_for(self, session: str, key: str) -> Path:
        """Where `locked(session, key)` reads/writes. Safe for a read-only
        caller to use directly (writes always go through an atomic replace,
        so a concurrent reader sees either the old or the new file, never a
        torn one) when taking the lock isn't worth it for a plain read.
        """
        return self._path(session, key)

    def _path(self, session: str, key: str) -> Path:
        return self.root / "state" / _safe(session) / f"{_safe(key)}.json"

    @contextlib.contextmanager
    def locked(self, session: str, key: str):
        """Yields (state_dict, save_fn), or (None, None) if the lock is busy."""
        path = self._path(session, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_suffix(".lock")
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        fd = None
        while fd is None:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                with contextlib.suppress(OSError):
                    if time.time() - lock.stat().st_mtime > LOCK_STALE_S:
                        lock.unlink()  # a crashed hook left it behind
                        continue
                if time.monotonic() > deadline:
                    yield None, None
                    return
                time.sleep(0.02)
        try:
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = {}

            def save(new_state: dict) -> None:
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(new_state, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, path)

            yield state, save
        finally:
            os.close(fd)
            with contextlib.suppress(OSError):
                lock.unlink()
