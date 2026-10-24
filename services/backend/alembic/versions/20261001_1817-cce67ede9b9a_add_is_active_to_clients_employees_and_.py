"""add is_active to clients, employees and unique to name of pickup_point

Revision ID: cce67ede9b9a
Revises: d6e633470779
Create Date: 2026-10-01 18:17:59.038055

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cce67ede9b9a'
down_revision: Union[str, Sequence[str], None] = 'd6e633470779'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clients', sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False), schema='app')
    op.add_column('employees', sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False), schema='app')
    op.create_unique_constraint(op.f('uq_pickup_points_name'), 'pickup_points', ['name'], schema='app')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('uq_pickup_points_name'), 'pickup_points', type_='unique', schema='app')
    op.drop_column('employees', 'is_active', schema='app')
    op.drop_column('clients', 'is_active', schema='app')