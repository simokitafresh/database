from pathlib import Path

MIGRATION = Path("app/migrations/versions/006_add_performance_indexes.py")


def test_migration_adds_performance_indexes():
    content = MIGRATION.read_text()
    assert 'op.create_index(' in content
    assert '\'idx_prices_symbol_date\'' in content
    assert '\'prices\'' in content
    assert '[\'symbol\', \'date\']' in content
    assert 'if_not_exists=True' in content
    assert '\'idx_prices_last_updated\'' in content
    assert '[\'last_updated\']' in content


def test_migration_contains_downgrade():
    content = MIGRATION.read_text()
    assert 'def downgrade() -> None:' in content
    assert 'op.drop_index(\'idx_prices_last_updated\', table_name=\'prices\', if_exists=True)' in content
    assert 'op.drop_index(\'idx_prices_symbol_date\', table_name=\'prices\', if_exists=True)' in content
