"""
Creator Platform SDK - 核心类型定义

定义插件开发中使用的所有数据类型、枚举和接口。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Union


# ===== 枚举类型 =====

class PluginCategory(Enum):
    """插件分类"""
    WORKFLOW_NODE = "workflow_node"      # 工作流节点
    DATASOURCE = "datasource"            # 数据源
    PLATFORM = "platform"                # 发布平台
    INTEGRATION = "integration"          # 集成工具
    UI_COMPONENT = "ui_component"        # UI组件

class Priority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

class NotificationLevel(Enum):
    """通知级别"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


# ===== 数据模型 =====

@dataclass
class PluginContext:
    """
    插件执行上下文
    
    每次插件执行时都会创建一个上下文对象，包含：
    - 用户信息（用于权限控制）
    - 配置参数（来自plugin.json的config_schema）
    - 日志器（用于输出日志）
    - 事件总线（用于发送事件）
    
    Attributes:
        user_id: 当前用户ID
        config: 插件配置字典
        logger: 日志记录器
        event_bus: 事件总线实例
        storage: 临时存储（跨节点传递数据）
        metadata: 元数据（如工作流ID等）
    """
    def __init__(
        self,
        user_id: str = "anonymous",
        config: Optional[Dict[str, Any]] = None,
        logger=None,
        event_bus=None,
        storage: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.user_id = user_id
        self.config = config or {}
        self.logger = logger
        self.event_bus = event_bus
        self.storage = storage or {}
        self.metadata = metadata or {}


@dataclass
class NodeOutput:
    """
    节点执行结果
    
    所有execute()方法必须返回此类型的对象。
    
    Example:
        return NodeOutput(
            success=True,
            data={"result": 42},
            message="计算完成",
            execution_time_ms=100
        )
    
    Attributes:
        success: 是否成功
        data: 输出数据（会被传递给下一个节点）
        message: 执行消息（显示在日志中）
        execution_time_ms: 执行耗时（毫秒）
        error: 错误信息（失败时填写）
    """
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    execution_time_ms: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "execution_time_ms": self.execution_time_ms,
            "error": self.error
        }


@dataclass
class ExecutionResult(NodeOutput):
    """
    执行结果（扩展版）
    
    用于需要更多元数据的场景。
    """
    node_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    retry_count: int = 0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class PublishResult:
    """
    平台发布结果
    
    BasePlatformPlugin.execute()应返回包含此对象的NodeOutput。
    
    Attributes:
        success: 是否发布成功
        post_id: 发布后的内容ID
        post_url: 内容链接
        platform: 平台名称
        published_at: 发布时间
        stats: 统计信息（如浏览量、点赞数等）
        error_message: 失败原因
    """
    success: bool
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    platform: Optional[str] = None
    published_at: Optional[datetime] = None
    stats: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = {
            "success": self.success,
            "post_id": self.post_id,
            "post_url": self.post_url,
            "platform": self.platform,
            "stats": self.stats or {},
            "error_message": self.error_message
        }
        
        if self.published_at:
            result["published_at"] = self.published_at.isoformat()
            
        return result


@dataclass
class TrendingContent:
    """
    热门内容项
    
    BaseDatasourcePlugin.fetch_trending()返回的数据结构。
    
    Attributes:
        content_id: 内容唯一标识
        title: 内容标题
        description: 内容描述/摘要
        url: 原文链接
        image_url: 封面图URL
        author: 作者/来源
        published_at: 发布时间
        metrics: 数据指标（点赞、评论、分享等）
        tags: 标签列表
        raw_data: 原始数据（保留完整信息）
    """
    content_id: str
    title: str
    description: str = ""
    url: Optional[str] = None
    image_url: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    raw_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> dict:
        result = {
            "content_id": self.content_id,
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "image_url": self.image_url,
            "author": self.author,
            "metrics": self.metrics or {},
            "tags": self.tags or [],
            "raw_data": self.raw_data
        }
        
        if self.published_at:
            result["published_at"] = self.published_at.isoformat()
            
        return result


@dataclass
class DataSourceItem:
    """
    数据源条目
    
    BaseDatasourcePlugin.fetch_data()返回的基础数据单元。
    """
    item_id: str
    item_type: str  # article, video, image, etc.
    title: str
    content: str
    source: Optional[str] = None
    url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    fetched_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        result = {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "url": self.url,
            "metadata": self.metadata or {}
        }
        
        if self.fetched_at:
            result["fetched_at"] = self.fetched_at.isoformat()
            
        return result


@dataclass
class DataSourceConfig:
    """
    数据源配置
    
    定义如何连接和获取外部数据源。
    """
    source_type: str  # rss, api, database, file, etc.
    endpoint: Optional[str] = None
    auth_config: Optional[Dict[str, Any]] = None
    query_params: Optional[Dict[str, Any]] = None
    refresh_interval: int = 300  # 秒
    max_items: int = 50
    filters: Optional[List[Dict[str, Any]]] = None


# ===== 工具函数 =====

def create_success_output(data: Dict[str, Any], message: str = "") -> NodeOutput:
    """快速创建成功结果"""
    return NodeOutput(success=True, data=data, message=message)

def create_error_output(error: str, data: Optional[Dict[str, Any]] = None) -> NodeOutput:
    """快速创建错误结果"""
    return NodeOutput(success=False, data=data or {}, error=error, message=f"Error: {error}")

def create_plugin_context(
    user_id: str = "test_user",
    **kwargs
) -> PluginContext:
    """快速创建测试用的上下文"""
    return PluginContext(user_id=user_id, **kwargs)