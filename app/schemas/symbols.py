from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class SymbolOut(BaseModel):
    """Output schema for symbol information."""

    symbol: str
    name: str | None = None
    exchange: str | None = None
    currency: str | None = None
    is_active: bool | None = None
    first_date: date | None = None
    last_date: date | None = None
    created_at: datetime | None = None


__all__ = ["SymbolOut"]
