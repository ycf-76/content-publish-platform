"""SQLAlchemy ORM models (Phase 1 + Phase 1 补漏)."""
import enum
import secrets
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, Boolean, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base, is_sqlite, is_mysql

# 非 PostgreSQL 兼容：PostgreSQL 用 JSONB，SQLite/MySQL 降级为 JSON
if is_sqlite or is_mysql:
    JSONB = JSON  # type: ignore[assignment,misc]
else:
    from sqlalchemy.dialects.postgresql import JSONB  # noqa: F401


def generate_ulid() -> str:
    """Generate ULID string (26 chars, time-sortable)."""
    return secrets.token_urlsafe(16)


# ===== Enums =====

class LoginMethod(enum.StrEnum):
    """D1 layered login method."""
    PLUGIN = "plugin"
    SESSION_REFRESH = "session_refresh"
    QRCODE = "qrcode"


class AccountStatus(enum.StrEnum):
    """XHS account status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    BANNED = "banned"


class WorkflowStatus(enum.StrEnum):
    """Workflow status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    TERMINATED = "terminated"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    FAILED = "failed"


class NodeState(enum.StrEnum):
    """Node state (LangGraph compatible)."""
    SEARCH = "search"
    ANALYZE = "analyze"
    IMAGE_GEN = "image_gen"
    IMAGE_REVIEW = "image_review"
    COPYWRITE = "copywrite"
    AUDIT = "audit"
    FINAL_REVIEW = "final_review"
    PUBLISH = "publish"
    END = "end"


# ===== Tables =====

