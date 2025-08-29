from datetime import date

from app.services.resolver import segments_for


def test_segments_for_handles_symbol_change_boundary():
    rows = [
        {"old_symbol": "FB", "new_symbol": "META", "change_date": date(2022, 6, 9)}
    ]
    result = segments_for("FB", date(2022, 6, 8), date(2022, 6, 10), rows)
    assert result == [
        ("FB", date(2022, 6, 8), date(2022, 6, 8)),
        ("META", date(2022, 6, 9), date(2022, 6, 10)),
    ]


def test_segments_for_accepts_new_symbol_request():
    rows = [
        {"old_symbol": "FB", "new_symbol": "META", "change_date": date(2022, 6, 9)}
    ]
    result = segments_for("META", date(2022, 6, 8), date(2022, 6, 10), rows)
    assert result == [
        ("FB", date(2022, 6, 8), date(2022, 6, 8)),
        ("META", date(2022, 6, 9), date(2022, 6, 10)),
    ]
