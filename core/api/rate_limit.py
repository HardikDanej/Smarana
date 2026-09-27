"""
Rate limiting (Plan Step 96, closing docs/THREAT_MODEL.md's other named
gap: "no... rate limiting... exists because there is no API yet to
enforce it on"). A fixed-window counter per principal, in-memory --
single-process, the same honesty as auth.py's API key store: right for
closing "none exists at all," not a claim this is what a multi-instance
production deployment would run. A real deployment needs a shared
counter (Redis, etc.) so one instance's count is visible to all of
them -- a real gap, named here rather than silently assumed solved.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Window:
    window_start: float
    count: int


class RateLimitExceeded(Exception):
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        super().__init__(f"rate limit exceeded: {max_requests} requests per {window_seconds:.0f}s")


class RateLimiter:
    """A pure fixed-window limiter, no FastAPI dependency of its own --
    app.py composes `check()` with authentication, since knowing WHO to
    limit requires the principal that authentication already resolved."""

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}

    def check(self, key: str) -> None:
        """Raises RateLimitExceeded if `key` is over quota for the
        current window; otherwise records this call."""
        now = time.monotonic()
        window = self._windows.get(key)
        if window is None or now - window.window_start >= self.window_seconds:
            self._windows[key] = _Window(window_start=now, count=1)
            return
        if window.count >= self.max_requests:
            raise RateLimitExceeded(self.max_requests, self.window_seconds)
        window.count += 1
