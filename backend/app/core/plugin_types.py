"""
Creator Platform Plugin System - Type Definitions
定义插件系统的所有数据类型和枚举
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


class PluginCategory(str, Enum):
    """插件分类"""
    PLATFORM = "platform"  # 平台发布器
    DATASOURCE = "datasource"  # 数据源
    WORKFLOW_NODE = "workflow_node"  # 工作流节点
    AI_MODEL = "ai_model"  # AI模型适配器
    UI_THEME = "ui_theme"  # UI主题
    INTEGRATION = "integration"  # 第三方集成


class PluginStatus(str, Enum):
    """插件状态"""
    PENDING_REVIEW = "pending_review"  # 待审核
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已拒绝
    ACTIVE = "active"  # 活跃
    INACTIVE = "inactive"  # 未激活
    SUSPENDED = "suspended"  # 已暂停
    DEPRECATED = "deprecated"  # 已废弃


class PluginPermission(str, Enum):
    """插件权限声明"""
    NETWORK_HTTP = "network:http"
    NETWORK_HTTPS = "network:https"
    FILESYSTEM_READ = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    SUBPROCESS_SPAWN = "subprocess:spawn"
    ENV_READ = "env:read"
    ENV_WRITE = "env:write"


@dataclass
class PluginContext:
    """插件上下文，在插件初始化时注入"""
    plugin_id: str
    plugin_dir: str
    config: Dict[str, Any]
    logger: Any  # logging.Logger instance
    user_id: Optional[str] = None
    api: Any = None  # API客户端实例

    def get_config(self, key: str, default: Any = None) -> Any:
        """安全获取配置项"""
        return self.config.get(key, default)


@dataclass
class ExecutionResult:
    """插件方法执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: int = 0

    @classmethod
    def ok(cls, data: Any = None, execution_time_ms: int = 0) -> "ExecutionResult":
        """创建成功结果"""
        return cls(success=True, data=data, execution_time_ms=execution_time_ms)

    @classmethod
    def fail(cls, error: str, execution_time_ms: int = 0) -> "ExecutionResult":
        """创建失败结果"""
        return cls(success=False, error=error, execution_time_ms=execution_time_ms)


@dataclass
class PublishResult:
    """平台发布结果"""
    success: bool
    platform_url: str = ""
    content_id: str = ""
    error: Optional[str] = None

    @classmethod
    def ok(cls, platform_url: str = "", content_id: str = "") -> "PublishResult":
        return cls(success=True, platform_url=platform_url, content_id=content_id)

    @classmethod
    def fail(cls, error: str) -> "PublishResult":
        return cls(success=False, error=error)


@dataclass
class TrendingContent:
    """趋势内容数据结构"""
    platform: str
    content_id: str
    title: str
    summary: str
    author: str = ""
    url: str = ""
    likes: int = 0
    comments: int = 0
    shares: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "platform": self.platform,
            "content_id": self.content_id,
            "title": self.title,
            "summary": self.summary,
            "author": self.author,
            "url": self.url,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
        }


@dataclass
class PluginManifest:
    """plugin.json 解析后的清单对象"""
    id: str
    name: str
    version: str
    type: PluginCategory
    entry_point: str = "main.py"

    author_name: str = ""
    author_email: str = ""
    description: str = ""
    
    capabilities: List[str] = field(default_factory=list)
    permissions: List[PluginPermission] = field(default_factory=list)
    
    config_schema: Dict[str, Any] = field(default_factory=dict)
    dependencies: Dict[str, str] = field(default_factory=dict)
    
    events_publishes: List[str] = field(default_factory=list)
    events_subscribes: List[str] = field(default_factory=list)
    
    pricing_model: str = "free"  # free/freemium/paid
    price_monthly: float = 0.0
    
    display_icon: str = "📦"
    display_color: str = "#6366f1"
    
    raw_json: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        """从字典创建实例"""
        return cls(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            type=PluginCategory(data["type"]),
            entry_point=data.get("entry_point", "main.py"),
            author_name=data.get("author", {}).get("name", ""),
            author_email=data.get("author", {}).get("email", ""),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            permissions=[PluginPermission(p) for p in data.get("permissions", [])],
            config_schema=data.get("config_schema", {}),
            dependencies=data.get("dependencies", {}),
            events_publishes=data.get("events", {}).get("publishes", []),
            events_subscribes=data.get("events", {}).get("subscribes", []),
            pricing_model=data.get("pricing", {}).get("model", "free"),
            price_monthly=data.get("pricing", {}).get("price_monthly", 0.0),
            display_icon=data.get("display", {}).get("icon", "📦"),
            display_color=data.get("display", {}).get("color", "#6366f1"),
            raw_json=data,
        )

    def validate(self) -> tuple[bool, List[str]]:
        """验证manifest的完整性和合法性"""
        errors = []
        
        if not self.id or not isinstance(self.id, str):
            errors.append("id must be a non-empty string")
        
        import re
        if not re.match(r'^[a-z][a-z0-9_-]*$', self.id):
            errors.append("id must match pattern: ^[a-z][a-z0-9_-]*$")
            
        if not self.name or len(self.name) < 2 or len(self.name) > 64:
            errors.append("name must be 2-64 characters")
            
        if not re.match(r'^\d+\.\d+\.\d+$', self.version):
            errors.append("version must match pattern: ^\\d+\\.\\d+\\.\\d+$")
            
        if self.type not in PluginCategory:
            errors.append(f"type must be one of {[c.value for c in PluginCategory]}")
            
        if self.pricing_model not in ["free", "freemium", "paid"]:
            errors.append("pricing.model must be free/freemium/paid")
            
        if self.pricing_model == "paid" and self.price_monthly <= 0:
            errors.append("paid plugins must have price_monthly > 0")

        return len(errors) == 0, errors


@dataclass
class PluginInstanceInfo:
    """运行时插件实例信息"""
    manifest: PluginManifest
    status: PluginStatus = PluginStatus.ACTIVE
    loaded_at: datetime = field(default_factory=datetime.now)
    execution_count: int = 0
    last_execution_at: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None