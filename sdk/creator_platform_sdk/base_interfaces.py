"""
Creator Platform SDK - 插件基类接口

定义所有类型插件的基类，开发者继承这些基类来实现自己的插件。
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .plugin_types import (
    PluginContext,
    NodeOutput,
    PublishResult,
    TrendingContent,
    DataSourceItem,
    DataSourceConfig,
)


class BasePlugin(ABC):
    """
    所有插件的基类
    
    提供通用的生命周期方法和工具函数。
    
    Example:
        class MyPlugin(BasePlugin):
            plugin_id = "my-plugin"
            plugin_name = "我的插件"
            
            async def setup(self, ctx: PluginContext):
                self._ctx = ctx
                
            async def execute(self, ctx: PluginContext, inputs: dict) -> NodeOutput:
                return NodeOutput(success=True, data={"hello": "world"})
    
    Attributes:
        plugin_id: 插件唯一标识符（必须由子类定义）
        plugin_name: 插件显示名称（必须由子类定义）
        version: 插件版本号（可选）
        description: 插件描述（可选）
    """

    # 子类必须定义的属性
    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """插件唯一标识符 (pattern: ^[a-z][a-z0-9_-]*$)"""
        pass

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """插件显示名称"""
        pass

    # 可选属性（提供默认值）
    version: str = "0.1.0"
    description: str = ""
    
    def __init__(self):
        self._ctx: Optional[PluginContext] = None
        self._logger: Optional[logging.Logger] = None
        self._initialized: bool = False

    async def setup(self, ctx: PluginContext) -> None:
        """
        插件初始化
        
        在execute()之前调用一次，用于：
        - 加载配置
        - 建立连接
        - 初始化资源
        
        Args:
            ctx: 插件上下文
        """
        self._ctx = ctx
        self._logger = ctx.logger if hasattr(ctx, 'logger') else logging.getLogger(self.plugin_id)
        self._initialized = True
        self._log(logging.INFO, "Plugin initialized")

    async def teardown(self) -> None:
        """
        插件清理
        
        在插件卸载时调用，用于释放资源。
        """
        self._log(logging.INFO, "Plugin teardown")
        self._initialized = False

    @abstractmethod
    async def execute(
        self,
        ctx: PluginContext,
        inputs: Dict[str, Any]
    ) -> NodeOutput:
        """
        执行插件逻辑（核心方法）
        
        Args:
            ctx: 执行上下文
            inputs: 输入参数
            
        Returns:
            NodeOutput: 执行结果
        """
        pass

    async def validate_inputs(
        self,
        inputs: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        验证输入参数
        
        在execute()之前调用，用于提前校验。
        
        Args:
            inputs: 输入参数
            
        Returns:
            (is_valid, error_message) 元组
        """
        return True, ""

    async def health_check(self) -> Tuple[bool, str]:
        """
        健康检查
        
        Returns:
            (is_healthy, message) 元组
        """
        return (
            self._initialized,
            f"{self.plugin_name} is {'ready' if self._initialized else 'not initialized'}"
        )

    def _log(self, level: int, message: str, *args, **kwargs):
        """内部日志方法"""
        if self._logger:
            self._logger.log(level, f"[{self.plugin_id}] {message}", *args, **kwargs)

    def get_manifest(self) -> Dict[str, Any]:
        """
        获取插件清单信息
        
        Returns:
            包含插件元数据的字典
        """
        return {
            "id": self.plugin_id,
            "name": self.plugin_name,
            "version": self.version,
            "description": self.description,
            "type": self.__class__.__name__,
        }


class BaseWorkflowNodePlugin(BasePlugin):
    """
    工作流节点插件基类
    
    用于在工作流中执行特定任务的节点。
    
    适用场景:
    - AI文案生成
    - 文本翻译
    - 情感分析
    - 数据转换
    - 自定义逻辑
    
    Example:
        class TextTranslator(BaseWorkflowNodePlugin):
            plugin_id = "text-translator"
            plugin_name = "AI文本翻译器"
            
            async def execute(self, ctx: PluginContext, inputs: dict) -> NodeOutput:
                text = inputs.get("text", "")
                target_lang = inputs.get("target_lang", "en")
                
                # 翻译逻辑...
                translated = await self._translate(text, target_lang)
                
                return NodeOutput(
                    success=True,
                    data={
                        "original": text,
                        "translated": translated,
                        "target_language": target_lang
                    }
                )
    """

    category: str = "workflow_node"

    async def on_node_start(self, node_id: str):
        """节点开始执行时回调"""
        pass

    async def on_node_complete(self, node_id: str, result: NodeOutput):
        """节点完成时回调"""
        pass


