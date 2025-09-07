from pathlib import Path

MIGRATION = Path("app/migrations/versions/001_init.py")


def test_migration_contains_tables_and_constraints():
    content = MIGRATION.read_text()
    assert 'op.create_table(\n        "symbols"' in content
    assert 'op.create_table(\n        "symbol_changes"' in content
    assert 'op.create_table(\n        "prices"' in content
    assert 'sa.UniqueConstraint("new_symbol")' in content
    assert "ck_prices_high_low_range" in content
    assert "ck_prices_positive" in content
