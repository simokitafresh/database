from pathlib import Path

MIGRATION = Path("app/migrations/versions/003_add_price_checks.py")


def test_migration_adds_price_checks():
    content = MIGRATION.read_text()
    assert "ck_prices_low_le_open_close" in content
    assert "ck_prices_open_close_le_high" in content
    assert "ck_prices_positive_ohlc" in content
    assert "ck_prices_volume_nonneg" in content
