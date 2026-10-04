"""Add work_id to chat_sessions for conversation isolation

Revision ID: 007
Revises: 006
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("work_id", sa.String(100), nullable=True),
        )
    op.create_index(
        "ix_chat_sessions_work_id",
        "chat_sessions",
        ["work_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_work_id", table_name="chat_sessions")
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("work_id")