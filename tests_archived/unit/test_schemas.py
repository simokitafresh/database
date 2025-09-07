from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.common import DateRange
from app.schemas.prices import PriceRowOut


def test_date_range_invalid_order_raises():
    with pytest.raises(ValidationError):
        DateRange(from_=date(2023, 1, 10), to=date(2023, 1, 5))


def test_price_row_out_enforces_types():
    aware = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=9)))
    row = PriceRowOut(
        symbol="AAA",
        date=date(2024, 1, 1),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100,
        source="test",
        last_updated=aware,
    )
    assert isinstance(row.date, date)
    assert row.last_updated.tzinfo == timezone.utc

    with pytest.raises(ValidationError):
        PriceRowOut(
            symbol="AAA",
            date=date(2024, 1, 1),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=100,
            source="test",
            last_updated=datetime(2024, 1, 1),  # naive
        )
