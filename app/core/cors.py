"""Utilities for creating a CORS middleware based on settings."""

from __future__ import annotations

from typing import Optional, Tuple, Type

from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings


MiddlewareConfig = Tuple[Type[CORSMiddleware], dict]


def create_cors_middleware(settings: Settings) -> Optional[MiddlewareConfig]:
    """Return a ``CORSMiddleware`` configuration if origins are provided.

    Parameters
    ----------
    settings:
        The application settings containing the ``CORS_ALLOW_ORIGINS`` CSV.

    Returns
    -------
    Optional[MiddlewareConfig]
        ``None`` if no origins were provided, otherwise a tuple of the
        middleware class and keyword arguments to pass to ``add_middleware``.
    """

    if not settings.CORS_ALLOW_ORIGINS:
        return None

    origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
    return (
        CORSMiddleware,
        {
            "allow_origins": origins,
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        },
    )


__all__ = ["create_cors_middleware"]
