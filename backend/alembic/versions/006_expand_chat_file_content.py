"""Expand chat_files.content_text for large analysis reports

Revision ID: 006
Revises: 005
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    with op.batch_alter_table("chat_files") as batch_op:
        batch_op.alter_column(
            "content_text",
            existing_type=sa.Text(),
            type_=mysql.LONGTEXT(),
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    with op.batch_alter_table("chat_files") as batch_op:
        batch_op.alter_column(
            "content_text",
            existing_type=mysql.LONGTEXT(),
            type_=sa.Text(),
            existing_nullable=True,
        )
