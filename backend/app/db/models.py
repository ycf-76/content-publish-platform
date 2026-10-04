"""SQLAlchemy ORM models (Phase 1 + Phase 1 补漏)."""
import enum
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, Boolean, UniqueConstraint, func
from sqlalchemy import JSON
from sqlalchemy.dialects.mysql import LONGTEXT
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


# ===== D18 用户画像枚举 =====

class PrimaryDomain(enum.StrEnum):
    """创作者主领域（必填）"""
    TECH = "tech"            # 科技
    BEAUTY = "beauty"        # 美妆
    FOOD = "food"            # 美食
    TRAVEL = "travel"        # 旅行
    EDUCATION = "education"  # 教育
    PARENTING = "parenting"  # 母婴
    FITNESS = "fitness"      # 健身
    FINANCE = "finance"      # 财经
    OTHER = "other"          # 其他


class CreatorTone(enum.StrEnum):
    """内容调性"""
    PROFESSIONAL = "professional"  # 专业
    FRIENDLY = "friendly"          # 亲和
    LIVELY = "lively"              # 活泼
    SERIOUS = "serious"            # 严肃
    HUMOROUS = "humorous"          # 幽默


class VisualStyle(enum.StrEnum):
    """视觉风格"""
    WARM = "warm"        # 暖色调
    COOL = "cool"        # 冷色调
    MINIMAL = "minimal"  # 极简
    RICH = "rich"        # 丰富


