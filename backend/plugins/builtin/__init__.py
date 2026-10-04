"""
Builtin Plugins - 内置插件集合
包含平台核心功能的标准化插件实现
"""

from .monitor_agent import MonitorAgentPlugin
from .ai_copywrite import AICopywriteNodePlugin


__all__ = [
    'MonitorAgentPlugin', 
    'AICopywriteNodePlugin',
]


# 内置插件清单（用于自动注册）
BUILTIN_PLUGINS = [
    {
        "module": "plugins.builtin.monitor_agent", 
        "class": "MonitorAgentPlugin",
        "category": "datasource"
    },
    {
        "module": "plugins.builtin.ai_copywrite",
        "class": "AICopywriteNodePlugin",
        "category": "workflow_node"
    }
]