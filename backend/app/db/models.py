"""SQLAlchemy ORM models (Phase 1 + Phase 1 补漏)."""
import enum
import secrets
from datetime import datetime
from typing import Optional

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
    """Generate real ULID string (26 chars, time-sortable, K-sortable).

    P2-10: 使用 ulid-py 库生成真正的 ULID，保证时间有序。
    格式：10 字符时间戳 + 16 字符随机部分 = 26 字符 Crockford Base32。
    """
    import ulid
    return str(ulid.new())


# ===== Enums =====

class LoginMethod(enum.StrEnum):
    """D1 layered login method."""
    PLUGIN = "plugin"
    SESSION_REFRESH = "session_refresh"
    QRCODE = "qrcode"
    EMAIL = "email"


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
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str] = mapped_column(String(128), default="", nullable=False)
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
    """Workflow run.

    Phase 1: 固定9节点流水线（向后兼容）
    Phase 2: 支持动态DAG执行（通过definition_id关联工作流定义）
    """
    __tablename__ = "workflows"
    __table_args__ = (
        Index("ix_workflows_user_id", "user_id"),
        Index("ix_workflows_account_id", "account_id"),
        Index("ix_workflows_definition_id", "definition_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("xhs_accounts.id", ondelete="SET NULL"), nullable=True
    )
    
    # Phase 2 新增：关联的工作流定义（可选）
    # 为NULL时表示使用默认的固定流程
    definition_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_definitions.id", ondelete="SET NULL"),
        nullable=True,
        comment="使用的工作流定义ID（NULL=使用默认流程）"
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
    
    # 执行模式
    execution_mode: Mapped[str] = mapped_column(
        String(20),
        default="sequential",
        comment="执行模式：sequential（顺序）/ dynamic（动态DAG）"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 关联关系
    definition: Mapped[Optional["WorkflowDefinition"]] = relationship(
        "WorkflowDefinition",
        back_populates="workflows",
        foreign_keys=[definition_id],
    )

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
        Index("ix_topic_pool_auto_source", "auto_source"),
        Index("ix_topic_pool_heat_score", "heat_score"),
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


# ===== Esther Factory 品牌配置 =====

class EstherBrandConfig(Base):
    """Esther Factory 品牌配置（每用户一行，头像存 base64）。"""
    __tablename__ = "esther_brand_configs"
    __table_args__ = (
        Index("ix_esther_brand_configs_user_id", "user_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    brand_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    gender: Mapped[str] = mapped_column(String(10), default="man", nullable=False)
    primary: Mapped[str] = mapped_column(String(7), default="#2B7FD8", nullable=False)
    accent: Mapped[str] = mapped_column(String(7), default="#F4D758", nullable=False)
    spot: Mapped[str] = mapped_column(String(7), default="#E84A5F", nullable=False)
    avatar_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EstherTemplate(Base):
    """Esther Factory 模板（每用户每模板一行）。"""
    __tablename__ = "esther_templates"
    __table_args__ = (
        Index("ix_esther_templates_user_id", "user_id"),
        Index("ix_esther_templates_user_tplid", "user_id", "template_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    template_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    template_html: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    scene: Mapped[str] = mapped_column(String(32), default="cards", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PublishedContentPerformance(Base):
    """发布内容的表现记录（T+7 回采）。

    分析智能体优化方案 阶段4：反馈闭环。
    记录每次发布内容采用了哪个分析模式/选题方向，
    7天后回采实际表现数据，用于校准 viral_score 权重。
    """
    __tablename__ = "published_content_performance"
    __table_args__ = (
        Index("ix_pcp_workflow_id", "workflow_id"),
        Index("ix_pcp_published_at", "published_at"),
        Index("ix_pcp_collected", "collected_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workflow_id: Mapped[str] = mapped_column(String(26), nullable=False)
    published_note_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selected_pattern: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    selected_direction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    collected_likes: Mapped[int] = mapped_column(Integer, default=0)
    collected_collects: Mapped[int] = mapped_column(Integer, default=0)
    collected_comments: Mapped[int] = mapped_column(Integer, default=0)
    collected_shares: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    performance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_replicated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalysisWeightHistory(Base):
    """分析权重的历史记录（用于追踪权重演变）。

    每次权重校准后记录旧值→新值，可追溯 viral_score 权重的演变过程。
    """
    __tablename__ = "analysis_weight_history"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    weight_name: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[float] = mapped_column(Float, nullable=False)
    new_value: Mapped[float] = mapped_column(Float, nullable=False)
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ===== Phase 2: 动态工作流编排支持 =====

class WorkflowDefinitionStatus(enum.StrEnum):
    """工作流定义状态."""
    DRAFT = "draft"                # 草稿
    ACTIVE = "active"              # 启用
    ARCHIVED = "archived"          # 归档
    DEPRECATED = "deprecated"      # 已废弃


class WorkflowDefinition(Base):
    """工作流定义模板（用户编排的可复用流程）.

    存储用户通过可视化编辑器创建的工作流DAG图定义，
    支持保存为模板、分享给团队、多次使用。

    与现有 Workflow 的关系：
    - WorkflowDefinition 是"模板/配方"
    - Workflow 是"实例/执行记录"
    - 一个 Definition 可以生成多个 Workflow 实例
    """
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        Index("ix_workflow_definitions_user_id", "user_id"),
        Index("ix_workflow_definitions_category", "category"),
        Index("ix_workflow_definitions_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(__import__('uuid').uuid4()))

    # 基本信息
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="工作流名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    icon: Mapped[str] = mapped_column(String(10), default="⚙️", comment="图标emoji")
    category: Mapped[str] = mapped_column(String(50), default="custom", comment="分类")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="版本号")

    # 所属用户
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="创建者ID")

    # DAG图定义（核心字段）
    graph_definition: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="""
        工作流图定义（JSON格式），包含：
        
        {
            "nodes": [
                {
                    "id": "node_1",
                    "type": "ai_copywrite",
                    "config": {"model": "deepseek-chat"},
                    "position": {"x": 100, "y": 200}
                }
            ],
            "edges": [
                {
                    "id": "edge_1",
                    "source": "node_1",
                    "target": "node_2",
                    "sourceHandle": "output-1",
                    "targetHandle": "input-1",
                    "condition": null,
                    "label": ""
                }
            ]
        }
        """
    )

    # 状态和可见性
    status: Mapped[WorkflowDefinitionStatus] = mapped_column(
        Enum(WorkflowDefinitionStatus, native_enum=True, name="wf_def_status"),
        default=WorkflowDefinitionStatus.DRAFT,
        nullable=False,
        comment="状态：草稿/启用/归档/废弃"
    )
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否为系统内置模板")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否公开分享")

    # 统计信息
    usage_count: Mapped[int] = mapped_column(Integer, default=0, comment="使用次数")
    success_count: Mapped[int] = mapped_column(Integer, default=0, comment="成功执行次数")
    avg_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="平均执行时长(ms)")

    # 元数据
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="标签列表")
    author_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="作者显示名")
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="缩略图URL")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关联关系
    workflows: Mapped[list["Workflow"]] = relationship(
        "Workflow",
        back_populates="definition",
        foreign_keys="Workflow.definition_id",
        lazy="dynamic",
    )


class WorkflowEdge(Base):
    """工作流边关系表（用于动态DAG执行）.

    记录节点之间的连接关系，支持：
    - 条件分支（condition表达式）
    - 多输入多输出
    - 数据映射

    此表主要用于运行时快速查询节点的上下游关系，
    图的完整定义仍存储在 WorkflowDefinition.graph_definition 中。
    """
    __tablename__ = "workflow_edges"
    __table_args__ = (
        Index("ix_workflow_edges_workflow_id", "workflow_id"),
        Index("ix_workflow_edges_source", "source_node_id"),
        Index("ix_workflow_edges_target", "target_node_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属工作流实例ID"
    )

    source_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
        comment="源节点ID"
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
        comment="目标节点ID"
    )

    source_handle: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="源节点的输出端口标识"
    )
    target_handle: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="目标节点的输入端口标识"
    )

    condition: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="""
        条件表达式（可选）。
        
        为空表示无条件执行；
        有值时只有表达式结果为true才执行目标节点。
        
        示例：
        - "${score} > 80"  (上游输出score>80才继续)
        - "${status} == 'approved'"  (审核通过才发布)
        
        表达式语法：简单的JavaScript-like表达式，
        变量引用上游节点的输出数据。
        """
    )

    label: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="边的标签（显示在连线上）"
    )
    
    data_mapping: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="""
        数据映射规则（可选）。
        
        用于将源节点的输出字段映射到目标节点的输入字段。
        
        示例：
        {
            "title": "${source.title}",
            "content": "${source.content}",
            "custom_field": "${source.output.keywords[0]}"
        }
        """
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===== Chat 驱动 Agent：会话与消息 =====

class ChatSession(Base):
    """Chat 会话（Chat 驱动 Agent 的多轮对话容器）。

    一个 Session 可触发多个 Workflow；关系通过 ChatMessage.agent_meta.workflow_id
    间接建立，不在这里加 workflow 外键。
    """
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_sessions_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), default="新会话", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(Base):
    """Chat 消息（一条消息可选关联一个 workflow）。"""
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    session_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # agent_meta 存 workflow_id / intent / workflow_status / steps 等，与 PRD v2 的
    # ChatMessage.agentMeta 对齐，工作流关系通过 agent_meta.workflow_id 间接建立。
    agent_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
