"""Drop xhs_accounts table and related enums (QR login removed)

Revision ID: 011
Revises: 010
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    return table in inspect(bind).get_table_names()


def _fk_names(bind, table: str, ref_table: str) -> list[str]:
    if bind.dialect.name != "mysql":
        return []
    rows = bind.execute(sa.text(
        "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
        "AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
    ), {"t": table}).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists("xhs_accounts"):
        if bind.dialect.name == "mysql":
            for tbl in ("workflows", "task_plans"):
                if _table_exists(tbl):
                    for fk in _fk_names(bind, tbl, "xhs_accounts"):
                        try:
                            op.execute(f"ALTER TABLE {tbl} DROP FOREIGN KEY {fk}")
                        except Exception:
                            pass
            try:
                op.execute("ALTER TABLE xhs_accounts DROP INDEX ix_xhs_accounts_xhs_user_id")
            except Exception:
                pass
            try:
                op.execute("ALTER TABLE xhs_accounts DROP INDEX ix_xhs_accounts_user_id")
            except Exception:
                pass
        else:
            try:
                op.drop_index("ix_xhs_accounts_xhs_user_id", table_name="xhs_accounts", if_exists=True)
            except Exception:
                pass
            try:
                op.drop_index("ix_xhs_accounts_user_id", table_name="xhs_accounts", if_exists=True)
            except Exception:
                pass
        op.drop_table("xhs_accounts")

    if bind.dialect.name == "mysql":
        for enum_name in ("login_method", "account_status"):
            try:
                op.execute(f"DROP TYPE IF EXISTS {enum_name}")
            except Exception:
                pass


def downgrade() -> None:
    pass