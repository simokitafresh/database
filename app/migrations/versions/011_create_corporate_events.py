"""create corporate_events

Revision ID: 011
Revises: 010
Create Date: 2025-12-03 14:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'corporate_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('ratio', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True, server_default='USD'),
        sa.Column('ex_date', sa.Date(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('detection_method', sa.String(length=20), nullable=True, server_default='auto'),
        sa.Column('db_price_at_detection', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('yf_price_at_detection', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('pct_difference', sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column('severity', sa.String(length=10), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='detected'),
        sa.Column('fixed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fix_job_id', sa.String(length=50), nullable=True),
        sa.Column('rows_deleted', sa.Integer(), nullable=True),
        sa.Column('rows_refetched', sa.Integer(), nullable=True),
        sa.Column('source_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['symbol'], ['symbols.symbol'], onupdate='CASCADE', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', 'event_date', 'event_type', name='uq_corp_event'),
        sa.CheckConstraint("event_type IN ('stock_split', 'reverse_split', 'dividend', 'special_dividend', 'capital_gain', 'spinoff', 'unknown')", name='ck_corp_event_type'),
        sa.CheckConstraint("status IN ('detected', 'confirmed', 'fixing', 'fixed', 'ignored', 'failed')", name='ck_corp_event_status'),
        sa.CheckConstraint("severity IN ('critical', 'high', 'normal', 'low')", name='ck_corp_event_severity')
    )
    op.create_index('idx_corp_events_date', 'corporate_events', [sa.text('event_date DESC')], unique=False)
    op.create_index('idx_corp_events_detected', 'corporate_events', [sa.text('detected_at DESC')], unique=False)
    op.create_index('idx_corp_events_status', 'corporate_events', ['status'], unique=False, postgresql_where=sa.text("status != 'fixed'"))
    op.create_index('idx_corp_events_symbol', 'corporate_events', ['symbol'], unique=False)
    op.create_index('idx_corp_events_type', 'corporate_events', ['event_type'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_corp_events_type', table_name='corporate_events')
    op.drop_index('idx_corp_events_symbol', table_name='corporate_events')
    op.drop_index('idx_corp_events_status', table_name='corporate_events', postgresql_where=sa.text("status != 'fixed'"))
    op.drop_index('idx_corp_events_detected', table_name='corporate_events')
    op.drop_index('idx_corp_events_date', table_name='corporate_events')
    op.drop_table('corporate_events')
