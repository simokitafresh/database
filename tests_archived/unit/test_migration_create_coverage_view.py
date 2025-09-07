from pathlib import Path

MIGRATION = Path("app/migrations/versions/005_create_coverage_view.py")


def test_migration_creates_coverage_view():
    content = MIGRATION.read_text()
    assert 'CREATE VIEW v_symbol_coverage AS' in content
    assert 'SELECT' in content
    assert 's.symbol,' in content
    assert 's.name,' in content
    assert 's.exchange,' in content
    assert 's.currency,' in content
    assert 's.is_active,' in content
    assert 'MIN(p.date) AS data_start,' in content
    assert 'MAX(p.date) AS data_end,' in content
    assert 'COUNT(DISTINCT p.date) AS data_days,' in content
    assert 'COUNT(*) AS row_count,' in content
    assert 'MAX(p.last_updated) AS last_updated,' in content
    assert 'CASE' in content
    assert 'WHEN COUNT(*) > 0 AND' in content
    assert 'THEN true' in content
    assert 'ELSE false' in content
    assert 'END AS has_gaps' in content
    assert 'FROM symbols s' in content
    assert 'LEFT JOIN prices p ON s.symbol = p.symbol' in content
    assert 'GROUP BY s.symbol, s.name, s.exchange, s.currency, s.is_active' in content


def test_migration_contains_downgrade():
    content = MIGRATION.read_text()
    assert 'def downgrade() -> None:' in content
    assert 'DROP VIEW IF EXISTS v_symbol_coverage' in content
