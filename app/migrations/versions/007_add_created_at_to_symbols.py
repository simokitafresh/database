"""add created_at to symbols table

Revision ID: 007
Revises: 006
Create Date: 2025-09-05 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add created_at column to symbols table."""
    
    # Add created_at column with default value for existing rows
    op.add_column(
        'symbols',
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        )
    )


def downgrade() -> None:
    """Remove created_at column from symbols table."""
    
    op.drop_column('symbols', 'created_at')