class UserProfile(Base):
    """D18 创作者画像。与 users 1:1（user_id 唯一）。

    红线（开发红线手册 7.4）：
    - primary_domain 必填（应用层校验）
    - 每次启动工作流前必须读取注入 WorkflowState
    - 画像缺失时拒绝启动工作流
    - 只存创作偏好，不存敏感个人信息
    """
    __tablename__ = "user_profiles"
    __table_args__ = (
        Index("ix_user_profiles_user_id", "user_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    primary_domain: Mapped[str] = mapped_column(
        Enum(PrimaryDomain, native_enum=True, name="primary_domain",
             values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    sub_domain: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tone: Mapped[str] = mapped_column(
        Enum(CreatorTone, native_enum=True, name="creator_tone",
             values_callable=lambda e: [x.value for x in e]),
        default=CreatorTone.PROFESSIONAL,
        nullable=False,
    )
    visual_style: Mapped[str] = mapped_column(
        Enum(VisualStyle, native_enum=True, name="visual_style_enum",
             values_callable=lambda e: [x.value for x in e]),
        default=VisualStyle.WARM,
        nullable=False,
    )
    taboo_topics: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    taboo_words: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    identity: Mapped[str | None] = mapped_column(String(200), nullable=True)
    differentiation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_direction: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(200), nullable=True)
    audience_pain_points: Mapped[str | None] = mapped_column(String(200), nullable=True)
    opening_style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_rhythm: Mapped[str | None] = mapped_column(String(100), nullable=True)
    signature_elements: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FeishuOAuthConnection(Base):
    """用户绑定的飞书 OAuth 账号。

    access_token / refresh_token 只能以 AES-GCM 密文保存；user_id 唯一，
    用于在智能体调用 Wiki/Doc 时按当前平台用户选择对应的 user_access_token。
    """
    __tablename__ = "feishu_oauth_connections"
    __table_args__ = (
        Index("ix_feishu_oauth_connections_user_id", "user_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    open_id: Mapped[str | None] = mapped_column(String(128))
    user_name: Mapped[str | None] = mapped_column(String(255))
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FeishuOAuthState(Base):
    """短期 OAuth state/PKCE 状态，防止回调被伪造。"""
    __tablename__ = "feishu_oauth_states"
    __table_args__ = (Index("ix_feishu_oauth_states_state", "state", unique=True),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    state: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(String(26), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
        String(26), nullable=True
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
    
    # 来源标记
    source: Mapped[str] = mapped_column(
        String(20),
        default="gui",
        comment="发起来源: gui | chat_agent"
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
    # 后处理节点：卡片生成 + 微信推送 + 飞书推送
    CARD_GEN = "card_gen"
    WECHAT_PUSH = "wechat_push"
    FEISHU_PUSH = "feishu_push"


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
    - my_works_summary: 我的作品归因摘要（SelfAttributionEngine 产出）
    - my_attribution: 写作处方（什么标题模式/情绪触发/内容结构对我有效）
    - avoid_patterns: 避坑清单（我试过但效果差的模式）
    """
    PREFERENCES = "preferences"
    TOPIC_HISTORY = "topic_history"
    COPYWRITE_HISTORY = "copywrite_history"
    PUBLISH_HISTORY = "publish_history"
    MY_WORKS_SUMMARY = "my_works_summary"
    MY_ATTRIBUTION = "my_attribution"
    AVOID_PATTERNS = "avoid_patterns"


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





class ImageAsset(Base):
    """User-uploaded image asset for template-free image mode."""
    __tablename__ = "image_assets"
    __table_args__ = (
        Index("ix_image_assets_user_id", "user_id"),
        Index("ix_image_assets_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="upload", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PublishedContentPerformance(Base):
    """发布内容的表现记录（T+7 回采）。

    分析智能体优化方案 阶段4：反馈闭环。
    记录每次发布内容采用了哪个分析模式/选题方向，
    7天后回采实际表现数据，用于校准 viral_score 权重。

    扩展字段（AI多平台分析文档 P0）：
    - platform: 目标平台标识（xiaohongshu/douyin/bilibili/wechat）
    - predicted_viral_score / actual_viral_score / prediction_error: 预测校准
    - title / content_text / tags / cover_img_url: 内容特征快照
    - title_pattern / emotion_trigger / content_structure: 归因标签
    """
    __tablename__ = "published_content_performance"
    __table_args__ = (
        Index("ix_pcp_workflow_id", "workflow_id"),
        Index("ix_pcp_published_at", "published_at"),
        Index("ix_pcp_collected", "collected_at"),
        Index("ix_pcp_user_platform", "user_id", "platform"),
        Index("ix_pcp_user_status", "user_id", "content_status"),
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

    platform: Mapped[str] = mapped_column(String(32), default="xiaohongshu", nullable=False)
    content_status: Mapped[str] = mapped_column(
        String(16), default="published", nullable=False,
        comment="draft=草稿 / published=已发布待采集 / collected=已采集有数据"
    )
    predicted_viral_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_viral_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_error: Mapped[float | None] = mapped_column(Float, nullable=True)

    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_text: Mapped[Text | None] = mapped_column(Text, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cover_img_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    images: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    title_pattern: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emotion_trigger: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_structure: Mapped[str | None] = mapped_column(String(128), nullable=True)
    card_draft: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    first_page_html: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    work_id 将对话绑定到具体作品，实现对话隔离。
    """
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_sessions_user_id", "user_id"),
        Index("ix_chat_sessions_work_id", "work_id"),
        Index("ix_chat_sessions_folder_id", "folder_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    work_id: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    folder_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(255), default="新会话", nullable=False)
    creative_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
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


class ChatFile(Base):
    """Chat 会话中创建的文件（文案、搜索结果、分析报告等）。

    关联 session_id，点击文件可跳回所属对话。
    """
    __tablename__ = "chat_files"
    __table_args__ = (
        Index("ix_chat_files_session_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    session_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), default="text/plain", nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    folder_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    content_text: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"), nullable=True
    )
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ===== 任务清单（多日定时发布）=====

class TaskPlanStatus(enum.StrEnum):
    """任务清单状态。

    draft: 拆解完成待用户确认；active: 生效中（调度器扫描）；
    paused: 暂停（保留现场，可恢复）；completed: 全部发布完成；cancelled: 取消。
    """
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskItemStatus(enum.StrEnum):
    """逐日子任务状态。"""
    PENDING = "pending"
    RUNNING = "running"
    SKIPPED = "skipped"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskRunStatus(enum.StrEnum):
    """单日执行记录状态。

    awaiting_confirmation: 工作流挂起中，已发飞书卡片等待用户决策。
    """
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class TaskPlan(Base):
    """多日任务清单（用户一句话意图 → 智能体拆解 → 每日定时执行）。

    plan_config 结构：
    - daily_time: "09:00" 每日发布时间（HH:MM，Asia/Shanghai）
    - review_mode: quality_gate | auto | manual（审核三档）
    - model_settings: 传给 start_workflow 的模型配置（含 auto_publish）
    - definition_name: 使用的内置工作流定义名（默认「定时发布流水线」）
    - confirm_timeout_min: 飞书确认超时分钟数（默认 30）
    - max_retry: 当日失败重试上限（默认 1）
    - feishu_open_id: 接收确认卡片的用户 open_id（可选）
    """
    __tablename__ = "task_plans"
    __table_args__ = (
        Index("ix_task_plans_user_id", "user_id"),
        Index("ix_task_plans_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[str | None] = mapped_column(
        String(26), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    intent_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[TaskPlanStatus] = mapped_column(
        Enum(TaskPlanStatus, native_enum=True, name="task_plan_status",
             values_callable=lambda e: [x.value for x in e]),
        default=TaskPlanStatus.DRAFT,
        nullable=False,
    )
    plan_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaskItem(Base):
    """逐日子任务（清单拆解后的单日条目）。

    扫描主索引 (status, plan_time)：调度器每分钟捞
    status=pending AND plan_time<=now 且所属 plan 为 active 的条目。
    """
    __tablename__ = "task_items"
    __table_args__ = (
        Index("ix_task_items_due", "status", "plan_time"),
        Index("ix_task_items_plan_id", "plan_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    plan_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("task_plans.id", ondelete="CASCADE"), nullable=False
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    topic: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    keyword: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plan_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[TaskItemStatus] = mapped_column(
        Enum(TaskItemStatus, native_enum=True, name="task_item_status",
             values_callable=lambda e: [x.value for x in e]),
        default=TaskItemStatus.PENDING,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TaskRun(Base):
    """单日执行记录（一次 TaskItem 触发的工作流运行现场 + 异常快照）。"""
    __tablename__ = "task_runs"
    __table_args__ = (
        Index("ix_task_runs_item", "task_item_id"),
        Index("ix_task_runs_plan", "plan_id"),
        Index("ix_task_runs_workflow", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    task_item_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("task_items.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("task_plans.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    status: Mapped[TaskRunStatus] = mapped_column(
        Enum(TaskRunStatus, native_enum=True, name="task_run_status",
             values_callable=lambda e: [x.value for x in e]),
        default=TaskRunStatus.RUNNING,
        nullable=False,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ===== 通用浏览器自动化：审计日志 =====

class BrowserAuditLog(Base):
    """浏览器自动化审计日志（G4）。

    记录每次导航 / 交互动作（来源 agent 或 mcp），供回溯「谁在什么时候
    对哪个网站做了什么」。写入方为 BrowserClient 的 audit sink
    （fire-and-forget，失败不影响主流程）。
    """
    __tablename__ = "browser_audit_logs"
    __table_args__ = (
        Index("ix_browser_audit_created_at", "created_at"),
        Index("ix_browser_audit_domain", "domain"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="agent",
        comment="调用来源：agent（内部智能体）/ mcp（外部 MCP 客户端）"
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="动作：navigate / act:click / act:fill ...")
    domain: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="目标域名")
    url: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="目标 URL")
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否成功")
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="失败原因等补充信息")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ===== 平台账号管理（账号绑定 + 作品数据回收）=====

class PlatformAccount(Base):
    """用户绑定的各平台账号。

    存储扫码登录获取的 cookies 和平台用户信息，
    供 Spider 爬取该账号下的全部已发布作品数据。
    platform 枚举值对齐 PublishedContentPerformance.platform：
    xiaohongshu / douyin / bilibili
    """
    __tablename__ = "platform_accounts"
    __table_args__ = (
        Index("ix_pa_user_id", "user_id"),
        Index("ix_pa_platform", "platform"),
        UniqueConstraint("user_id", "platform", name="uq_pa_user_platform"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=generate_ulid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    platform_home_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cookies_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(16), default="idle", nullable=False)
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    works_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fans_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())