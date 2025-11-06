"""add mac address to badges

Revision ID: d0b55d5b090c
Revises: b8bec1855043
Create Date: 2025-11-03 12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


# revision identifiers, used by Alembic.
revision: str = 'd0b55d5b090c'
down_revision: Union[str, Sequence[str], None] = 'b8bec1855043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not _has_column('badges', 'mac_address'):
        op.add_column('badges', sa.Column('mac_address', sa.String(length=17), nullable=True))
    existing_constraints = {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints('badges')
    }
    if 'uq_badges_mac_address' not in existing_constraints:
        op.create_unique_constraint('uq_badges_mac_address', 'badges', ['mac_address'])


def downgrade() -> None:
    if _has_column('badges', 'mac_address'):
        op.drop_constraint('uq_badges_mac_address', 'badges', type_='unique')
        op.drop_column('badges', 'mac_address')
