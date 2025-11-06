"""store firmware assets on badges and remove work queue

Revision ID: 3d0f4f3b9d10
Revises: d0b55d5b090c
Create Date: 2025-11-03 14:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d0f4f3b9d10'
down_revision: Union[str, Sequence[str], None] = 'd0b55d5b090c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('badges', sa.Column('firmware_base64', sa.Text(), nullable=True))
    op.add_column('badges', sa.Column('firmware_hash', sa.String(length=16), nullable=True))
    op.add_column('badges', sa.Column('selected_image_label', sa.String(), nullable=True))
    op.add_column('badges', sa.Column('selected_image_base64', sa.Text(), nullable=True))
    op.add_column('badges', sa.Column('selected_image_mime_type', sa.String(), nullable=True))
    op.add_column('badges', sa.Column('selected_image_color', sa.String(), nullable=True))
    op.add_column('badges', sa.Column('selected_image_font', sa.String(), nullable=True))
    op.add_column('badges', sa.Column('selected_font_size', sa.Integer(), nullable=True))
    op.add_column('badges', sa.Column('selected_text_x', sa.Integer(), nullable=True))
    op.add_column('badges', sa.Column('selected_text_y', sa.Integer(), nullable=True))
    op.execute("DROP TABLE IF EXISTS work_queue")


def downgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS work_queue (
        id SERIAL PRIMARY KEY,
        unique_id VARCHAR NOT NULL,
        name TEXT NOT NULL,
        image_label VARCHAR NOT NULL,
        image_base64 TEXT NOT NULL,
        image_mime_type VARCHAR,
        image_color VARCHAR NOT NULL,
        image_font VARCHAR NOT NULL,
        font_size INTEGER,
        text_x INTEGER,
        text_y INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        processed_at TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_queue_processed_created ON work_queue (processed_at, created_at)")
    op.drop_column('badges', 'selected_text_y')
    op.drop_column('badges', 'selected_text_x')
    op.drop_column('badges', 'selected_font_size')
    op.drop_column('badges', 'selected_image_font')
    op.drop_column('badges', 'selected_image_color')
    op.drop_column('badges', 'selected_image_mime_type')
    op.drop_column('badges', 'selected_image_base64')
    op.drop_column('badges', 'selected_image_label')
    op.drop_column('badges', 'firmware_base64')
    op.drop_column('badges', 'firmware_hash')
