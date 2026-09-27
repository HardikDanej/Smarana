"""
Telemetry interface (Plan Step 91): OpenTelemetry instrumentation.

OpenTelemetry's own API package is designed to be imported directly by
libraries -- it IS the vendor-neutral instrumentation standard, not a
vendor lock-in choice the way `anthropic`/`psycopg2`/`cryptography` are.
This module still puts a Protocol in front of it, for one reason: every
other concrete technology choice in this codebase (LLM, storage,
encryption, object store) follows the same core-vs-adapter rule with no
carve-outs, and "this one's actually fine to import directly" is exactly
the kind of exception that erodes an invariant an automated gate is
supposed to hold absolutely. OTelTelemetry (core/adapters) is the only
file allowed to import `opentelemetry`.

Two operations, matching what Step 91 actually needs so RetrievalEngine
and PolicyEngine can report through it: a span for timing/tracing one
operation, and a metric observation. Not a general OTel API surface.
"""

from __future__ import annotations

from typing import ContextManager, Protocol, runtime_checkable


@runtime_checkable
class Telemetry(Protocol):
    def span(self, name: str, **attributes: object) -> ContextManager[None]:
        """A context manager timing/tracing one operation."""
        ...

    def record_metric(self, name: str, value: float, **attributes: object) -> None:
        """Records one metric observation (Step 92's Recall@K,
        contradiction rate, etc. are computed by metrics.py and reported
        through here, not the other way around -- this module knows
        nothing about what a memory metric means)."""
        ...
