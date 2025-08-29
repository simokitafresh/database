from pathlib import Path

MIGRATION = Path("app/migrations/versions/002_fn_prices_resolved.py")


def test_migration_contains_create_and_drop_function():
    content = MIGRATION.read_text()
    assert "CREATE OR REPLACE FUNCTION get_prices_resolved" in content
    assert "DROP FUNCTION IF EXISTS get_prices_resolved" in content
    assert "p.date >= sc.change_date" in content
    assert "p.date < sc.change_date" in content
