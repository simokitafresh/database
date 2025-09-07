"""add has_full_history flag to symbols

Revision ID: 008
Revises: 007
Create Date: 2025-09-07 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add has_full_history boolean flag to symbols table (default false)."""
    op.add_column(
        'symbols',
        sa.Column('has_full_history', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Remove has_full_history column from symbols table."""
    op.drop_column('symbols', 'has_full_history')

