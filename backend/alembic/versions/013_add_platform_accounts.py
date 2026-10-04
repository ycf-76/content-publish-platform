"""Add platform_accounts table for account binding + works sync

Revision ID: 013
Revises: 012
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "e4e5d130d25f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_accounts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_uid", sa.String(128), nullable=True),
        sa.Column("platform_nickname", sa.String(128), nullable=True),
        sa.Column("platform_avatar_url", sa.String(1024), nullable=True),
        sa.Column("platform_home_url", sa.String(1024), nullable=True),
        sa.Column("cookies_json", sa.JSON, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("sync_error", sa.Text, nullable=True),
        sa.Column("works_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fans_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pa_user_id", "platform_accounts", ["user_id"])
    op.create_index("ix_pa_platform", "platform_accounts", ["platform"])
    op.create_unique_constraint("uq_pa_user_platform", "platform_accounts", ["user_id", "platform"])


def downgrade() -> None:
    op.drop_constraint("uq_pa_user_platform", "platform_accounts", type_="unique")
    op.drop_index("ix_pa_platform", table_name="platform_accounts")
    op.drop_index("ix_pa_user_id", table_name="platform_accounts")
    op.drop_table("platform_accounts")