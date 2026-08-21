"""
Builtin Plugins Registration - 内置插件自动注册脚本
在应用启动时调用，将核心功能包装为标准插件并加载到 PluginManager
"""

import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from app.core.plugin_manager import PluginManager, PluginLoadResult
from app.core.base_interfaces import (
    BasePlugin,
    BasePlatformPlugin,
    BaseDatasourcePlugin,
    BaseWorkflowNodePlugin,
)
from app.core.plugin_types import PluginCategory, PluginManifest, PluginInstanceInfo


logger = logging.getLogger(__name__)


# 内置插件清单（按类别分组）
BUILTIN_PLUGIN_REGISTRY: List[Dict[str, Any]] = [
    {
        "plugin_id": "xiaohongshu-publish",
        "module_path": "plugins.builtin.xiaohongshu_publish.xiaohongshu_publish",
        "class_name": "XiaohongshuPublishPlugin",
        "category": PluginCategory.PLATFORM,
        "priority": 100,
        "auto_load": True,
        "manifest": {
            "id": "xiaohongshu-publish",
            "name": "小红书发布器",
            "version": "1.0.0",
            "category": "platform",
            "description": "向小红书平台发布笔记内容（MCP Client架构）",
            "display_icon": "📕",
            "is_builtin": True,
            "is_enabled_by_default": True,
        }
    },
    {
        "plugin_id": "monitor-agent",
        "module_path": "plugins.builtin.monitor_agent.monitor_agent",
        "class_name": "MonitorAgentPlugin",
        "category": PluginCategory.DATASOURCE,
        "priority": 90,
        "auto_load": True,
        "manifest": {
            "id": "monitor-agent",
            "name": "热点监控智能体",
            "version": "1.0.0",
            "category": "datasource",
            "description": "全平台热点内容监控与智能分类系统",
            "display_icon": "🔍",
            "is_builtin": True,
            "is_enabled_by_default": True,
        }
    },
    {
        "plugin_id": "ai-copywrite-node",
        "module_path": "plugins.builtin.ai_copywrite.ai_copywrite",
        "class_name": "AICopywriteNodePlugin",
        "category": PluginCategory.WORKFLOW_NODE,
        "priority": 80,
        "auto_load": True,
        "manifest": {
            "id": "ai-copywrite-node",
            "name": "AI文案生成器",
            "version": "1.0.0",
            "category": "workflow_node",
            "description": "基于LLM的小红书专业文案生成节点",
            "display_icon": "✍️",
            "is_builtin": True,
            "is_enabled_by_default": True,
        }
    },
    {
        "plugin_id": "crab-companion",
        "module_path": "plugins.builtin.crab_companion.crab_companion",
        "class_name": "CrabCompanionPlugin",
        "category": PluginCategory.UI_THEME,
        "priority": 50,
        "auto_load": True,
        "manifest": {
            "id": "crab-companion",
            "name": "螃蟹伴侣",
            "version": "1.0.0",
            "category": "ui_theme",
            "description": "聊天界面交互螃蟹，躲在输入框后面，眼睛跟随鼠标，可点击互动",
            "display_icon": "🦀",
            "is_builtin": True,
            "is_enabled_by_default": False,
        }
    },
]


