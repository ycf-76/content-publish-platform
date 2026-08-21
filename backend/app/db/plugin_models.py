"""
Plugin System ORM Models (Day 4)
插件系统数据库模型定义

包含6张核心表：
1. plugins - 插件注册信息
2. plugin_versions - 版本历史
3. plugin_configs - 用户配置
4. plugin_reviews - 用户评价
5. audit_logs - 审计日志
6. plugin_stats - 运行统计
"""

import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    JSON,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# ===== Enums =====

class PluginCategory(str, enum.Enum):
    """Plugin category classification."""
    PLATFORM = "PLATFORM"
    DATASOURCE = "DATASOURCE"
    WORKFLOW_NODE = "WORKFLOW_NODE"
    AI_MODEL = "AI_MODEL"
    UI_THEME = "UI_THEME"
    INTEGRATION = "INTEGRATION"


class PluginStatus(str, enum.Enum):
    """Plugin lifecycle status."""
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    DEPRECATED = "DEPRECATED"


class PricingModel(str, enum.Enum):
    """Pricing model types."""
    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"


class AuditAction(str, enum.Enum):
    """Audit log action types."""
    PLUGIN_INSTALL = "plugin_install"
    PLUGIN_UNINSTALL = "plugin_uninstall"
    PLUGIN_ENABLE = "plugin_enable"
    PLUGIN_DISABLE = "plugin_disable"
    PLUGIN_UPDATE = "plugin_update"
    CONFIG_CHANGE = "config_change"
    PERMISSION_GRANT = "permission_grant"
    PERMISSION_REVOKE = "permission_revoke"
    SECURITY_VIOLATION = "security_violation"
    API_ACCESS = "api_access"


