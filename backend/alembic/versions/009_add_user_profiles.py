"""Add user_profiles table (D18 创作者画像)

Revision ID: 009
Revises: 008
Create Date: 2026-09-11

Changes:
1. 新建 user_profiles 表（与 users 1:1，user_id 唯一索引）
2. primary_domain / tone / visual_style 三个枚举列
3. taboo_topics / taboo_words JSON 列
"""
from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if insp.has_table("user_profiles"):
        return

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "primary_domain",
            sa.Enum(
                "tech", "beauty", "food", "travel", "education",
                "parenting", "fitness", "finance", "other",
                name="primary_domain",
            ),
            nullable=False,
        ),
        sa.Column("sub_domain", sa.String(50), nullable=True),
        sa.Column(
            "tone",
            sa.Enum(
                "professional", "friendly", "lively", "serious", "humorous",
                name="creator_tone",
            ),
            nullable=False,
        ),
        sa.Column(
            "visual_style",
            sa.Enum("warm", "cool", "minimal", "rich", name="visual_style_enum"),
            nullable=False,
        ),
        sa.Column("taboo_topics", sa.JSON(), nullable=False),
        sa.Column("taboo_words", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table("user_profiles"):
        return

    op.drop_index("ix_user_profiles_user_id", table_name="user_profiles")
    op.drop_table("user_profiles")
