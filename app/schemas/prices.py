from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

try:
    # Pydantic v2
    from pydantic import BaseModel, Field, field_validator
except Exception:  # v1 fallback
    from pydantic import BaseModel, Field
    from pydantic import validator as field_validator


class PriceRowOut(BaseModel):
    symbol: str
    # Contract: date-only (YYYY-MM-DD). PydanticはISO文字列を自動でdateに変換します。
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str
    last_updated: datetime = Field(..., description="Timezone-aware UTC timestamp")
    source_symbol: Optional[str] = None

    @field_validator("last_updated")
    @classmethod
    def _tz_aware_utc(cls, v: datetime) -> datetime:
        # timezone-aware を必須化し、常に UTC に正規化
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("last_updated must be timezone-aware")
        return v.astimezone(timezone.utc)


__all__ = ["PriceRowOut"]
