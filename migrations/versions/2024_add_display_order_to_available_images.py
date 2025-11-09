"""add display order to available images

Revision ID: add_display_order_available_images
Revises: add_badge_unlocked_images
Create Date: 2025-02-15 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_display_order_available_images"
down_revision: Union[str, Sequence[str], None] = "add_badge_unlocked_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "available_images",
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column(
        "available_images",
        "display_order",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("available_images", "display_order")

