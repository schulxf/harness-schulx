"""User-facing Harness errors shared across adapters."""

from __future__ import annotations


class HarnessError(Exception):
    """User-facing CLI error without a Python traceback."""