async def register_builtin_plugins(
    plugin_manager: PluginManager,
    event_bus=None,
) -> Dict[str, PluginLoadResult]:
    """
    注册所有内置插件到 PluginManager
    
    Args:
        plugin_manager: 插件管理器实例
        event_bus: 共享事件总线（可选）
        
    Returns:
        {plugin_id: PluginLoadResult} 字典
    """
    
    logger.info("=" * 70)
    logger.info("开始注册内置插件...")
    logger.info("=" * 70)
    
    results = {}
    
    for plugin_info in BUILTIN_PLUGIN_REGISTRY:
        plugin_id = plugin_info["plugin_id"]
        
        try:
            # 动态导入模块和类
            module = __import__(
                plugin_info["module_path"],
                fromlist=[plugin_info["class_name"]]
            )
            
            plugin_class = getattr(module, plugin_info["class_name"])
            
            # 创建实例
            instance = plugin_class()
            
            # 验证类型
            if not isinstance(instance, BasePlugin):
                raise TypeError(
                    f"{plugin_class.__name__} 不是有效的插件基类子类"
                )
            
            # 构建完整Manifest
            manifest_data = {
                **plugin_info.get("manifest", {}),
                "entry_point": f"{plugin_info['module_path']}:{plugin_info['class_name']}",
                "author": {
                    "name": "Platform Core Team",
                    "email": "core@creator-platform.com"
                },
                "capabilities": list(instance.__class__.__dict__.get("__annotations__", {}).keys()),
            }
            
            manifest = PluginManifest(**manifest_data)
            
            # 加载到PluginManager
            load_result = await plugin_manager._load_plugin_instance(
                plugin_id=plugin_id,
                instance=instance,
                manifest=manifest,
                priority=plugin_info.get("priority", 50),
            )
            
            results[plugin_id] = load_result
            
            if load_result.success:
                logger.info(f"✅ [{plugin_info['category'].value}] {plugin_id} - "
                           f"注册成功 ({load_result.load_time_ms}ms)")
                
                # 如果提供了event_bus，设置上下文并初始化
                if event_bus and hasattr(instance, 'setup'):
                    from app.core.plugin_types import PluginContext
                    
                    ctx = PluginContext(
                        config=plugin_info.get("default_config", {}),
                        logger=logging.getLogger(f"plugin.{plugin_id}"),
                        event_bus=event_bus,
                    )
                    await instance.setup(ctx)
                    
            else:
                logger.error(f"❌ {plugin_id} - 注册失败: {load_result.error}")
                
        except ImportError as e:
            error_msg = f"模块导入失败: {e}"
            results[plugin_id] = PluginLoadResult(
                success=False,
                plugin_id=plugin_id,
                error=error_msg
            )
            logger.error(f"❌ {plugin_id} - {error_msg}")
            
        except Exception as e:
            import traceback
            error_msg = f"注册异常: {str(e)}\n{traceback.format_exc()}"
            results[plugin_id] = PluginLoadResult(
                success=False,
                plugin_id=plugin_id,
                error=error_msg
            )
            logger.error(f"❌ {plugin_id} - {error_msg}")
    
    # 统计结果
    success_count = sum(1 for r in results.values() if r.success)
    total_count = len(results)
    
    logger.info("=" * 70)
    logger.info(f"内置插件注册完成 | 成功: {success_count}/{total_count}")
    
    for plugin_id, result in results.items():
        status = "✅" if result.success else "❌"
        logger.info(f"  {status} {plugin_id}: {'OK' if result.success else result.error[:50]}")
    
    logger.info("=" * 70)
    
    return results


async def get_builtin_plugin_instances() -> Dict[str, BasePlugin]:
    """
    获取所有内置插件实例（不经过PluginManager，直接创建）
    
    用于测试或独立使用场景
    
    Returns:
        {plugin_id: plugin_instance} 字典
    """
    
    instances = {}
    
    for plugin_info in BUILTIN_PLUGIN_REGISTRY:
        try:
            module = __import__(
                plugin_info["module_path"],
                fromlist=[plugin_info["class_name"]]
            )
            
            plugin_class = getattr(module, plugin_info["class_name"])
            instances[plugin_info["plugin_id"]] = plugin_class()
            
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"无法创建内置插件 {plugin_info['plugin_id']}: {e}"
            )
    
    return instances


def get_builtin_plugin_manifests() -> List[Dict[str, Any]]:
    """
    获取所有内置插件的Manifest信息
    
    Returns:
        Manifest字典列表
    """
    
    return [info.get("manifest", {}) for info in BUILTIN_PLUGIN_REGISTRY]


def validate_builtin_plugins_structure() -> tuple[bool, List[str]]:
    """
    验证内置插件目录结构完整性
    
    Returns:
        (is_valid, errors_list) 元组
    """
    
    errors = []
    base_path = Path(__file__).parent
    
    required_plugins = ["xiaohongshu_publish", "monitor_agent", "ai_copywrite"]
    
    for plugin_dir in required_plugins:
        plugin_path = base_path / plugin_dir
        
        if not plugin_path.exists():
            errors.append(f"缺少插件目录: {plugin_dir}/")
            continue
        
        # 检查plugin.json
        json_file = plugin_path / "plugin.json"
        if not json_file.exists():
            errors.append(f"缺少 plugin.json: {plugin_dir}/plugin.json")
        
        # 检查Python文件
        py_files = list(plugin_path.glob("*.py"))
        if not py_files:
            errors.append(f"缺少Python实现文件: {plugin_dir}/*.py")
    
    is_valid = len(errors) == 0
    
    if is_valid:
        logging.getLogger(__name__).info("✅ 内置插件目录结构验证通过")
    else:
        logging.getLogger(__name__).error(f"❌ 目录结构问题:\n" + "\n".join(errors))
    
    return is_valid, errors


# 导出函数和常量
__all__ = [
    'register_builtin_plugins',
    'get_builtin_plugin_instances',
    'get_builtin_plugin_manifests',
    'validate_builtin_plugins_structure',
    'BUILTIN_PLUGIN_REGISTRY',
]