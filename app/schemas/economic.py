"""Pydantic schemas for economic indicators functionality."""

from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List


class EconomicDataOut(BaseModel):
    """Single economic indicator data point."""
    symbol: str
    date: date
    value: Optional[float] = None
    last_updated: datetime

    class Config:
        from_attributes = True


class EconomicDataListOut(BaseModel):
    """Economic data list response."""
    symbol: str
    data: List[EconomicDataOut]
    count: int
    date_range: dict


class EconomicSeriesInfoOut(BaseModel):
    """Economic series metadata."""
    symbol: str
    name: str
    description: Optional[str] = None
    frequency: str
    units: str
    source: str
    data_start: Optional[date] = None
    data_end: Optional[date] = None
    row_count: int = 0
    last_updated: Optional[datetime] = None


__all__ = ["EconomicDataOut", "EconomicDataListOut", "EconomicSeriesInfoOut"]