class AuditSeverity(str, enum.Enum):
    """Audit severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ===== Table 1: Plugins (插件主表) =====

class Plugin(Base):
    """
    Plugin registry table.
    
    Stores metadata for all plugins (both builtin and third-party).
    One row per unique plugin_id.
    
    Relationships:
    - versions: List[PluginVersion] (one-to-many)
    - configs: List[PluginConfig] (one-to-many)
    - reviews: List[PluginReview] (one-to-many)
    - stats: PluginStats (one-to-one)
    - audit_logs: List[AuditLog] (one-to-many)
    """
    __tablename__ = "plugins"
    __table_args__ = (
        # 按分类索引（用于列表查询）
        Index("ix_plugins_category", "category"),
        # 按状态索引（用于过滤）
        Index("ix_plugins_status", "status"),
        # 按作者索引（用于作者页面）
        Index("ix_plugins_author_name", "author_name"),
        # 复合索引用于市场搜索
        Index("ix_plugins_category_status", "category", "status"),
        # 全文搜索索引（MySQL/PostgreSQL）
        Index("ix_plugins_name_search", "name", mysql_length=100),
    )

    id: Mapped[str] = mapped_column(
        String(64), 
        primary_key=True, 
        comment="Plugin ID (e.g., 'xiaohongshu-publisher')"
    )
    name: Mapped[str] = mapped_column(
        String(128), 
        nullable=False, 
        comment="Display name"
    )
    version: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="0.0.1",
        comment="Semantic version (e.g., '1.2.3')"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True, 
        comment="Plugin description (markdown supported)"
    )
    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Plugin category classification"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PluginStatus.ACTIVE,
        comment="Current lifecycle status"
    )
    
    # Author information
    author_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="",
        comment="Author display name"
    )
    author_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Author contact email"
    )
    
    # Entry point and manifest
    entry_point: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="main.py",
        comment="Python module entry point filename"
    )
    manifest_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Full plugin.json content (for reference)"
    )
    
    # Capabilities and permissions
    capabilities: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="List of capability strings"
    )
    permissions: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="Required permission declarations"
    )
    
    # Configuration schema
    config_schema: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="JSON Schema for user configuration form"
    )
    
    # Display settings
    display_icon: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="📦",
        comment="Emoji icon for UI display"
    )
    display_color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        default="#6366f1",
        comment="Hex color code for UI theming"
    )
    
    # Pricing
    pricing_model: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="free",
        comment="Monetization model"
    )
    price_monthly: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Monthly price in CNY (if paid)"
    )
    
    # Events (for event bus routing)
    events_publishes: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="Event names this plugin publishes"
    )
    events_subscribes: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="Event names this plugin subscribes to"
    )
    
    # Dependencies
    dependencies: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Dependency map {plugin_id: min_version}"
    )
    
    # Source tracking
    is_builtin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if this is a platform-bundled plugin"
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="Git repository URL or marketplace download link"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="First registration timestamp"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp"
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Marketplace publish date (if applicable)"
    )
    
    # Statistics (denormalized for performance)
    install_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total installation count (denormalized)"
    )
    average_rating: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Average review rating 1-5 (denormalized)"
    )
    review_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of reviews (denormalized)"
    )

    # Relationships
    versions: Mapped[List["PluginVersion"]] = relationship(
        back_populates="plugin",
        cascade="all, delete-orphan",
        order_by="desc(PluginVersion.version)"
    )
    configs: Mapped[List["PluginConfig"]] = relationship(
        back_populates="plugin",
        cascade="all, delete-orphan"
    )
    reviews: Mapped[List["PluginReview"]] = relationship(
        back_populates="plugin",
        cascade="all, delete-orphan"
    )
    stats: Mapped[Optional["PluginStats"]] = relationship(
        back_populates="plugin",
        uselist=False,
        cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        back_populates="plugin",
        cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status == PluginStatus.ACTIVE

    @property
    def total_reviews(self) -> int:
        return self.review_count

    def __repr__(self) -> str:
        return f"<Plugin {self.id} v{self.version} [{self.status}]>"


# ===== Table 2: PluginVersions (版本历史表) =====

class PluginVersion(Base):
    """
    Plugin version history.
    
    Tracks all version releases for rollback and changelog.
    """
    __tablename__ = "plugin_versions"
    __table_args__ = (
        Index("ix_plugin_versions_plugin_id", "plugin_id"),
        Index("ix_plugin_versions_version", "plugin_id", "version", unique=True),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    plugin_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("plugins.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to parent plugin"
    )
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Semantic version string"
    )
    
    # Changelog
    changelog: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Version changelog in markdown"
    )
    release_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed release notes"
    )
    
    # Package info
    package_checksum: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA256 checksum of the package archive"
    )
    package_size_bytes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Package size in bytes"
    )
    download_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="Download URL for this specific version"
    )
    
    # Compatibility
    min_platform_version: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Minimum required platform version"
    )
    max_platform_version: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Maximum compatible platform version (exclusive)"
    )
    
    # Status
    is_latest: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Flag indicating this is the current latest version"
    )
    
    # Timestamps
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Release/publish date"
    )
    
    # Relationship
    plugin: Mapped["Plugin"] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return f"<PluginVersion {self.plugin_id}@{self.version}>"


# ===== Table 3: PluginConfigs (用户配置表) =====

class PluginConfig(Base):
    """
    Per-user plugin configuration.
    
    Stores user-specific settings for each installed plugin.
    Supports JSON-structured configuration with validation.
    """
    __tablename__ = "plugin_configs"
    __table_args__ = (
        Index("ix_plugin_configs_user_id", "user_id"),
        Index("ix_plugin_configs_plugin_user", "user_id", "plugin_id", unique=True),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    user_id: Mapped[str] = mapped_column(
        String(26),
        nullable=False,
        comment="Owner user ID"
    )
    plugin_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("plugins.id", ondelete="CASCADE"),
        nullable=False,
        comment="Target plugin ID"
    )
    
    # Configuration data
    config_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="User configuration key-value pairs"
    )
    
    # Encrypted sensitive fields (API keys, tokens etc.)
    encrypted_fields: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Encrypted sensitive values {field_name: encrypted_value}"
    )
    
    # State
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this plugin is enabled for this user"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    plugin: Mapped["Plugin"] = relationship(back_populates="configs")

    def __repr__(self) -> str:
        return f"<PluginConfig user={self.user_id} plugin={self.plugin_id}>"


# ===== Table 4: PluginReviews (评价表) =====

class PluginReview(Base):
    """
    User reviews and ratings for plugins.
    
    Supports star ratings + text feedback.
    Used for marketplace ranking and quality signals.
    """
    __tablename__ = "plugin_reviews"
    __table_args__ = (
        Index("ix_plugin_reviews_plugin_id", "plugin_id"),
        Index("ix_plugin_reviews_user_id", "user_id"),
        Index("ix_plugin_reviews_plugin_user", "plugin_id", "user_id", unique=True),
        Index("ix_plugin_reviews_rating", "plugin_id", "rating"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    plugin_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("plugins.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(26),
        nullable=False
    )
    
    # Rating (1-5 stars)
    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Star rating 1-5"
    )
    
    # Text content
    title: Mapped[Optional[str]] = mapped_column(
        String(256),
        nullable=True,
        comment="Review title/summary"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed review text (markdown)"
    )
    
    # Moderation
    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="User has actually used this plugin"
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Highlighted by admin as helpful"
    )
    moderation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="approved",
        comment="Moderation status: approved/rejected/pending"
    )
    
    # Engagement
    helpful_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of 'helpful' votes"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationship
    plugin: Mapped["Plugin"] = relationship(back_populates="reviews")

    def __repr__(self) -> str:
        return f"<PluginReview {self.plugin_id} ⭐{self.rating}>"


# ===== Table 5: AuditLogs (审计日志表) =====

class AuditLog(Base):
    """
    Security and operations audit trail.
    
    Tracks all significant actions for compliance and debugging.
    Immutable once written (append-only).
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_plugin_id", "plugin_id"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_severity", "severity"),
        Index("ix_audit_logs_timestamp", "created_at"),
        # Composite index for common queries
        Index("ix_audit_logs_action_time", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    
    # Actor information
    user_id: Mapped[Optional[str]] = mapped_column(
        String(26),
        nullable=True,
        comment="User who performed the action (null for system actions)"
    )
    plugin_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("plugins.id", ondelete="SET NULL"),
        nullable=True,
        comment="Target plugin ID (if applicable)"
    )
    
    # Action details
    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Type of action performed"
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AuditSeverity.INFO,
        comment="Impact/severity level"
    )
    
    # Description
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable description of the action"
    )
    
    # Context data
    context_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional structured context (IP, UA, params, etc.)"
    )
    
    # Result
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the action succeeded"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error details if failed"
    )
    
    # IP address for security tracking
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address (IPv4 or IPv6)"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="Browser/client User-Agent string"
    )
    
    # Timestamp (immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="When the action occurred (never updated)"
    )
    
    # Relationship
    plugin: Mapped[Optional["Plugin"]] = relationship(back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action.value} [{self.severity.value}]>"


