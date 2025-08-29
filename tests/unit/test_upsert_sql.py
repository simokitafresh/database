from app.services.upsert import upsert_prices_sql


def test_upsert_sql_contains_on_conflict():
    sql = upsert_prices_sql()
    assert "ON CONFLICT (symbol, date) DO UPDATE" in sql
