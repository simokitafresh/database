"""Minimal performance profiler stub for tests.

The real project includes a rich profiler implementation. For the
purposes of the tests in this kata we only need a lightweight class that
can be instantiated without side effects.
"""

from __future__ import annotations


class FallbackProfiler:
    """No-op profiler used by integration tests."""

    def __init__(self) -> None:  # pragma: no cover - trivial
        pass
