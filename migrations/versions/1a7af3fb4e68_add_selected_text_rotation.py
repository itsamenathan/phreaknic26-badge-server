"""add selected_text_rotation to badges

Revision ID: 1a7af3fb4e68
Revises: e608625baeeb
Create Date: 2024-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a7af3fb4e68'
down_revision: Union[str, Sequence[str], None] = 'e608625baeeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding selected_text_rotation."""
    op.add_column(
        'badges',
        sa.Column('selected_text_rotation', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema by removing selected_text_rotation."""
    op.drop_column('badges', 'selected_text_rotation')

