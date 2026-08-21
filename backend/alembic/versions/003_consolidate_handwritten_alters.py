"""Consolidate all handwritten ALTER TABLE from main.py lifespan

Revision ID: 003
Revises: 002
Create Date: 2026-08-21

Migrated from main.py lifespan:
1. topic_pool_items v2: collects, shares, fans_count, images
2. topic_pool_items v6: auto_source, simhash_fingerprint, heat_score,
   heat_status, dimensions, published_at
3. topic_pool_items v7: tags, ai_summary, view_count, ai_summary_generated_at
4. topic_pool_items indexes: ix_topic_pool_auto_source, ix_topic_pool_heat_score
5. esther_brand_configs: gender
6. users: email, password_hash, nickname

All columns use IF NOT EXISTS pattern via batch_alter_table
so this migration is idempotent and safe for databases that
already have these columns (from the old main.py lifespan path).
"""

from alembic import op
import sqlalchemy as sa


revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    existing_cols = {c["name"] for c in insp.get_columns("topic_pool_items")}
    existing_indexes = {idx["name"] for idx in insp.get_indexes("topic_pool_items")}

    with op.batch_alter_table("topic_pool_items") as batch_op:
        if "collects" not in existing_cols:
            batch_op.add_column(sa.Column("collects", sa.Integer(), nullable=False, server_default="0"))
        if "shares" not in existing_cols:
            batch_op.add_column(sa.Column("shares", sa.Integer(), nullable=False, server_default="0"))
        if "fans_count" not in existing_cols:
            batch_op.add_column(sa.Column("fans_count", sa.Integer(), nullable=False, server_default="0"))
        if "images" not in existing_cols:
            batch_op.add_column(sa.Column("images", sa.JSON(), nullable=True))
        if "auto_source" not in existing_cols:
            batch_op.add_column(sa.Column("auto_source", sa.String(20), nullable=False, server_default="manual"))
        if "simhash_fingerprint" not in existing_cols:
            batch_op.add_column(sa.Column("simhash_fingerprint", sa.String(64), nullable=True))
        if "heat_score" not in existing_cols:
            batch_op.add_column(sa.Column("heat_score", sa.Float(), nullable=False, server_default="0"))
        if "heat_status" not in existing_cols:
            batch_op.add_column(sa.Column("heat_status", sa.String(20), nullable=False, server_default="活跃"))
        if "dimensions" not in existing_cols:
            batch_op.add_column(sa.Column("dimensions", sa.JSON(), nullable=True))
        if "published_at" not in existing_cols:
            batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        if "tags" not in existing_cols:
            batch_op.add_column(sa.Column("tags", sa.JSON(), nullable=True))
        if "ai_summary" not in existing_cols:
            batch_op.add_column(sa.Column("ai_summary", sa.Text(), nullable=True))
        if "view_count" not in existing_cols:
            batch_op.add_column(sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"))
        if "ai_summary_generated_at" not in existing_cols:
            batch_op.add_column(sa.Column("ai_summary_generated_at", sa.DateTime(timezone=True), nullable=True))

    if "ix_topic_pool_auto_source" not in existing_indexes:
        op.create_index("ix_topic_pool_auto_source", "topic_pool_items", ["auto_source"])
    if "ix_topic_pool_heat_score" not in existing_indexes:
        op.create_index("ix_topic_pool_heat_score", "topic_pool_items", ["heat_score"])

    try:
        ebc_cols = {c["name"] for c in insp.get_columns("esther_brand_configs")}
    except Exception:
        ebc_cols = set()

    if ebc_cols:
        with op.batch_alter_table("esther_brand_configs") as batch_op:
            if "gender" not in ebc_cols:
                batch_op.add_column(sa.Column("gender", sa.String(10), nullable=False, server_default="man"))

    try:
        user_cols = {c["name"] for c in insp.get_columns("users")}
    except Exception:
        user_cols = set()

    if user_cols:
        with op.batch_alter_table("users") as batch_op:
            if "email" not in user_cols:
                batch_op.add_column(sa.Column("email", sa.String(255), nullable=True, unique=True))
            if "password_hash" not in user_cols:
                batch_op.add_column(sa.Column("password_hash", sa.String(255), nullable=True))
            if "nickname" not in user_cols:
                batch_op.add_column(sa.Column("nickname", sa.String(128), nullable=False, server_default=""))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    existing_indexes = {idx["name"] for idx in insp.get_indexes("topic_pool_items")}

    if "ix_topic_pool_heat_score" in existing_indexes:
        op.drop_index("ix_topic_pool_heat_score", table_name="topic_pool_items")
    if "ix_topic_pool_auto_source" in existing_indexes:
        op.drop_index("ix_topic_pool_auto_source", table_name="topic_pool_items")

    with op.batch_alter_table("topic_pool_items") as batch_op:
        batch_op.drop_column("ai_summary_generated_at")
        batch_op.drop_column("view_count")
        batch_op.drop_column("ai_summary")
        batch_op.drop_column("tags")
        batch_op.drop_column("published_at")
        batch_op.drop_column("dimensions")
        batch_op.drop_column("heat_status")
        batch_op.drop_column("heat_score")
        batch_op.drop_column("simhash_fingerprint")
        batch_op.drop_column("auto_source")
        batch_op.drop_column("images")
        batch_op.drop_column("fans_count")
        batch_op.drop_column("shares")
        batch_op.drop_column("collects")

    try:
        ebc_cols = {c["name"] for c in insp.get_columns("esther_brand_configs")}
        if "gender" in ebc_cols:
            with op.batch_alter_table("esther_brand_configs") as batch_op:
                batch_op.drop_column("gender")
    except Exception:
        pass

    try:
        user_cols = {c["name"] for c in insp.get_columns("users")}
        with op.batch_alter_table("users") as batch_op:
            if "nickname" in user_cols:
                batch_op.drop_column("nickname")
            if "password_hash" in user_cols:
                batch_op.drop_column("password_hash")
            if "email" in user_cols:
                batch_op.drop_column("email")
    except Exception:
        pass