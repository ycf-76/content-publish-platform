"""
Creator Platform Plugin System - Base Interfaces
定义所有插件必须实现的基础接口（SDK）
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
import asyncio
import logging

from .plugin_types import (
    PluginContext,
    ExecutionResult,
    PublishResult,
    TrendingContent,
)


class BasePlugin(ABC):
    """
    所有插件的基类
    
    插件开发者必须继承此类并实现必要的抽象方法。
    
    Example:
        class MyPlugin(BasePlugin):
            plugin_id = "my-plugin"
            plugin_name = "我的插件"
            
            async def setup(self, ctx: PluginContext):
                self._ctx = ctx
                # 初始化逻辑
    """

    def __init__(self):
        self._ctx: Optional[PluginContext] = None
        self._logger: Optional[logging.Logger] = None

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """
        插件唯一标识符
        必须匹配 pattern: ^[a-z][a-z0-9_-]*$
        """
        pass

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """插件显示名称"""
        pass

    async def setup(self, ctx: PluginContext) -> None:
        """
        插件初始化时调用
        在此方法中进行配置加载、连接建立等初始化工作
        
        Args:
            ctx: 插件上下文，包含配置、日志器等
        """
        self._ctx = ctx
        self._logger = ctx.logger

    async def teardown(self) -> None:
        """
        插件卸载时调用
        在此方法中释放资源、关闭连接等清理工作
        """
        pass

    async def health_check(self) -> tuple[bool, str]:
        """
        健康检查
        
        Returns:
            (is_healthy, message) 元组
        """
        return True, f"{self.plugin_name} is healthy"

    def _log(self, level: int, message: str, *args, **kwargs):
        """内部日志方法"""
        if self._logger:
            self._logger.log(level, f"[{self.plugin_id}] {message}", *args, **kwargs)


class BasePlatformPlugin(BasePlugin):
    """
    平台发布器插件基类
    
    用于向第三方平台（如小红书、抖音、B站等）发布内容的插件。
    
    Example:
        class XiaohongshuPlugin(BasePlatformPlugin):
            plugin_id = "xiaohongshu"
            plugin_name = "小红书发布器"
            
            async def authenticate(self, credentials, ctx):
                # 认证逻辑
                pass
                
            async def publish(self, content, config, ctx):
                # 发布逻辑
                pass
    """

    @abstractmethod
    async def authenticate(
        self, 
        credentials: Dict[str, Any], 
        ctx: PluginContext
    ) -> bool:
        """
        平台认证
        
        Args:
            credentials: 认证凭据（如cookie、token等）
            ctx: 插件上下文
            
        Returns:
            认证是否成功
            
        Raises:
            AuthenticationError: 认证失败时抛出
        """
        pass

    @abstractmethod
    async def publish(
        self, 
        content: Dict[str, Any], 
        config: Dict[str, Any], 
        ctx: PluginContext
    ) -> PublishResult:
        """
        发布内容到平台
        
        Args:
            content: 要发布的内容（标题、正文、图片等）
            config: 发布配置（定时发布、话题标签等）
            ctx: 插件上下文
            
        Returns:
            PublishResult 包含发布结果和平台URL
        """
        pass

    async def get_analytics(
        self, 
        content_id: str, 
        ctx: PluginContext
    ) -> Dict[str, Any]:
        """
        获取内容数据分析（可选实现）
        
        Args:
            content_id: 平台内容ID
            ctx: 插件上下文
            
        Returns:
            分析数据（阅读量、点赞数、评论数等）
        """
        raise NotImplementedError(f"{self.plugin_name} 暂不支持数据分析")

    async def delete_content(
        self, 
        content_id: str, 
        ctx: PluginContext
    ) -> bool:
        """
        删除已发布的内容（可选实现）
        
        Args:
            content_id: 平台内容ID
            ctx: 插件上下文
            
        Returns:
            是否删除成功
        """
        raise NotImplementedError(f"{self.plugin_name} 暂不支持删除内容")


class BaseDatasourcePlugin(BasePlugin):
    """
    数据源插件基类
    
    用于从外部数据源获取趋势内容、热门话题等数据的插件。
    
    Example:
        class HackerNewsPlugin(BaseDatasourcePlugin):
            plugin_id = "hackernews"
            plugin_name = "Hacker News"
            
            async def search_trending(self, keyword, limit, ctx):
                # 搜索逻辑
                pass
                
            async def get_trending(self, limit, ctx):
                # 获取热门逻辑
                pass
    """

    @abstractmethod
    async def search_trending(
        self, 
        keyword: str, 
        limit: int = 20, 
        ctx: Optional[PluginContext] = None
    ) -> List[TrendingContent]:
        """
        搜索趋势内容
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限
            ctx: 插件上下文（可选）
            
        Returns:
            TrendingContent 列表
        """
        pass

    @abstractmethod
    async def get_trending(
        self, 
        limit: int = 20, 
        ctx: Optional[PluginContext] = None
    ) -> List[TrendingContent]:
        """
        获取当前热门/推荐内容
        
        Args:
            limit: 返回结果数量上限
            ctx: 插件上下文（可选）
            
        Returns:
            TrendingContent 列表
        """
        pass

    async def validate_config(
        self, 
        config: Dict[str, Any]
    ) -> tuple[bool, List[str]]:
        """
        验证配置是否合法（可选重写）
        
        Args:
            config: 用户配置的参数
            
        Returns:
            (is_valid, errors) 元组
        """
        return True, []


class BaseWorkflowNodePlugin(BasePlugin):
    """
    工作流节点插件基类
    
    用于在工作流中执行特定任务的节点（如AI文案生成、图片生成、审核等）。
    
    Example:
        class AICopywriteNode(BaseWorkflowNodePlugin):
            node_type = "ai_copywrite"
            display_name = "AI文案生成"
            
            async def execute(self, inputs, node_config, ctx):
                # 执行逻辑
                return {"content": generated_text}
    """

    @property
    @abstractmethod
    def node_type(self) -> str:
        """节点类型标识符（唯一）"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """节点显示名称"""
        pass

    @property
    def description(self) -> str:
        """节点描述（可选）"""
        return ""

    @property
    def icon(self) -> str:
        """节点图标（emoji或图标名，默认📦）"""
        return "📦"

    @property
    def input_schema(self) -> Dict[str, Any]:
        """
        输入参数Schema（JSON Schema格式）
        
        用于前端动态渲染输入表单
        """
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        """
        输出参数Schema（JSON Schema格式）
        
        用于下游节点的输入验证
        """
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    @abstractmethod
    async def execute(
        self, 
        inputs: Dict[str, Any], 
        node_config: Dict[str, Any], 
        ctx: PluginContext
    ) -> Dict[str, Any]:
        """
        执行节点逻辑
        
        Args:
            inputs: 上游节点传递的输入数据
            node_config: 当前节点的配置参数
            ctx: 插件上下文
            
        Returns:
            节点输出数据（将传递给下游节点）
            
        Raises:
            NodeExecutionError: 执行失败时抛出
        """
        pass

    async def before_execute(
        self, 
        inputs: Dict[str, Any], 
        node_config: Dict[str, Any]
    ) -> None:
        """
        执行前钩子（可选实现）
        
        可用于输入验证、日志记录等预处理
        """
        pass

    async def after_execute(
        self, 
        result: Dict[str, Any], 
        execution_time_ms: int
    ) -> None:
        """
        执行后钩子（可选实现）
        
        可用于结果处理、性能监控等后处理
        """
        pass


class PluginEventBus:
    """
    插件事件总线
    
    实现插件间的松耦合通信机制。
    支持发布-订阅模式的事件分发。
    
    Usage:
        bus = PluginEventBus()
        
        # 订阅事件
        sub_id = await bus.subscribe("content:published", handler)
        
        # 发布事件
        await bus.publish("content:published", {"id": 123})
        
        # 取消订阅
        await bus.unsubscribe(sub_id)
    """

    def __init__(self):
        self._subscribers: Dict[str, List[tuple[str, Callable]]] = {}
        self._event_history: List[Dict[str, Any]] = []
        self._max_history = 1000  # 最大历史记录数
        self._lock = asyncio.Lock()

    async def publish(
        self, 
        event_name: str, 
        data: Any = None,
        source_plugin_id: Optional[str] = None
    ) -> int:
        """
        发布事件
        
        Args:
            event_name: 事件名称（建议使用命名空间格式如 "plugin:id:event"）
            data: 事件负载数据
            source_plugin_id: 来源插件ID（用于审计）
            
        Returns:
            成功通知的订阅者数量
        """
        subscribers = self._subscribers.get(event_name, [])
        
        if not subscribers:
            return 0

        notify_count = 0
        for sub_id, handler in subscribers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_name, data)
                else:
                    handler(event_name, data)
                notify_count += 1
            except Exception as e:
                print(f"[EventBus] Handler {sub_id} failed for event {event_name}: {e}")

        # 记录事件历史
        async with self._lock:
            self._event_history.append({
                "event": event_name,
                "data": data,
                "source": source_plugin_id,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "subscribers_notified": notify_count
            })
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]

        return notify_count

    async def subscribe(
        self, 
        event_name: str, 
        handler: Callable
    ) -> str:
        """
        订阅事件
        
        Args:
            event_name: 事件名称
            handler: 事件处理函数 (async or sync)
            
        Returns:
            订阅ID（用于取消订阅）
        """
        import uuid
        sub_id = str(uuid.uuid4())[:8]

        if event_name not in self._subscribers:
            self._subscribers[event_name] = []

        self._subscribers[event_name].append((sub_id, handler))
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        取消订阅
        
        Args:
            subscription_id: 订阅ID
            
        Returns:
            是否成功取消
        """
        for event_name, subscribers in self._subscribers.items():
            for i, (sub_id, _) in enumerate(subscribers):
                if sub_id == subscription_id:
                    subscribers.pop(i)
                    return True
        return False

    def get_event_history(
        self, 
        event_name: Optional[str] = None, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取事件历史（用于调试和审计）
        
        Args:
            event_name: 过滤特定事件（None表示全部）
            limit: 返回数量上限
            
        Returns:
            事件列表（按时间倒序）
        """
        history = self._event_history
        if event_name:
            history = [e for e in history if e["event"] == event_name]
        return history[-limit:][::-1]  # 倒序返回最新的

    def list_subscriptions(self) -> Dict[str, int]:
        """
        列出所有事件的订阅者数量
        
        Returns:
            {事件名称: 订阅者数量} 字典
        """
        return {
            event_name: len(handlers)
            for event_name, handlers in self._subscribers.items()
        }


class NodeExecutionError(Exception):
    """工作流节点执行错误"""

    def __init__(self, message: str, node_type: str = "", recoverable: bool = False):
        super().__init__(message)
        self.node_type = node_type
        self.recoverable = recoverable


class AuthenticationError(Exception):
    """认证错误"""

    def __init__(self, message: str, platform: str = ""):
        super().__init__(message)
        self.platform = platform