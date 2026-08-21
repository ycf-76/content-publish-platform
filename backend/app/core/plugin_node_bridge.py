"""
Plugin-Workflow Bridge - 插件到工作流节点的桥接层
==============================================

功能：
1. 应用启动时扫描已安装的 workflow_node 类型插件
2. 使用 PluginManager 动态加载插件代码
3. 将 BaseWorkflowNodePlugin 实例注册到 NodeRegistry
4. 提供安装/卸载后的刷新机制

使用方式：
    # 在应用 lifespan 中调用
    from app.core.plugin_node_bridge import initialize_plugin_nodes
    await initialize_plugin_nodes()
    
    # 安装/卸载后手动刷新
    from app.core.plugin_node_bridge import refresh_plugin_nodes
    await refresh_plugin_nodes()
"""

import asyncio
import logging
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# 标记是否已完成初始化
_initialized = False


async def initialize_plugin_nodes(
    plugin_dirs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    初始化：扫描并注册所有 workflow_node 类型的插件
    
    Args:
        plugin_dirs: 插件目录列表（默认使用内置目录）
        
    Returns:
        {
            "success": bool,
            "registered_count": int,
            "plugins_scanned": int,
            "errors": List[str]
        }
    """
    global _initialized
    if _initialized:
        logger.info("[plugin_node_bridge] Already initialized, skipping")
        return {"success": True, "registered_count": 0, "plugins_scanned": 0, "errors": []}
    
    result = {
        "success": True,
        "registered_count": 0,
        "plugins_scanned": 0,
        "errors": [],
    }
    
    try:
        # 1. 导入必要模块
        from app.core.node_registry import node_registry, NodeDefinition, NodeCategory
        from app.db.session import AsyncSessionLocal
        from app.services.plugin_service import PluginService
        
        async with AsyncSessionLocal() as session:
            service = PluginService(session)
            
            # 2. 获取所有 workflow_node 类型的插件
            plugins, total = await service.list_plugins()
            workflow_plugins = [p for p in plugins if p.category == "workflow_node" or p.category == "workflow_node"]
            
            result["plugins_scanned"] = len(workflow_plugins)
            logger.info(f"[plugin_node_bridge] Found {len(workflow_plugins)} workflow_node plugins")
            
            if not workflow_plugins:
                logger.info("[plugin_node_bridge] No workflow_node plugins found")
                _initialized = True
                return result
            
            # 3. 初始化 PluginManager 并加载插件
            if plugin_dirs is None:
                backend_dir = Path(__file__).parent.parent.parent
                plugin_dirs = [
                    str(backend_dir / "plugins" / "builtin"),
                    # third_party 目录可能不存在，跳过
                ]
            
            # 过滤存在的目录
            existing_dirs = [d for d in plugin_dirs if Path(d).exists()]
            
            if not existing_dirs:
                logger.warning("[plugin_node_bridge] No valid plugin directories found")
                _initialized = True
                return result
            
            from app.core.plugin_manager import PluginManager
            pm = PluginManager(plugin_dirs=existing_dirs)
            
            # 发现并加载所有插件
            try:
                load_results = await pm.discover_and_load_all()
                
                # 处理返回值（可能是列表或字符串）
                if isinstance(load_results, list):
                    loaded_count = sum(1 for r in load_results if hasattr(r, 'success') and r.success)
                else:
                    # 如果返回的不是预期格式，假设全部成功或记录日志
                    loaded_count = len(workflow_plugins) if workflow_plugins else 0
                    logger.warning(f"[plugin_node_bridge] PluginManager returned unexpected type: {type(load_results)}")
                
                logger.info(f"[plugin_node_bridge] PluginManager processed {loaded_count} plugins")
            except Exception as pm_error:
                logger.warning(f"[plugin_node_bridge] PluginManager discovery failed: {pm_error}")
                loaded_count = 0
            
            # 4. 遍历每个 workflow_node 插件，提取并注册节点
            for plugin in workflow_plugins:
                try:
                    plugin_id = plugin.id
                    
                    # 从 PluginManager 获取实例（使用 get_plugin 方法）
                    instance = pm.get_plugin(plugin_id)
                    
                    if instance is None:
                        warning_msg = f"[plugin_node_bridge] ⚠️ Plugin '{plugin_id}' not loaded by PluginManager"
                        logger.warning(warning_msg)
                        result["errors"].append(warning_msg)
                        continue
                    
                    # 检查是否为工作流节点插件
                    from app.core.base_interfaces import BaseWorkflowNodePlugin
                    if not isinstance(instance, BaseWorkflowNodePlugin):
                        warning_msg = f"[plugin_node_bridge] ⚠️ Plugin '{plugin_id}' is not a BaseWorkflowNodePlugin"
                        logger.warning(warning_msg)
                        result["errors"].append(warning_msg)
                        continue
                    
                    # 构建节点定义
                    node_def = NodeDefinition(
                        node_type=instance.node_type,
                        display_name=instance.display_name,
                        category=NodeCategory.CUSTOM.value,
                        description=instance.description,
                        icon=instance.icon,
                        version=getattr(instance, 'version', '1.0.0'),
                        
                        # Schema 定义
                        input_schema=getattr(instance, 'input_schema', {}),
                        output_schema=getattr(instance, 'output_schema', {}),
                        config_schema=getattr(instance, 'config_schema', {}),
                        
                        # 执行函数
                        execute_func=instance.execute,
                        plugin_id=plugin_id,
                        is_builtin=False,
                        
                        # 元信息
                        tags=getattr(instance, 'tags', []),
                        author=plugin.author_name or "Unknown",
                        metadata={
                            "plugin_name": plugin.name,
                            "plugin_version": plugin.version,
                            "entry_point": f"{plugin_id}",
                        },
                    )
                    
                    # 注册到 NodeRegistry
                    success = node_registry.register(node_def)
                    
                    if success:
                        result["registered_count"] += 1
                        logger.info(
                            f"[plugin_node_bridge] ✅ Registered node: {instance.node_type} "
                            f"(display: {instance.display_name}, plugin: {plugin_id})"
                        )
                    else:
                        error_msg = f"[plugin_node_bridge] ❌ Failed to register node: {instance.node_type}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                
                except Exception as e:
                    error_msg = f"[plugin_node_bridge] ❌ Error processing plugin '{plugin.id}': {e}"
                    logger.exception(error_msg)
                    result["errors"].append(error_msg)
                    continue
        
        # 5. 刷新工作流引擎的节点映射缓存
        try:
            from app.agents.graph import refresh_node_func_map
            refresh_node_func_map()
            logger.info("[plugin_node_bridge] 🔄 Refreshed node function map cache")
        except Exception as e:
            logger.warning(f"[plugin_node_bridge] ⚠️ Failed to refresh node map: {e}")
        
        _initialized = True
        logger.info(
            f"[plugin_node_bridge] 🎉 Initialization complete! "
            f"Registered {result['registered_count']}/{result['plugins_scanned']} nodes"
        )
        
    except Exception as e:
        result["success"] = False
        error_msg = f"[plugin_node_bridge] ❌ Fatal error during initialization: {e}"
        logger.exception(error_msg)
        result["errors"].append(error_msg)
    
    return result


async def refresh_plugin_nodes() -> Dict[str, Any]:
    """
    刷新插件节点（安装/卸载/启用/禁用后调用）
    
    Returns:
        同 initialize_plugin_nodes 的返回格式
    """
    global _initialized
    _initialized = False  # 重置初始化标记
    
    logger.info("[plugin_node_bridge] 🔄 Refreshing plugin nodes...")
    return await initialize_plugin_nodes()


def get_registered_plugin_nodes() -> List[Dict[str, Any]]:
    """
    获取当前已注册的所有插件节点信息（用于API展示）
    
    Returns:
        [
            {
                "node_type": "ai_copywrite",
                "display_name": "AI文案生成",
                "plugin_id": "ai-copywrite-node",
                ...
            },
            ...
        ]
    """
    from app.core.node_registry import node_registry
    
    plugin_nodes = []
    for node_type, node_def in node_registry._registry.items():
        if node_def.plugin_id:  # 只返回插件节点
            plugin_nodes.append({
                "node_type": node_def.node_type,
                "display_name": node_def.display_name,
                "category": node_def.category,
                "description": node_def.description,
                "icon": node_def.icon,
                "version": node_def.version,
                "plugin_id": node_def.plugin_id,
                "is_builtin": node_def.is_builtin,
                "tags": node_def.tags,
                "author": node_def.author,
                "input_schema": node_def.input_schema,
                "output_schema": node_def.output_schema,
                "config_schema": node_def.config_schema,
            })
    
    return plugin_nodes


# ===== CLI 测试入口 =====

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("🧪 Plugin-Workflow Bridge Test")
        print("=" * 60)
        
        result = await initialize_plugin_nodes()
        
        print("\n📊 Test Results:")
        print(f"  Success: {result['success']}")
        print(f"  Plugins Scanned: {result['plugins_scanned']}")
        print(f"  Nodes Registered: {result['registered_count']}")
        
        if result['errors']:
            print(f"\n⚠️ Errors ({len(result['errors'])}):")
            for err in result['errors']:
                print(f"   - {err}")
        
        if result['registered_count'] > 0:
            print("\n✅ Registered Nodes:")
            nodes = get_registered_plugin_nodes()
            for node in nodes:
                print(f"   - [{node['icon']}] {node['display_name']} ({node['node_type']})")
                print(f"     Plugin: {node['plugin_id']}")
        
        print("\n" + "=" * 60)
    
    asyncio.run(test())
