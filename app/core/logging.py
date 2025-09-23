"""Utility functions for application logging and error metrics.

This module provides a simple ``configure_logging`` helper that configures the
root logger to output JSON formatted log records. Only a minimal set of fields
``level``, ``name`` and ``message`` are included to satisfy the project
requirements.

Also provides error metrics collection for monitoring and debugging.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, Counter
from typing import Dict, Any, Optional
from contextlib import contextmanager


class _JsonFormatter(logging.Formatter):
    """Format log records as compact JSON strings."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - short
        return json.dumps(
            {
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
            }
        )


def configure_logging(level: int | str = logging.INFO) -> None:
    """Configure the root logger to emit JSON formatted records.

    Parameters
    ----------
    level:
        The minimum logging level. Defaults to ``logging.INFO``.
    """

    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


# Error metrics collection
class ErrorMetrics:
    """Simple error metrics collector for monitoring error patterns."""
    
    def __init__(self):
        self.errors = Counter()
        self.error_timestamps = defaultdict(list)
        self._lock = False  # Simple lock for thread safety
    
    def record_error(self, error_type: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Record an error occurrence."""
        if self._lock:
            return
        self._lock = True
        try:
            self.errors[error_type] += 1
            self.error_timestamps[error_type].append(time.time())
            
            # Keep only recent timestamps (last 100 per error type)
            if len(self.error_timestamps[error_type]) > 100:
                self.error_timestamps[error_type] = self.error_timestamps[error_type][-100:]
        finally:
            self._lock = False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current error metrics."""
        return {
            "error_counts": dict(self.errors),
            "recent_errors": {
                error_type: len(timestamps) 
                for error_type, timestamps in self.error_timestamps.items()
                if timestamps and (time.time() - timestamps[-1]) < 3600  # Last hour
            }
        }
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.errors.clear()
        self.error_timestamps.clear()


# Global error metrics instance
_error_metrics = ErrorMetrics()


def get_error_metrics() -> ErrorMetrics:
    """Get the global error metrics instance."""
    return _error_metrics


@contextmanager
def error_context(operation: str, **context):
    """Context manager for tracking operation errors."""
    start_time = time.time()
    try:
        yield
    except Exception as e:
        duration = time.time() - start_time
        error_type = type(e).__name__
        
        # Record error metrics
        get_error_metrics().record_error(error_type, {
            "operation": operation,
            "duration": duration,
            **context
        })
        
        # Re-raise the exception
        raise
    finally:
        pass


# Get logger instance for use in other modules
logger = logging.getLogger(__name__)


__all__ = ["configure_logging", "logger", "ErrorMetrics", "get_error_metrics", "error_context"]
