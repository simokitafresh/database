from __future__ import annotations

from datetime import date
from typing import Generic, TypeVar, List, Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


T = TypeVar('T')


class DateRange(BaseModel):
    """A validated date range."""

    from_: date = Field(..., alias="from")
    to: date

    # allow population by both field name and alias
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("to")
    @classmethod
    def _check_order(cls, v: date, info: ValidationInfo) -> date:
        start = info.data.get("from_") if info.data else None
        if start and v < start:
            raise ValueError("'from' must be on or before 'to'")
        return v


class BaseResponse(BaseModel):
    """Base response model for API endpoints."""
    
    success: bool = True
    message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseResponse, Generic[T]):
    """Paginated response model for API endpoints."""
    
    data: List[T]
    total: int
    page: int = 1
    per_page: int = 50
    has_next: bool = False
    has_prev: bool = False


__all__ = ["DateRange", "BaseResponse", "PaginatedResponse"]
