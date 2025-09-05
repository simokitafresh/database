"""create fetch_jobs table

Revision ID: 004
Revises: 003
Create Date: 2025-09-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create fetch_jobs table for managing background data fetch tasks."""
    
    op.create_table(
        'fetch_jobs',
        sa.Column('job_id', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('symbols', postgresql.ARRAY(sa.String), nullable=False),
        sa.Column('date_from', sa.Date, nullable=False),
        sa.Column('date_to', sa.Date, nullable=False),
        sa.Column('interval', sa.String(10), nullable=False, default='1d'),
        sa.Column('force_refresh', sa.Boolean, nullable=False, default=False),
        sa.Column('priority', sa.String(10), nullable=False, default='normal'),
        sa.Column('progress', sa.JSON, nullable=True),
        sa.Column('results', sa.JSON, nullable=True),
        sa.Column('errors', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('job_id'),
    )
    
    # Create indexes for performance
    op.create_index('idx_fetch_jobs_status', 'fetch_jobs', ['status'])
    op.create_index('idx_fetch_jobs_created_at', 'fetch_jobs', ['created_at'], postgresql_ops={'created_at': 'DESC'})


def downgrade() -> None:
    """Drop fetch_jobs table and related indexes."""
    
    op.drop_index('idx_fetch_jobs_created_at', table_name='fetch_jobs')
    op.drop_index('idx_fetch_jobs_status', table_name='fetch_jobs')
    op.drop_table('fetch_jobs')