class User(Base):
    """Platform user."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class XhsAccount(Base):
    """XHS account table."""
    __tablename__ = "xhs_accounts"
    __table_args__ = (
        Index("ix_xhs_accounts_user_id", "user_id"),
        Index("ix_xhs_accounts_xhs_user_id", "xhs_user_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    xhs_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    xhs_nickname: Mapped[str | None] = mapped_column(String(255))
    xhs_avatar_url: Mapped[str | None] = mapped_column(String(1024))
    session_data_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_method: Mapped[LoginMethod] = mapped_column(
        Enum(LoginMethod, native_enum=True, name="login_method",
             values_callable=lambda e: [x.value for x in e]),
        default=LoginMethod.PLUGIN,
        nullable=False,
    )
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, native_enum=True, name="account_status",
             values_callable=lambda e: [x.value for x in e]),
        default=AccountStatus.ACTIVE,
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Workflow(Base):
    """Workflow run."""
    __tablename__ = "workflows"
    __table_args__ = (
        Index("ix_workflows_user_id", "user_id"),
        Index("ix_workflows_account_id", "account_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("xhs_accounts.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, native_enum=True, name="workflow_status",
             values_callable=lambda e: [x.value for x in e]),
        default=WorkflowStatus.PENDING,
        nullable=False,
    )
    current_node_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    # D15 30分钟挂起用
    suspended_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

# ===== Additional Enums =====

class NodeType(enum.StrEnum):
    """Node type."""
    SEARCH = "search"
    ANALYZE = "analyze"
    IMAGE_GEN = "image_gen"
    IMAGE_REVIEW = "image_review"
    COPYWRITE = "copywrite"
    AUDIT = "audit"
    FINAL_REVIEW = "final_review"
    PUBLISH = "publish"
    # 第一期新增：图片规划节点（LLM 分析文案 → 输出图片类型+模板数据）
    IMAGE_PLAN = "image_plan"
    # 第二期预留：用户编排工作台（替代 image_review，本期待定）
    IMAGE_WORKSHOP = "image_workshop"


class NodeStatus(enum.StrEnum):
    """Node status. 9 种状态对应《前后端通信协议》第4章。"""
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    PASSED = "passed"
    REJECTED = "rejected"
    ERROR = "error"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    TERMINATED = "terminated"


# ===== Additional Tables =====

class WorkflowNode(Base):
    """Workflow node. 对应手册 Phase 1 第 4 张表。"""
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        Index("ix_workflow_nodes_workflow_id", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    workflow_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    node_type: Mapped[NodeType] = mapped_column(
        Enum(NodeType, native_enum=True, name="node_type",
             values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Python 属性用 node_status，DB 列名是 status（与 migration 对齐）
    node_status: Mapped[NodeStatus] = mapped_column(
        "status",
        Enum(NodeStatus, native_enum=True, name="node_status",
             values_callable=lambda e: [x.value for x in e]),
        default=NodeStatus.PENDING,
        nullable=False,
    )
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # D11: output_data 不含原图 base64，只存 VL 标签 / 文案 / 元数据
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    crash_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recovery_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ===== Phase 1 补漏：4 张表 =====

class WorkflowCheckpoint(Base):
    """D6: 业务层 checkpoint 索引表（用于时光机 UI）。

    LangGraph 自身的 checkpoint 由 PostgresSaver 自动管理，
    这里只存"人类可读的索引"方便前端时光机列表展示。
    """
    __tablename__ = "workflow_checkpoints"
    __table_args__ = (
        Index("ix_workflow_checkpoints_workflow_id", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    workflow_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("workflow_nodes.id", ondelete="SET NULL"), nullable=True
    )
    langgraph_thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    langgraph_checkpoint_id: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TraceEventType(enum.StrEnum):
    """D16 trace 事件类型。"""
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    PROGRESS_UPDATE = "progress_update"
    MODEL_SWITCHED = "model_switched"
    AGENT_THINKING = "agent_thinking"
    DECISION_MADE = "decision_made"


class AgentTrace(Base):
    """D16: 过程透明化，L3 原始数据存 DB（按需访问）。"""
    __tablename__ = "agent_traces"
    __table_args__ = (
        Index("ix_agent_traces_node_id_created", "node_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    node_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[TraceEventType] = mapped_column(
        Enum(TraceEventType, native_enum=True, name="trace_event_type",
             values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    event_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReviewType(enum.StrEnum):
    """人工审核类型。"""
    IMAGE_REVIEW = "image_review"
    FINAL_REVIEW = "final_review"
    STRUCTURAL_RECOVERY = "structural_recovery"  # D15 结构性恢复也走这里


class ReviewStatus(enum.StrEnum):
    """审核状态。"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class PendingReview(Base):
    """人工审核待办。"""
    __tablename__ = "pending_reviews"
    __table_args__ = (
        Index("ix_pending_reviews_workflow_id", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    workflow_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("workflow_nodes.id", ondelete="SET NULL"), nullable=True
    )
    review_type: Mapped[ReviewType] = mapped_column(
        Enum(ReviewType, native_enum=True, name="review_type",
             values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=True, name="review_status",
             values_callable=lambda e: [x.value for x in e]),
        default=ReviewStatus.PENDING,
        nullable=False,
    )
    user_decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SuggestionSeverity(enum.StrEnum):
    """监督建议严重级别。

    注意：name 必须和 value 一致（小写），否则 SQLAlchemy Enum
    默认存 name 会导致 DB 读取时大小写不匹配。
    """
    info = "info"
    warning = "warning"
    error = "error"


class SuggestionType(enum.StrEnum):
    """D15 监督建议类型。"""
    technical = "technical"
    structural = "structural"


class SuggestionStatus(enum.StrEnum):
    """监督建议状态。"""
    pending = "pending"
    auto_executed = "auto_executed"
    user_confirmed = "user_confirmed"
    user_rejected = "user_rejected"
    timeout = "timeout"


class PendingSuggestion(Base):
    """D4 建议权 + D15 技术/结构性分类。"""
    __tablename__ = "pending_suggestions"
    __table_args__ = (
        Index("ix_pending_suggestions_workflow_id", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    workflow_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("workflow_nodes.id", ondelete="SET NULL"), nullable=True
    )
    severity: Mapped[SuggestionSeverity] = mapped_column(
        Enum(SuggestionSeverity, native_enum=True, name="suggestion_severity",
             values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    suggestion_type: Mapped[SuggestionType] = mapped_column(
        Enum(SuggestionType, native_enum=True, name="suggestion_type",
             values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proposed_action: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus, native_enum=True, name="suggestion_status",
             values_callable=lambda e: [x.value for x in e]),
        default=SuggestionStatus.pending,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ===== 选题池（v5）：其他平台内容存入选题池供日后创作参考 =====

class TopicPoolItem(Base):
    """选题池条目：来自 HackerNews/Reddit/tavily 等非小红书平台的内容。

    工作流 search 节点搜索小红书时，后台 fire-and-forget 抓取其他平台
    内容存入此表，供用户在选题池页面浏览、筛选、收藏、一键发起新工作流。
    """
    __tablename__ = "topic_pool_items"
    __table_args__ = (
        Index("ix_topic_pool_platform", "platform"),
        Index("ix_topic_pool_source_keyword", "source_keyword"),
        Index("ix_topic_pool_is_favorited", "is_favorited"),
        Index("ix_topic_pool_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    collects: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shares: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fans_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cover_img: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    images: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source_keyword: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_favorited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ===== 监控模块扩展字段（v6 合并：监控数据直接写选题池）=====
    # auto_source="manual"：用户手动抓取（原有逻辑）
    # auto_source="monitor"：监控定时抓取并评分入库（pool_monitor 模块）
    auto_source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    simhash_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heat_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    heat_status: Mapped[str] = mapped_column(String(20), default="活跃", nullable=False)
    dimensions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ===== 详情页扩展字段（v7）=====
    # tags：从标题/内容/摘要中提取的关键词标签（LLM 生成，便于标签筛选和关联推荐）
    # ai_summary：AI 生成的详细摘要（与原 summary 区分：原 summary 是抓取原始摘要，
    #             ai_summary 是 LLM 基于完整 content 字段重新生成的深度摘要）
    # view_count：详情页访问次数，用于热度排序参考
    # ai_summary_generated_at：AI 摘要生成时间，用于判断是否需要重新生成
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_summary_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ===== 用户级智能体记忆（跨工作流长期记忆）=====

class MemoryType(enum.StrEnum):
    """记忆类型。

    - preferences: 用户偏好（文风/图片风格/主题类别），user_explicit 或 workflow_inferred
    - topic_history: 历史选题记录，避免重复创作
    - copywrite_history: 最近文案摘要，供 LLM 学习用户风格
    - publish_history: 已发布笔记记录
    """
    PREFERENCES = "preferences"
    TOPIC_HISTORY = "topic_history"
    COPYWRITE_HISTORY = "copywrite_history"
    PUBLISH_HISTORY = "publish_history"


class AgentMemory(Base):
    """用户级智能体长期记忆（跨工作流持久化）。

    设计：
    - 每条记忆 = user_id + memory_type + memory_key + memory_value
    - memory_key 细分：如 "writing_style" / "preferred_topics" / "avoided_topics"
    - memory_value 是 JSONB，存具体内容
    - 同一 (user_id, memory_type, memory_key) 唯一，upsert 更新
    - source 标记来源：user_explicit（用户显式设置）/ workflow_inferred（工作流推断）/ publish_feedback
    """
    __tablename__ = "agent_memories"
    __table_args__ = (
        Index("ix_agent_memories_user_id", "user_id"),
        Index("ix_agent_memories_user_type", "user_id", "memory_type"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, native_enum=True, name="memory_type",
             values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    memory_key: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(32), default="workflow_inferred", nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

