"""Add PublishedContentPerformance extension fields + MemoryType enum values

Revision ID: 005
Revises: 004
Create Date: 2026-08-23

Changes:
1. published_content_performance: add platform, predicted_viral_score,
   actual_viral_score, prediction_error, title, content_text, tags,
   cover_img_url, title_pattern, emotion_trigger, content_structure
2. published_content_performance: add index ix_pcp_user_platform
3. agent_memories: expand memory_type enum to include
   my_works_summary, my_attribution, avoid_patterns
"""

from alembic import op
import sqlalchemy as sa


revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    existing_cols = {c["name"] for c in insp.get_columns("published_content_performance")}
    existing_indexes = {idx["name"] for idx in insp.get_indexes("published_content_performance")}

    with op.batch_alter_table("published_content_performance") as batch_op:
        if "platform" not in existing_cols:
            batch_op.add_column(sa.Column("platform", sa.String(32), nullable=False, server_default="xiaohongshu"))
        if "predicted_viral_score" not in existing_cols:
            batch_op.add_column(sa.Column("predicted_viral_score", sa.Float(), nullable=True))
        if "actual_viral_score" not in existing_cols:
            batch_op.add_column(sa.Column("actual_viral_score", sa.Float(), nullable=True))
        if "prediction_error" not in existing_cols:
            batch_op.add_column(sa.Column("prediction_error", sa.Float(), nullable=True))
        if "title" not in existing_cols:
            batch_op.add_column(sa.Column("title", sa.String(512), nullable=True))
        if "content_text" not in existing_cols:
            batch_op.add_column(sa.Column("content_text", sa.Text(), nullable=True))
        if "tags" not in existing_cols:
            batch_op.add_column(sa.Column("tags", sa.JSON(), nullable=True))
        if "cover_img_url" not in existing_cols:
            batch_op.add_column(sa.Column("cover_img_url", sa.String(1024), nullable=True))
        if "title_pattern" not in existing_cols:
            batch_op.add_column(sa.Column("title_pattern", sa.String(32), nullable=True))
        if "emotion_trigger" not in existing_cols:
            batch_op.add_column(sa.Column("emotion_trigger", sa.String(32), nullable=True))
        if "content_structure" not in existing_cols:
            batch_op.add_column(sa.Column("content_structure", sa.String(128), nullable=True))

        if "ix_pcp_user_platform" not in existing_indexes:
            batch_op.create_index("ix_pcp_user_platform", ["user_id", "platform"])

    try:
        with op.batch_alter_table("agent_memories") as batch_op:
            existing_type_vals = {"preferences", "topic_history", "copywrite_history", "publish_history"}
            new_vals = existing_type_vals | {"my_works_summary", "my_attribution", "avoid_patterns"}
            batch_op.alter_column(
                "memory_type",
                existing_type=sa.Enum(*existing_type_vals, name="memory_type"),
                type_=sa.Enum(*new_vals, name="memory_type"),
                existing_nullable=False,
            )
    except Exception:
        pass


def downgrade() -> None:
    with op.batch_alter_table("published_content_performance") as batch_op:
        batch_op.drop_index("ix_pcp_user_platform")
        batch_op.drop_column("content_structure")
        batch_op.drop_column("emotion_trigger")
        batch_op.drop_column("title_pattern")
        batch_op.drop_column("cover_img_url")
        batch_op.drop_column("tags")
        batch_op.drop_column("content_text")
        batch_op.drop_column("title")
        batch_op.drop_column("prediction_error")
        batch_op.drop_column("actual_viral_score")
        batch_op.drop_column("predicted_viral_score")
        batch_op.drop_column("platform")