# ===== Table 6: PluginStats (运行统计表) =====

class PluginStats(Base):
    """
    Aggregated runtime statistics.
    
    Updated periodically (not real-time) for dashboard analytics.
    One row per plugin.
    """
    __tablename__ = "plugin_stats"
    __table_args__ = (
        Index("ix_plugin_stats_plugin_id", "plugin_id", unique=True),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    plugin_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("plugins.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    
    # Execution statistics
    total_executions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total method invocations since install"
    )
    successful_executions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Successful executions count"
    )
    failed_executions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Failed executions count"
    )
    
    # Performance metrics (averages)
    avg_execution_time_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Average execution time in milliseconds"
    )
    max_execution_time_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Worst-case execution time"
    )
    total_execution_time_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Cumulative execution time (for averaging)"
    )
    
    # Error tracking
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Most recent error message"
    )
    last_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent error"
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Current streak of failures (for circuit breaker)"
    )
    
    # Usage patterns
    last_execution_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent execution"
    )
    peak_concurrent_usages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Maximum observed concurrent usage count"
    )
    
    # Resource usage (optional, if tracked)
    memory_usage_mb: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Average memory usage in MB"
    )
    
    # Snapshot timestamp
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="When these stats were last calculated"
    )
    
    # Relationship
    plugin: Mapped["Plugin"] = relationship(back_populates="stats")

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        total = self.total_executions
        if total == 0:
            return 100.0
        return round(self.successful_executions / total * 100, 2)

    @property
    def health_status(self) -> str:
        """Determine health based on recent errors."""
        if self.consecutive_failures >= 5:
            return "critical"
        elif self.consecutive_failures >= 3:
            return "warning"
        else:
            return "healthy"

    def __repr__(self) -> str:
        return (
            f"<PluginStats {self.plugin_id} "
            f"execs={self.total_executions} "
            f"success_rate={self.success_rate}%>"
        )


# ===== Helper Functions =====

def create_initial_stats(plugin_id: str) -> PluginStats:
    """Create initial stats record for a new plugin."""
    return PluginStats(
        plugin_id=plugin_id,
        total_executions=0,
        successful_executions=0,
        failed_executions=0,
        avg_execution_time_ms=0.0,
        max_execution_time_ms=0.0,
        total_execution_time_ms=0.0,
        consecutive_failures=0,
        peak_concurrent_usages=0,
    )