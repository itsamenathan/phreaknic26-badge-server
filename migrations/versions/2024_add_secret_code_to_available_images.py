"""add secret code to available images

Revision ID: add_secret_code_available_images
Revises: b8bec1855043
Create Date: 2025-02-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_secret_code_available_images"
down_revision: Union[str, Sequence[str], None] = "b8bec1855043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "available_images",
        sa.Column("secret_code", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("available_images", "secret_code")

