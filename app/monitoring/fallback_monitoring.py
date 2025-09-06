"""Lightweight monitoring utilities for fallback tests.

This module provides a minimal implementation of the monitoring
interfaces expected by the integration tests. It tracks how many
requests have been monitored and exposes a context manager that allows
tests to simulate recording results.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterable, Optional


class _MetricsCollector:
    """A tiny metrics collector used in tests.

    It only keeps track of how many requests were monitored so that tests
    can assert that monitoring was triggered.
    """

    def __init__(self) -> None:
        self.total_requests: int = 0

    def record_request(self) -> None:
        self.total_requests += 1


_metrics_collector = _MetricsCollector()


def get_metrics_collector() -> _MetricsCollector:
    """Return the process-wide metrics collector."""

    return _metrics_collector


@contextmanager
def fallback_monitoring(
    symbols: Iterable[str],
    date_from: Any,
    date_to: Any,
):
    """Context manager used by the tests to simulate monitoring.

    The context manager increments the global metrics counter when
    entered and provides an object exposing a ``set_result`` method so
    that tests can attach arbitrary result data.
    """

    _metrics_collector.record_request()
    monitor = SimpleNamespace(symbols=list(symbols), date_from=date_from, date_to=date_to)

    def set_result(result: Any, adjusted_from: Optional[Any] = None) -> None:
        monitor.result = result
        monitor.adjusted_from = adjusted_from

    monitor.set_result = set_result

    try:
        yield monitor
    finally:
        pass
