"""Add folder_id to chat_sessions so conversations remember their workspace folder

Revision ID: 010
Revises: 009
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = inspect(bind).get_columns(table)
    return any(c["name"] == column for c in cols)


def upgrade() -> None:
    if not _column_exists("chat_sessions", "folder_id"):
        with op.batch_alter_table("chat_sessions") as batch_op:
            batch_op.add_column(
                sa.Column("folder_id", sa.String(100), nullable=False, server_default=""),
            )
        op.create_index(
            "ix_chat_sessions_folder_id",
            "chat_sessions",
            ["folder_id"],
        )


def downgrade() -> None:
    if _column_exists("chat_sessions", "folder_id"):
        op.drop_index("ix_chat_sessions_folder_id", table_name="chat_sessions")
        with op.batch_alter_table("chat_sessions") as batch_op:
            batch_op.drop_column("folder_id")
