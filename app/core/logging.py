"""Utility functions for application logging.

This module provides a simple ``configure_logging`` helper that configures the
root logger to output JSON formatted log records. Only a minimal set of fields
``level``, ``name`` and ``message`` are included to satisfy the project
requirements.
"""

from __future__ import annotations

import json
import logging


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


__all__ = ["configure_logging"]

