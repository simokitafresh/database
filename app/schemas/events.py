"""Pydantic schemas for corporate events."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventTypeEnum(str, Enum):
    """Corporate event types."""
    
    STOCK_SPLIT = "stock_split"
    REVERSE_SPLIT = "reverse_split"
    DIVIDEND = "dividend"
    SPECIAL_DIVIDEND = "special_dividend"
    CAPITAL_GAIN = "capital_gain"
    SPINOFF = "spinoff"
    UNKNOWN = "unknown"


class EventStatusEnum(str, Enum):
    """Corporate event status."""
    
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    FIXING = "fixing"
    FIXED = "fixed"
    IGNORED = "ignored"
    FAILED = "failed"


class EventSeverityEnum(str, Enum):
    """Corporate event severity."""
    
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class CorporateEventBase(BaseModel):
    """Base schema for corporate events."""
    
    symbol: str = Field(..., description="Stock symbol")
    event_date: date = Field(..., description="Event date")
    event_type: EventTypeEnum = Field(..., description="Event type")
    ratio: Optional[Decimal] = Field(None, description="Split ratio (e.g., 4.0 for 4:1 split)")
    amount: Optional[Decimal] = Field(None, description="Dividend or distribution amount")
    currency: Optional[str] = Field("USD", description="Currency code")
    ex_date: Optional[date] = Field(None, description="Ex-dividend date")
    severity: Optional[EventSeverityEnum] = Field(None, description="Event severity")
    notes: Optional[str] = Field(None, description="Additional notes")


class CorporateEventCreate(CorporateEventBase):
    """Schema for creating a corporate event."""
    
    detection_method: Optional[str] = Field("auto", description="Detection method")
    db_price_at_detection: Optional[Decimal] = Field(None, description="DB price at detection")
    yf_price_at_detection: Optional[Decimal] = Field(None, description="Yahoo Finance price at detection")
    pct_difference: Optional[Decimal] = Field(None, description="Percentage difference")
    source_data: Optional[dict] = Field(None, description="Source data")


class CorporateEventUpdate(BaseModel):
    """Schema for updating a corporate event."""
    
    status: Optional[EventStatusEnum] = Field(None, description="Event status")
    notes: Optional[str] = Field(None, description="Additional notes")


class CorporateEventResponse(CorporateEventBase):
    """Schema for corporate event response."""
    
    id: int = Field(..., description="Event ID")
    detected_at: datetime = Field(..., description="Detection timestamp")
    detection_method: Optional[str] = Field(None, description="Detection method")
    db_price_at_detection: Optional[Decimal] = Field(None, description="DB price at detection")
    yf_price_at_detection: Optional[Decimal] = Field(None, description="Yahoo Finance price at detection")
    pct_difference: Optional[Decimal] = Field(None, description="Percentage difference")
    status: Optional[str] = Field(None, description="Event status")
    fixed_at: Optional[datetime] = Field(None, description="Fix timestamp")
    fix_job_id: Optional[str] = Field(None, description="Fix job ID")
    rows_deleted: Optional[int] = Field(None, description="Rows deleted during fix")
    rows_refetched: Optional[int] = Field(None, description="Rows refetched during fix")
    source_data: Optional[dict] = Field(None, description="Source data")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")

    class Config:
        from_attributes = True


class CorporateEventListResponse(BaseModel):
    """Schema for paginated event list response."""
    
    events: list[CorporateEventResponse] = Field(..., description="List of events")
    total: int = Field(..., description="Total number of events")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Page size")
