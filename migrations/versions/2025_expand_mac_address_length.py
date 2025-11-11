"""expand mac address length

Revision ID: expand_mac_length
Revises: add_badge_unlocked_images
Create Date: 2025-02-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "expand_mac_length"
down_revision: Union[str, Sequence[str], None] = "add_badge_unlocked_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_LENGTH = 23
OLD_LENGTH = 17


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "badges",
        "mac_address",
        existing_type=sa.String(length=OLD_LENGTH),
        type_=sa.String(length=NEW_LENGTH),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "badges",
        "mac_address",
        existing_type=sa.String(length=NEW_LENGTH),
        type_=sa.String(length=OLD_LENGTH),
        existing_nullable=True,
    )
