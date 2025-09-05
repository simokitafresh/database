"""add check constraints for prices

Revision ID: 003_add_price_checks
Revises: 002_fn_prices_resolved
Create Date: 2025-08-29
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_prices_low_le_open_close",
        "prices",
        "low <= LEAST(open, close)",
    )
    op.create_check_constraint(
        "ck_prices_open_close_le_high",
        "prices",
        "GREATEST(open, close) <= high",
    )
    op.create_check_constraint(
        "ck_prices_positive_ohlc",
        "prices",
        "open > 0 AND high > 0 AND low > 0 AND close > 0",
    )
    op.create_check_constraint(
        "ck_prices_volume_nonneg",
        "prices",
        "volume >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_prices_volume_nonneg", "prices", type_="check")
    op.drop_constraint("ck_prices_positive_ohlc", "prices", type_="check")
    op.drop_constraint("ck_prices_open_close_le_high", "prices", type_="check")
    op.drop_constraint("ck_prices_low_le_open_close", "prices", type_="check")
