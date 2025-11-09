"""add requires_secret_code flag to available images

Revision ID: add_requires_secret_flag
Revises: add_secret_code_available_images
Create Date: 2025-02-15 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_requires_secret_flag"
down_revision: Union[str, Sequence[str], None] = "add_secret_code_available_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "available_images",
        sa.Column("requires_secret_code", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column(
        "available_images",
        "requires_secret_code",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("available_images", "requires_secret_code")

