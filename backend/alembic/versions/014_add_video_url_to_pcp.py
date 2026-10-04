"""Add video_url column to published_content_performance

Revision ID: 014
Revises: 013
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "published_content_performance",
        sa.Column("video_url", sa.String(1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("published_content_performance", "video_url")