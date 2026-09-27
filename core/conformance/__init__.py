"""Adapter conformance suites (Plan Step 99). See storage_adapter.py."""

from .storage_adapter import CONFORMANCE_CHECKS, certify

__all__ = ["CONFORMANCE_CHECKS", "certify"]
