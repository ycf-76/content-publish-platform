"""Drop esther_brand_configs and esther_templates tables (esther_factory removed)

Revision ID: 012
Revises: 011
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    return table in inspect(bind).get_table_names()


def upgrade() -> None:
    for table_name in ("esther_templates", "esther_brand_configs"):
        if _table_exists(table_name):
            op.drop_table(table_name)


def downgrade() -> None:
    pass