"""add badge unlocked images table

Revision ID: add_badge_unlocked_images
Revises: add_requires_secret_flag
Create Date: 2025-02-15 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_badge_unlocked_images"
down_revision: Union[str, Sequence[str], None] = "add_requires_secret_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "badge_unlocked_images",
        sa.Column("unique_id", sa.String(), nullable=False),
        sa.Column("image_label", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["unique_id"], ["badges.unique_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("unique_id", "image_label"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("badge_unlocked_images")

