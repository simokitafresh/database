"""Pydantic schemas for coverage functionality."""

from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List


class CoverageItemOut(BaseModel):
    """Single symbol coverage information."""
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None
    data_start: Optional[date] = None
    data_end: Optional[date] = None
    data_days: int = 0
    row_count: int = 0
    last_updated: Optional[datetime] = None
    has_gaps: bool = False

    class Config:
        from_attributes = True


class PaginationMeta(BaseModel):
    """Pagination information."""
    page: int
    page_size: int
    total_items: int
    total_pages: int


class QueryMeta(BaseModel):
    """Query execution metadata."""
    query_time_ms: int
    cached: bool = False
    cache_updated_at: Optional[datetime] = None


class CoverageListOut(BaseModel):
    """Coverage list response with pagination."""
    items: List[CoverageItemOut]
    pagination: PaginationMeta
    meta: QueryMeta
