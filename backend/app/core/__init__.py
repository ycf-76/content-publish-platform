# Creator Platform Plugin System Core
# 一切皆插件 - 核心模块

from .plugin_types import (
    PluginCategory,
    PluginStatus,
    PluginPermission,
    ExecutionResult,
    PublishResult,
    TrendingContent,
    PluginContext,
    PluginManifest,
    PluginInstanceInfo,
)

from .base_interfaces import (
    BasePlugin,
    BasePlatformPlugin,
    BaseDatasourcePlugin,
    BaseWorkflowNodePlugin,
    PluginEventBus,
)

from .plugin_manager import (
    PluginManager,
    PluginLoadResult,
    ExecuteRequest,
)

from .event_bus import (
    EnhancedEventBus,
    DataStore,
    Event,
    EventPriority,
    Subscription,
    SharedDataItem,
)

__all__ = [
    # Types
    "PluginCategory",
    "PluginStatus",
    "PluginPermission",
    "ExecutionResult",
    "PublishResult",
    "TrendingContent",
    "PluginContext",
    "PluginManifest",
    "PluginInstanceInfo",
    # Interfaces
    "BasePlugin",
    "BasePlatformPlugin",
    "BaseDatasourcePlugin",
    "BaseWorkflowNodePlugin",
    "PluginEventBus",
    # Manager
    "PluginManager",
    "PluginLoadResult",
    "ExecuteRequest",
    # EventBus (Enhanced)
    "EnhancedEventBus",
    "DataStore",
    "Event",
    "EventPriority",
    "Subscription",
    "SharedDataItem",
]