"""create coverage view

Revision ID: 005
Revises: 004
Create Date: 2025-09-05 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create v_symbol_coverage view for displaying symbol data coverage information."""
    
    op.execute("""
        CREATE VIEW v_symbol_coverage AS
        SELECT 
            s.symbol,
            s.name,
            s.exchange,
            s.currency,
            s.is_active,
            MIN(p.date) AS data_start,
            MAX(p.date) AS data_end,
            COUNT(DISTINCT p.date) AS data_days,
            COUNT(*) AS row_count,
            MAX(p.last_updated) AS last_updated,
            CASE 
                WHEN COUNT(*) > 0 AND 
                     (MAX(p.date) - MIN(p.date) + 1) > COUNT(DISTINCT p.date)
                THEN true 
                ELSE false 
            END AS has_gaps
        FROM symbols s
        LEFT JOIN prices p ON s.symbol = p.symbol
        GROUP BY s.symbol, s.name, s.exchange, s.currency, s.is_active
    """)


def downgrade() -> None:
    """Drop v_symbol_coverage view."""
    
    op.execute("DROP VIEW IF EXISTS v_symbol_coverage")
