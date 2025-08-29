import json
from datetime import date, datetime, timezone

from app.schemas.prices import PriceRowOut


def _dump_model(m):
    # pydantic v2 / v1 両対応
    if hasattr(m, "model_dump"):
        return m.model_dump()
    return m.dict()


def _dump_json(m):
    # pydantic v2 / v1 両対応
    if hasattr(m, "model_dump_json"):
        return m.model_dump_json()
    return json.dumps(m.dict(), default=str)


def test_date_is_date_only_and_last_updated_tzaware():
    m = PriceRowOut(
        symbol="AAPL",
        date="2024-01-02",  # 文字列でもdateに変換される
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1,
        source="yfinance",
        last_updated=datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
    )
    # Python モデル上は date 型
    assert isinstance(m.date, date)
    # tz-aware であること
    assert m.last_updated.tzinfo is not None and m.last_updated.utcoffset() is not None

    # dict では date オブジェクト
    payload = _dump_model(m)
    assert payload["date"] == date(2024, 1, 2)

    # JSON は "YYYY-MM-DD"（時刻なし）
    j = _dump_json(m)
    assert '"date":"2024-01-02"' in j
