from __future__ import annotations

import typer

from app.services import normalize


def db_add_symbol(symbol: str) -> None:  # pragma: no cover - placeholder
    """Insert symbol into the database (stub)."""


def add_symbol(symbol: str) -> None:
    """Normalize and insert a symbol, reporting duplicates."""
    norm = normalize.normalize_symbol(symbol)
    try:
        db_add_symbol(norm)
    except ValueError:
        typer.echo(f"{norm} already exists")
    else:
        typer.echo(f"added {norm}")
