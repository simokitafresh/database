"""Utilities for creating a CORS middleware based on settings."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Type

from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings

MiddlewareConfig = Tuple[Type[CORSMiddleware], Dict[str, Any]]


def _parse_csv(csv: str) -> List[str]:
    """Split a comma-separated string into trimmed items, omitting empties."""
    return [s.strip() for s in csv.split(",") if s and s.strip()]


def create_cors_middleware(settings: Settings) -> Optional[MiddlewareConfig]:
    """Return a ``CORSMiddleware`` configuration if CORS is enabled.

    Handles the wildcard "*" value safely by switching to ``allow_origin_regex``
    and disabling credentials, as Starlette forbids credentials when using a
    raw "*" origin list.
    """
    csv = (settings.CORS_ALLOW_ORIGINS or "").strip()
    if not csv:
        return None

    origins = _parse_csv(csv)
    kwargs: Dict[str, Any] = {
        "allow_methods": ["*"],
        "allow_headers": ["*"],
        # Expose request ID header for tracing
        "expose_headers": ["X-Request-ID"],
    }

    wildcard_only = len(origins) == 1 and origins[0] == "*"
    wildcard_included = "*" in origins

    if wildcard_only or wildcard_included:
        # Starlette does not allow allow_credentials=True with wildcard
        kwargs.update({
            "allow_origin_regex": ".*",
            "allow_credentials": False,
        })
    else:
        kwargs.update({
            "allow_origins": origins,
            "allow_credentials": True,
        })

    return CORSMiddleware, kwargs


__all__ = ["create_cors_middleware"]
