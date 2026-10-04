"""Add source column to workflows table

Revision ID: 004
Revises: 003
Create Date: 2026-08-23
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflows", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(20), server_default="gui", nullable=False),
        )


def downgrade() -> None:
    with op.batch_alter_table("workflows", schema=None) as batch_op:
        batch_op.drop_column("source")