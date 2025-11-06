"""add mac address to badges

Revision ID: d0b55d5b090c
Revises: b8bec1855043
Create Date: 2025-11-03 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0b55d5b090c'
down_revision: Union[str, Sequence[str], None] = 'b8bec1855043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('badges', sa.Column('mac_address', sa.String(length=17), nullable=True))
    op.create_unique_constraint('uq_badges_mac_address', 'badges', ['mac_address'])


def downgrade() -> None:
    op.drop_constraint('uq_badges_mac_address', 'badges', type_='unique')
    op.drop_column('badges', 'mac_address')
