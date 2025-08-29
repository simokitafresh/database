from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class PriceRowOut(BaseModel):
    """Output schema for a price row."""

    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str
    last_updated: datetime = Field(..., description="Timezone-aware timestamp")
    source_symbol: str | None = None

    @field_validator("last_updated")
    @classmethod
    def _ensure_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("last_updated must be timezone-aware")
        return v


__all__ = ["PriceRowOut"]
