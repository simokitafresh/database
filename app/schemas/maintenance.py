"""Schemas for maintenance API endpoints (TID-ADJ-010)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AdjustmentCheckRequest(BaseModel):
    """Request body for adjustment check endpoint."""
    
    symbols: Optional[List[str]] = Field(
        default=None,
        description="List of symbols to check. If None, all active symbols are checked.",
    )
    auto_fix: bool = Field(
        default=False,
        description="Whether to automatically fix detected issues.",
    )
    threshold_pct: float = Field(
        default=0.001,
        ge=0,
        description="Minimum percentage difference to trigger detection.",
    )
    sample_points: int = Field(
        default=10,
        ge=2,
        le=50,
        description="Number of sample points to check.",
    )


class AdjustmentEventResponse(BaseModel):
    """Single adjustment event in response."""
    
    symbol: str
    event_type: str
    severity: str
    pct_difference: float
    check_date: str
    db_price: float
    yf_adjusted_price: float
    details: Dict[str, Any] = Field(default_factory=dict)
    recommendation: str = ""
    event_id: Optional[int] = None


class ScanResultResponse(BaseModel):
    """Result for a single symbol scan."""
    
    symbol: str
    needs_refresh: bool
    events: List[AdjustmentEventResponse] = Field(default_factory=list)
    max_pct_diff: float = 0.0
    error: Optional[str] = None


class AdjustmentCheckResponse(BaseModel):
    """Response body for adjustment check endpoint."""
    
    scan_timestamp: str
    total_symbols: int
    scanned: int
    needs_refresh: List[ScanResultResponse]
    no_change: List[str]
    errors: List[Dict[str, str]]
    fixed: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Dict[str, int]]


class AdjustmentFixRequest(BaseModel):
    """Request body for adjustment fix endpoint."""
    
    symbols: Optional[List[str]] = Field(
        default=None,
        description="List of symbols to fix. If None, fixes all needing refresh.",
    )
    confirm: bool = Field(
        default=False,
        description="Must be True to proceed with fix. Safety guard.",
    )


class FixResultItem(BaseModel):
    """Result of fixing a single symbol."""
    
    symbol: str
    deleted_rows: int
    job_created: bool
    job_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: str


class AdjustmentFixResponse(BaseModel):
    """Response body for adjustment fix endpoint."""
    
    total_requested: int
    fixed: List[FixResultItem]
    errors: List[Dict[str, str]]
    summary: Dict[str, int]


class AdjustmentReportResponse(BaseModel):
    """Response body for adjustment report endpoint."""
    
    last_scan_timestamp: Optional[str] = None
    total_symbols: int = 0
    needs_refresh_count: int = 0
    needs_refresh: List[ScanResultResponse] = Field(default_factory=list)
    summary: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    available: bool = True
