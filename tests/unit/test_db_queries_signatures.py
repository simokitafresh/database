from pathlib import Path


def test_get_prices_resolved_returns_double_precision():
    sql = Path("app/migrations/versions/002_fn_prices_resolved.py").read_text(encoding="utf-8")
    assert "RETURNS TABLE (" in sql
    assert "open double precision" in sql
    assert "high double precision" in sql
    assert "low double precision" in sql
    assert "close double precision" in sql
