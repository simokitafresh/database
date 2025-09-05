"""add performance indexes

Revision ID: 006
Revises: 005
Create Date: 2025-09-05 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes for prices table to improve coverage queries."""
    
    # Index on (symbol, date) for efficient coverage range queries
    op.create_index(
        'idx_prices_symbol_date', 
        'prices', 
        ['symbol', 'date'],
        if_not_exists=True
    )
    
    # Index on last_updated for tracking data freshness
    op.create_index(
        'idx_prices_last_updated', 
        'prices', 
        ['last_updated'],
        if_not_exists=True
    )


def downgrade() -> None:
    """Drop performance indexes."""
    
    op.drop_index('idx_prices_last_updated', table_name='prices', if_exists=True)
    op.drop_index('idx_prices_symbol_date', table_name='prices', if_exists=True)
