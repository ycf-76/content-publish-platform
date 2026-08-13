"""init schema - 8 tables + 11 enum types

Revision ID: 20260724074510
Revises:
Create Date: 2026-07-24T07:45:10.473686+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260724074510"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum type definitions
ENUMS = {
    "login_method": ["plugin", "session_refresh", "qrcode"],
    "account_status": ["active", "expired", "banned"],
    "workflow_status": ["pending", "running", "awaiting_review", "suspended", "completed", "failed", "terminated"],
    "node_type": ["search", "analyze", "image_gen", "image_review", "copywrite", "audit", "final_review", "publish"],
    "node_status": ["pending", "running", "awaiting_review", "passed", "rejected", "error", "suspended", "completed", "terminated"],
    "trace_event_type": ["tool_call_start", "tool_call_end", "progress_update", "model_switched", "agent_thinking", "decision_made"],
    "review_type": ["image_review", "final_review", "structural_recovery"],
    "review_status": ["pending", "approved", "rejected", "timeout"],
    "suggestion_severity": ["info", "warning", "error"],
    "suggestion_type": ["technical", "structural"],
    "suggestion_status": ["pending", "auto_executed", "user_confirmed", "user_rejected", "timeout"],
}


def _enum(name):
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    # Create all enum types
    for name, values in ENUMS.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({vals})")

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 2. xhs_accounts
    op.create_table(
        "xhs_accounts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("xhs_user_id", sa.String(128), nullable=False),
        sa.Column("xhs_nickname", sa.String(255)),
        sa.Column("xhs_avatar_url", sa.String(1024)),
        sa.Column("session_data_encrypted", sa.Text()),
        sa.Column("refresh_token_encrypted", sa.Text()),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("login_method", _enum("login_method"), nullable=False, server_default="plugin"),
        sa.Column("status", _enum("account_status"), nullable=False, server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_xhs_accounts_user_id", "xhs_accounts", ["user_id"])
    op.create_index("ix_xhs_accounts_xhs_user_id", "xhs_accounts", ["xhs_user_id"])

    # 3. workflows
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(26), sa.ForeignKey("xhs_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("status", _enum("workflow_status"), nullable=False, server_default="pending"),
        sa.Column("current_node_id", sa.String(26)),
        sa.Column("suspended_until", sa.DateTime(timezone=True)),
        sa.Column("suspension_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    # 4. workflow_nodes
    op.create_table(
        "workflow_nodes",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workflow_id", sa.String(26), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", _enum("node_type"), nullable=False),
        sa.Column("node_key", sa.String(64), nullable=False),
        sa.Column("status", _enum("node_status"), nullable=False, server_default="pending"),
        sa.Column("input_data", postgresql.JSONB()),
        sa.Column("output_data", postgresql.JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column("crash_reason", sa.String(128)),
        sa.Column("recovery_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("token_usage", sa.Integer()),
        sa.Column("model_used", sa.String(128)),
    )

    # 5. workflow_checkpoints
    op.create_table(
        "workflow_checkpoints",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workflow_id", sa.String(26), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(26), sa.ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("langgraph_thread_id", sa.String(128), nullable=False),
        sa.Column("langgraph_checkpoint_id", sa.String(128), nullable=False),
        sa.Column("snapshot_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 6. agent_traces
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("node_id", sa.String(26), sa.ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", _enum("trace_event_type"), nullable=False),
        sa.Column("event_payload", postgresql.JSONB()),
        sa.Column("raw_data", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_traces_node_created", "agent_traces", ["node_id", "created_at"])

    # 7. pending_reviews
    op.create_table(
        "pending_reviews",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workflow_id", sa.String(26), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(26), sa.ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_type", _enum("review_type"), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("status", _enum("review_status"), nullable=False, server_default="pending"),
        sa.Column("user_decision", postgresql.JSONB()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 8. pending_suggestions
    op.create_table(
        "pending_suggestions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("workflow_id", sa.String(26), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(26), sa.ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", _enum("suggestion_severity"), nullable=False),
        sa.Column("suggestion_type", _enum("suggestion_type"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("trace", postgresql.JSONB()),
        sa.Column("proposed_action", postgresql.JSONB()),
        sa.Column("status", _enum("suggestion_status"), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("pending_suggestions")
    op.drop_table("pending_reviews")
    op.drop_index("ix_agent_traces_node_created", table_name="agent_traces")
    op.drop_table("agent_traces")
    op.drop_table("workflow_checkpoints")
    op.drop_table("workflow_nodes")
    op.drop_table("workflows")
    op.drop_index("ix_xhs_accounts_xhs_user_id", table_name="xhs_accounts")
    op.drop_index("ix_xhs_accounts_user_id", table_name="xhs_accounts")
    op.drop_table("xhs_accounts")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE {name}")