class BaseDatasourcePlugin(BasePlugin):
    """
    数据源插件基类
    
    用于从外部数据源获取数据。
    
    适用场景:
    - RSS订阅监控
    - 社交媒体抓取
    - API数据获取
    - 数据库查询
    - 文件系统监听
    
    Example:
        class RSSMonitor(BaseDatasourcePlugin):
            plugin_id = "rss-monitor"
            plugin_name = "RSS订阅监控"
            
            async def fetch_data(
                self,
                ctx: PluginContext,
                config: DataSourceConfig
            ) -> List[DataSourceItem]:
                # 解析RSS并返回数据项
                items = []
                
                for entry in rss_entries:
                    item = DataSourceItem(
                        item_id=entry.id,
                        item_type="article",
                        title=entry.title,
                        content=entry.summary,
                        url=entry.link,
                        source=config.endpoint
                    )
                    items.append(item)
                    
                return items
    """

    category: str = "datasource"

    async def fetch_data(
        self,
        ctx: PluginContext,
        config: DataSourceConfig
    ) -> List[DataSourceItem]:
        """
        获取数据（核心方法）
        
        Args:
            ctx: 上下文
            config: 数据源配置
            
        Returns:
            数据项列表
        """
        raise NotImplementedError("Subclasses must implement fetch_data()")

    async def fetch_trending(
        self,
        ctx: PluginContext,
        category: Optional[str] = None,
        limit: int = 20
    ) -> List[TrendingContent]:
        """
        获取热门内容
        
        Args:
            ctx: 上下文
            category: 分类过滤
            limit: 返回数量限制
            
        Returns:
            热门内容列表
        """
        raise NotImplementedError("Subclasses must implement fetch_trending()")

    async def test_connection(
        self,
        ctx: PluginContext,
        config: DataSourceConfig
    ) -> Tuple[bool, str]:
        """
        测试数据源连接
        
        Returns:
            (is_connected, message) 元组
        """
        try:
            items = await self.fetch_data(ctx, config)
            return True, f"Connection successful. Found {len(items)} items."
        except Exception as e:
            return False, f"Connection failed: {str(e)}"


class BasePlatformPlugin(BasePlugin):
    """
    平台发布器插件基类
    
    用于向第三方平台发布内容。
    
    适用场景:
    - 小红书发布
    - 微博/抖音/B站发布
    - WordPress博客
    - 邮件发送
    
    Example:
        class XiaohongshuPublisher(BasePlatformPlugin):
            plugin_id = "xiaohongshu-publisher"
            plugin_name = "小红书发布器"
            
            async def publish(
                self,
                ctx: PluginContext,
                content: dict,
                credentials: dict
            ) -> PublishResult:
                # 发布到小红书的逻辑...
                
                return PublishResult(
                    success=True,
                    post_id=post_id,
                    post_url=f"https://www.xiaohongshu.com/explore/{post_id}",
                    platform="xiaohongshu",
                    published_at=datetime.utcnow()
                )
    """

    category: str = "platform"

    async def publish(
        self,
        ctx: PluginContext,
        content: Dict[str, Any],
        credentials: Dict[str, Any]
    ) -> PublishResult:
        """
        发布内容（核心方法）
        
        Args:
            ctx: 上下文
            content: 内容数据（标题、正文、图片等）
            credentials: 认证凭据
            
        Returns:
            PublishResult: 发布结果
        """
        raise NotImplementedError("Subclasses must implement publish()")

    async def authenticate(
        self,
        ctx: PluginContext,
        credentials: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        认证用户身份
        
        Args:
            ctx: 上下文
            credentials: 认证信息（如token、密码等）
            
        Returns:
            (is_authenticated, user_info_or_error_message) 元组
        """
        raise NotImplementedError("Subclasses must implement authenticate()")

    async def get_publish_history(
        self,
        ctx: PluginContext,
        limit: int = 20,
        offset: int = 0
    ) -> List[PublishResult]:
        """
        获取发布历史
        
        Returns:
            PublishResult列表
        """
        return []

    async def delete_post(
        self,
        ctx: PluginContext,
        post_id: str,
        credentials: Dict[str, Any]
    ) -> bool:
        """
        删除已发布的内容
        
        Returns:
            是否成功删除
        """
        raise NotImplementedError("Delete not supported")


class BaseIntegrationPlugin(BasePlugin):
    """
    集成工具插件基类
    
    用于集成外部服务和工具。
    
    适用场景:
    - 通知推送（邮件、微信、钉钉、Slack）
    - 云存储（OSS、S3）
    - CI/CD集成
    - 第三方API对接
    
    Example:
        class NotificationBot(BaseIntegrationPlugin):
            plugin_id = "notification-bot"
            plugin_name = "多渠道通知机器人"
            
            async def send_notification(
                self,
                ctx: PluginContext,
                notification: dict
            ) -> NodeOutput:
                # 发送通知的逻辑...
                
                return NodeOutput(
                    success=True,
                    data={
                        "notification_id": notif_id,
                        "sent_channels": ["email", "slack"]
                    }
                )
    """

    category: str = "integration"

    async def send_notification(
        self,
        ctx: PluginContext,
        notification: Dict[str, Any]
    ) -> NodeOutput:
        """
        发送通知（示例方法）
        
        Args:
            ctx: 上下文
            notification: 通知内容
            
        Returns:
            发送结果
        """
        raise NotImplementedError("Subclasses must implement send_notification()")

    async def integrate(
        self,
        ctx: PluginContext,
        action: str,
        params: Dict[str, Any]
    ) -> NodeOutput:
        """
        通用集成方法
        
        Args:
            ctx: 上下文
            action: 操作类型
            params: 参数
            
        Returns:
            集成结果
        """
        raise NotImplementedError("Subclasses must implement integrate()")