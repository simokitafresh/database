"""Add economic_indicators table

Revision ID: 010
Revises: 009
Create Date: 2024-11-27 13:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('economic_indicators',
    sa.Column('symbol', sa.String(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('value', sa.Float(), nullable=True),
    sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('symbol', 'date')
    )


def downgrade() -> None:
    op.drop_table('economic_indicators')
