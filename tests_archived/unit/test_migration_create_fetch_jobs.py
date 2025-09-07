from pathlib import Path

MIGRATION = Path("app/migrations/versions/004_create_fetch_jobs.py")


def test_migration_creates_fetch_jobs_table():
    content = MIGRATION.read_text()
    assert 'op.create_table(\n        \'fetch_jobs\'' in content
    assert 'sa.Column(\'job_id\', sa.String(50), nullable=False)' in content
    assert 'sa.Column(\'status\', sa.String(20), nullable=False)' in content
    assert 'sa.Column(\'symbols\', postgresql.ARRAY(sa.String), nullable=False)' in content
    assert 'sa.Column(\'date_from\', sa.Date, nullable=False)' in content
    assert 'sa.Column(\'date_to\', sa.Date, nullable=False)' in content
    assert 'sa.Column(\'interval\', sa.String(10), nullable=False, default=\'1d\')' in content
    assert 'sa.Column(\'force_refresh\', sa.Boolean, nullable=False, default=False)' in content
    assert 'sa.Column(\'priority\', sa.String(10), nullable=False, default=\'normal\')' in content
    assert 'sa.Column(\'progress\', sa.JSON, nullable=True)' in content
    assert 'sa.Column(\'results\', sa.JSON, nullable=True)' in content
    assert 'sa.Column(\'errors\', sa.JSON, nullable=True)' in content
    assert 'sa.Column(\'created_at\', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())' in content
    assert 'sa.Column(\'started_at\', sa.DateTime(timezone=True), nullable=True)' in content
    assert 'sa.Column(\'completed_at\', sa.DateTime(timezone=True), nullable=True)' in content
    assert 'sa.Column(\'created_by\', sa.String(100), nullable=True)' in content
    assert 'sa.PrimaryKeyConstraint(\'job_id\')' in content


def test_migration_creates_indexes():
    content = MIGRATION.read_text()
    assert 'op.create_index(\'idx_fetch_jobs_status\', \'fetch_jobs\', [\'status\'])' in content
    assert 'op.create_index(\'idx_fetch_jobs_created_at\', \'fetch_jobs\', [\'created_at\'], postgresql_ops={\'created_at\': \'DESC\'})' in content


def test_migration_contains_downgrade():
    content = MIGRATION.read_text()
    assert 'def downgrade() -> None:' in content
    assert 'op.drop_index(\'idx_fetch_jobs_created_at\', table_name=\'fetch_jobs\')' in content
    assert 'op.drop_index(\'idx_fetch_jobs_status\', table_name=\'fetch_jobs\')' in content
    assert 'op.drop_table(\'fetch_jobs\')' in content
