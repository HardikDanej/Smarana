"""
Audit trails (Plan Step 84): every important operation leaves a record --
WHO/WHAT/WHEN/WHY/SOURCE/RESULT. Plan's own two examples:

    Agent A retrieved memory M-18492 at 14:03 for task T-9281, policy allowed.
    Agent B attempted access, memory M-18492, denied, reason: scope mismatch.

Plain in-memory log, the same shape as RelationshipGraph: an index over
records, not a database -- persisting it durably is a StorageAdapter's
job in a later phase, not this one's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AuditEntry:
    who: str
    what: str
    when: datetime
    why: str
    source: str
    result: str


class AuditLog:
    def __init__(self):
        self._entries: list[AuditEntry] = []

    def record(self, who: str, what: str, why: str, source: str, result: str) -> AuditEntry:
        entry = AuditEntry(
            who=who, what=what, when=datetime.now(timezone.utc), why=why, source=source, result=result
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def for_principal(self, who: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.who == who]

    def denials(self) -> list[AuditEntry]:
        # "result" carries security.PolicyDecision's own vocabulary
        # ("allow"/"deny") verbatim, not a paraphrase of it -- one
        # vocabulary for a decision, not two spellings to keep in sync.
        return [e for e in self._entries if e.result == "deny"]
