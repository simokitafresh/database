import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "symbols",
        sa.Column("symbol", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("exchange", sa.String(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("first_date", sa.Date(), nullable=True),
        sa.Column("last_date", sa.Date(), nullable=True),
    )

    op.create_table(
        "symbol_changes",
        sa.Column("old_symbol", sa.String(), nullable=False),
        sa.Column("new_symbol", sa.String(), nullable=False),
        sa.Column("change_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("old_symbol", "change_date"),
        sa.UniqueConstraint("new_symbol"),
        sa.Index("idx_symbol_changes_old", "old_symbol"),
        sa.Index("idx_symbol_changes_new", "new_symbol"),
    )

    op.create_table(
        "prices",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("symbol", "date"),
        sa.ForeignKeyConstraint(
            ["symbol"], ["symbols.symbol"], onupdate="CASCADE", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name="ck_prices_high_low_range",
        ),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name="ck_prices_positive",
        ),
    )


def downgrade() -> None:
    op.drop_table("prices")
    op.drop_table("symbol_changes")
    op.drop_table("symbols")
