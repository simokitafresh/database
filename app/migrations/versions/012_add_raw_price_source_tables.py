"""add raw price source tables

Revision ID: 012
Revises: 011
Create Date: 2026-07-05 22:35:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prices_raw",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=False),
        sa.Column("high", sa.Numeric(18, 6), nullable=False),
        sa.Column("low", sa.Numeric(18, 6), nullable=False),
        sa.Column("close", sa.Numeric(18, 6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("consensus_close", sa.Numeric(18, 6), nullable=True),
        sa.ForeignKeyConstraint(
            ["symbol"], ["symbols.symbol"], onupdate="CASCADE", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("symbol", "date", "source"),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_prices_raw_positive_ohlc"
        ),
        sa.CheckConstraint("low <= LEAST(open, close)", name="ck_prices_raw_low_le_open_close"),
        sa.CheckConstraint(
            "GREATEST(open, close) <= high", name="ck_prices_raw_open_close_le_high"
        ),
        sa.CheckConstraint("volume >= 0", name="ck_prices_raw_volume_nonneg"),
    )
    op.create_index("idx_prices_raw_symbol_date", "prices_raw", ["symbol", "date"], unique=False)
    op.create_index(
        "idx_prices_raw_consensus",
        "prices_raw",
        ["symbol", "date"],
        unique=False,
        postgresql_where=sa.text("consensus_close IS NOT NULL"),
    )

    op.add_column(
        "corporate_events", sa.Column("dividend_amount", sa.Numeric(18, 8), nullable=True)
    )
    op.add_column("corporate_events", sa.Column("split_ratio", sa.Numeric(18, 8), nullable=True))
    op.add_column("corporate_events", sa.Column("record_date", sa.Date(), nullable=True))
    op.add_column("corporate_events", sa.Column("pay_date", sa.Date(), nullable=True))
    op.add_column(
        "corporate_events", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("corporate_events", sa.Column("source_count", sa.Integer(), nullable=True))
    op.add_column(
        "corporate_events",
        sa.Column("sources_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "idx_corp_events_confirmed",
        "corporate_events",
        ["symbol", "ex_date"],
        unique=False,
        postgresql_where=sa.text("confirmed_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_corp_events_confirmed",
        table_name="corporate_events",
        postgresql_where=sa.text("confirmed_at IS NOT NULL"),
    )
    op.drop_column("corporate_events", "sources_json")
    op.drop_column("corporate_events", "source_count")
    op.drop_column("corporate_events", "confirmed_at")
    op.drop_column("corporate_events", "pay_date")
    op.drop_column("corporate_events", "record_date")
    op.drop_column("corporate_events", "split_ratio")
    op.drop_column("corporate_events", "dividend_amount")
    op.drop_index(
        "idx_prices_raw_consensus",
        table_name="prices_raw",
        postgresql_where=sa.text("consensus_close IS NOT NULL"),
    )
    op.drop_index("idx_prices_raw_symbol_date", table_name="prices_raw")
    op.drop_table("prices_raw")
