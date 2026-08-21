"""
Creator Platform SDK - 插件开发工具包

让第三方开发者能快速编写插件，无需了解平台内部实现。

安装:
    pip install creator-platform-sdk

快速开始:
    from creator_platform_sdk import BaseWorkflowNodePlugin, PluginContext, NodeOutput

    class MyPlugin(BaseWorkflowNodePlugin):
        plugin_id = "my-plugin"
        plugin_name = "我的插件"

        async def execute(self, ctx: PluginContext, inputs: dict) -> NodeOutput:
            # 你的逻辑
            return NodeOutput(success=True, data={"result": "Hello!"})

版本: 1.0.0
作者: Platform Team <dev@your-platform.com>
"""

__version__ = "1.0.0"
__author__ = "Platform Team"

# 导出核心类和类型
from .base_interfaces import (
    BasePlugin,
    BaseWorkflowNodePlugin,
    BaseDatasourcePlugin,
    BasePlatformPlugin,
    BaseIntegrationPlugin,
)

from .plugin_types import (
    # 基础类型
    PluginContext,
    ExecutionResult,
    NodeOutput,
    
    # 平台插件类型
    PublishResult,
    TrendingContent,
    
    # 数据源类型
    DataSourceItem,
    DataSourceConfig,
)

from .event_bus import EventBus, Event

__all__ = [
    # 版本信息
    "__version__",
    "__author__",

    # 基类
    "BasePlugin",
    "BaseWorkflowNodePlugin",
    "BaseDatasourcePlugin",
    "BasePlatformPlugin",
    "BaseIntegrationPlugin",

    # 类型定义
    "PluginContext",
    "ExecutionResult",
    "NodeOutput",
    "PublishResult",
    "TrendingContent",
    "DataSourceItem",
    "DataSourceConfig",

    # 事件系统
    "EventBus",
    "Event",
]