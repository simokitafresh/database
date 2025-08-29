from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


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


__all__ = ["DateRange"]
