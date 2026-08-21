"""
Creator Platform Plugin System - PluginManager
插件管理器核心实现，负责插件的生命周期管理

功能：
1. 插件发现 (discover) - 扫描目录查找plugin.json
2. 插件加载 (load) - 动态导入Python模块
3. 插件执行 (execute) - 调用插件方法，带超时和错误隔离
4. 插件卸载 (unload) - 清理资源
5. 插件重载 (reload) - 热更新
"""

import asyncio
import json
import importlib.util
import sys
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
import traceback

from .plugin_types import (
    PluginCategory,
    PluginStatus,
    PluginManifest,
    PluginInstanceInfo,
    ExecutionResult,
    PluginContext,
)
from .base_interfaces import (
    BasePlugin,
    BasePlatformPlugin,
    BaseDatasourcePlugin,
    BaseWorkflowNodePlugin,
    PluginEventBus,
)


@dataclass
class PluginLoadResult:
    """插件加载结果"""
    success: bool
    plugin_id: str = ""
    error: Optional[str] = None
    manifest: Optional[PluginManifest] = None
    instance: Optional[BasePlugin] = None
    load_time_ms: int = 0


@dataclass
class ExecuteRequest:
    """执行请求"""
    plugin_id: str
    method: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    timeout: float = 30.0  # 默认30秒超时
    request_id: str = ""


class PluginManager:
    """
    插件管理器
    
    Usage:
        pm = PluginManager(
            plugin_dirs=["./plugins/builtin", "./plugins/third_party"],
            event_bus=PluginEventBus()
        )
        
        # 发现并加载所有插件
        results = await pm.discover_and_load_all()
        
        # 执行插件方法
        result = await pm.execute_method("my-plugin", "search_trending", "AI")
        
        # 列出已加载插件
        plugins = pm.list_plugins()
        
        # 卸载插件
        await pm.unload_plugin("old-plugin")
    """

    def __init__(
        self,
        plugin_dirs: List[str],
        event_bus: Optional[PluginEventBus] = None,
        logger: Optional[logging.Logger] = None,
        default_timeout: float = 30.0,
        max_plugins: int = 100,
    ):
        """
        初始化插件管理器
        
        Args:
            plugin_dirs: 插件目录列表（按优先级排序）
            event_bus: 共享事件总线实例（可选）
            logger: 日志记录器
            default_timeout: 默认方法执行超时时间（秒）
            max_plugins: 最大允许加载的插件数量
        """
        self.plugin_dirs = [Path(d).resolve() for d in plugin_dirs]
        self._event_bus = event_bus or PluginEventBus()
        self._logger = logger or logging.getLogger("plugin_manager")
        
        self._registry: Dict[str, PluginInstanceInfo] = {}
        self._instances: Dict[str, BasePlugin] = {}
        self._loaded_modules: Dict[str, Any] = {}
        
        self._default_timeout = default_timeout
        self._max_plugins = max_plugins
        
        # 统计信息
        self._stats = {
            "total_loads": 0,
            "total_executions": 0,
            "total_errors": 0,
            "start_time": datetime.now(),
        }

    async def discover_and_load_all(self) -> Dict[str, PluginLoadResult]:
        """
        发现并加载所有插件
        
        扫描所有plugin_dirs目录下的子文件夹，
        查找plugin.json文件并尝试加载。
        
        Returns:
            {plugin_id: PluginLoadResult} 加载结果字典
        """
        results = {}
        self._logger.info(f"🔍 开始扫描插件目录: {[str(d) for d in self.plugin_dirs]}")
        
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                self._logger.warning(f"⚠️ 插件目录不存在: {plugin_dir}")
                continue
            
            # 查找所有包含plugin.json的子目录
            for manifest_path in plugin_dir.glob("*/plugin.json"):
                plugin_folder = manifest_path.parent
                
                try:
                    result = await self._load_single_plugin(plugin_folder)
                    if result.success and result.plugin_id:
                        results[result.plugin_id] = result
                        
                        # 发布事件
                        await self._event_bus.publish(
                            "plugin:loaded",
                            {"plugin_id": result.plugin_id},
                            source_plugin_id="system"
                        )
                    else:
                        folder_name = plugin_folder.name
                        results[folder_name] = result
                        
                except Exception as e:
                    error_msg = f"加载异常: {str(e)}"
                    self._logger.error(f"❌ {plugin_folder.name}: {error_msg}")
                    results[plugin_folder.name] = PluginLoadResult(
                        success=False,
                        plugin_id=plugin_folder.name,
                        error=error_msg
                    )

        # 输出统计
        success_count = sum(1 for r in results.values() if r.success)
        fail_count = len(results) - success_count
        self._logger.info(
            f"✅ 插件加载完成: 成功={success_count}, 失败={fail_count}, 总计={len(results)}"
        )
        
        return results

    async def _load_single_plugin(self, plugin_folder: Path) -> PluginLoadResult:
        """加载单个插件"""
        start_time = time.time()
        
        manifest_path = plugin_folder / "plugin.json"
        if not manifest_path.exists():
            return PluginLoadResult(
                success=False,
                error="缺少plugin.json文件",
                plugin_id=plugin_folder.name
            )
        
        # 读取并解析manifest
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
            
            manifest = PluginManifest.from_dict(manifest_data)
            
            # 验证manifest
            is_valid, errors = manifest.validate()
            if not is_valid:
                return PluginLoadResult(
                    success=False,
                    plugin_id=manifest.id,
                    error=f"Manifest验证失败: {'; '.join(errors)}",
                    manifest=manifest
                )
                
        except json.JSONDecodeError as e:
            return PluginLoadResult(
                success=False,
                plugin_id=plugin_folder.name,
                error=f"JSON解析错误: {e}"
            )
        except Exception as e:
            return PluginLoadResult(
                success=False,
                plugin_id=plugin_folder.name,
                error=f"Manifest读取错误: {e}"
            )

        # 检查是否已达上限
        if len(self._registry) >= self._max_plugins:
            return PluginLoadResult(
                success=False,
                plugin_id=manifest.id,
                error=f"插件数量已达上限 ({self._max_plugins})",
                manifest=manifest
            )

        # 动态加载Python模块
        try:
            entry_point = manifest.entry_point
            module_file = plugin_folder / entry_point
            
            if not module_file.exists():
                return PluginLoadResult(
                    success=False,
                    plugin_id=manifest.id,
                    error=f"入口文件不存在: {entry_point}",
                    manifest=manifest
                )

            # 使用importlib动态导入
            module_name = f"plugin_{manifest.id.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(module_name, str(module_file))
            
            if spec is None or spec.loader is None:
                return PluginLoadResult(
                    success=False,
                    plugin_id=manifest.id,
                    error="无法创建模块规格",
                    manifest=manifest
                )
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # 查找Plugin类
            plugin_class = getattr(module, 'Plugin', None)
            if plugin_class is None:
                return PluginLoadResult(
                    success=False,
                    plugin_id=manifest.id,
                    error="模块中未找到Plugin类",
                    manifest=manifest
                )

            # 实例化插件
            instance: BasePlugin = plugin_class()
            
            # 创建上下文并初始化
            ctx = PluginContext(
                plugin_id=manifest.id,
                plugin_dir=str(plugin_folder),
                config={},  # 配置稍后从数据库加载
                logger=logging.getLogger(f"plugin.{manifest.id}"),
                api=None,  # API客户端稍后注入
            )
            
            await instance.setup(ctx)
            
            # 注册到管理器
            load_time_ms = int((time.time() - start_time) * 1000)
            
            self._instances[manifest.id] = instance
            self._loaded_modules[manifest.id] = module
            self._registry[manifest.id] = PluginInstanceInfo(
                manifest=manifest,
                status=PluginStatus.ACTIVE,
                loaded_at=datetime.now(),
            )
            
            self._stats["total_loads"] += 1
            
            self._logger.info(
                f"✅ 插件加载成功: {manifest.id} v{manifest.version} ({load_time_ms}ms)"
            )
            
            return PluginLoadResult(
                success=True,
                plugin_id=manifest.id,
                manifest=manifest,
                instance=instance,
                load_time_ms=load_time_ms
            )
            
        except Exception as e:
            tb_str = traceback.format_exc()
            self._logger.error(f"❌ 插件加载失败 {manifest.id}:\n{tb_str}")
            
            return PluginLoadResult(
                success=False,
                plugin_id=manifest.id,
                error=f"加载异常: {str(e)}",
                manifest=manifest
            )

    async def execute_method(
        self,
        plugin_id: str,
        method: str,
        *args,
        timeout: Optional[float] = None,
        **kwargs
    ) -> ExecutionResult:
        """
        执行插件方法
        
        带有超时控制和错误隔离的安全执行机制。
        
        Args:
            plugin_id: 插件ID
            method: 方法名
            *args: 位置参数
            timeout: 超时时间（秒），None则使用默认值
            **kwargs: 关键字参数
            
        Returns:
            ExecutionResult 执行结果
        """
        start_time = time.time()
        execute_timeout = timeout or self._default_timeout
        
        self._stats["total_executions"] += 1
        
        # 检查插件是否存在
        instance = self._instances.get(plugin_id)
        if not instance:
            self._stats["total_errors"] += 1
            return ExecutionResult.fail(
                error=f"插件未找到: {plugin_id}",
                execution_time_ms=0
            )
        
        # 检查方法是否存在
        if not hasattr(instance, method):
            self._stats["total_errors"] += 1
            return ExecutionResult.fail(
                error=f"方法不存在: {method}",
                execution_time_ms=0
            )
        
        func = getattr(instance, method)
        
        # 发布执行开始事件
        request_id = f"{plugin_id}_{method}_{int(time.time()*1000)}"
        await self._event_bus.publish(
            "plugin:execution:start",
            {
                "pluginId": plugin_id,
                "method": method,
                "requestId": request_id,
            },
            source_plugin_id="system"
        )
        
        try:
            # 带超时的异步执行
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=execute_timeout
                )
            else:
                # 同步函数在线程池中执行
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: func(*args, **kwargs)),
                    timeout=execute_timeout
                )
            
            # 更新统计
            exec_time_ms = int((time.time() - start_time) * 1000)
            info = self._registry.get(plugin_id)
            if info:
                info.execution_count += 1
                info.last_execution_at = datetime.now()
            
            # 发布执行完成事件
            await self._event_bus.publish(
                "plugin:execution:complete",
                {
                    "pluginId": plugin_id,
                    "success": True,
                    "durationMs": exec_time_ms,
                    "requestId": request_id,
                },
                source_plugin_id="system"
            )
            
            return ExecutionResult.ok(data=result, execution_time_ms=exec_time_ms)
            
        except asyncio.TimeoutError:
            exec_time_ms = int((time.time() - start_time) * 1000)
            error_msg = f"执行超时 ({execute_timeout}s)"
            
            self._stats["total_errors"] += 1
            info = self._registry.get(plugin_id)
            if info:
                info.error_count += 1
                info.last_error = error_msg
            
            await self._event_bus.publish(
                "plugin:execution:error",
                {
                    "pluginId": plugin_id,
                    "error": error_msg,
                    "requestId": request_id,
                },
                source_plugin_id="system"
            )
            
            return ExecutionResult.fail(error=error_msg, execution_time_ms=exec_time_ms)
            
        except Exception as e:
            exec_time_ms = int((time.time() - start_time) * 1000)
            error_msg = f"执行异常: {str(e)}"
            
            self._stats["total_errors"] += 1
            info = self._registry.get(plugin_id)
            if info:
                info.error_count += 1
                info.last_error = error_msg
            
            self._logger.error(f"❌ [{plugin_id}.{method}] {error_msg}")
            
            await self._event_bus.publish(
                "plugin:execution:error",
                {
                    "pluginId": plugin_id,
                    "error": error_msg,
                    "traceback": traceback.format_exc(),
                    "requestId": request_id,
                },
                source_plugin_id="system"
            )
            
            return ExecutionResult.fail(error=error_msg, execution_time_ms=exec_time_ms)

    async def unload_plugin(self, plugin_id: str) -> bool:
        """
        卸载插件
        
        清理资源、移除注册表中的条目。
        
        Args:
            plugin_id: 要卸载的插件ID
            
        Returns:
            是否成功卸载
        """
        instance = self._instances.get(plugin_id)
        if not instance:
            self._logger.warning(f"⚠️ 插件未找到，无法卸载: {plugin_id}")
            return False
        
        try:
            # 调用teardown清理资源
            await instance.teardown()
            
            # 从注册表中移除
            del self._instances[plugin_id]
            
            if plugin_id in self._registry:
                del self._registry[plugin_id]
            
            if plugin_id in self._loaded_modules:
                del self._loaded_modules[plugin_id]
            
            # 发布事件
            await self._event_bus.publish(
                "plugin:unloaded",
                {"pluginId": plugin_id},
                source_plugin_id="system"
            )
            
            self._logger.info(f"✅ 插件已卸载: {plugin_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"❌ 卸载插件失败 {plugin_id}: {e}")
            return False

    async def reload_plugin(self, plugin_id: str) -> PluginLoadResult:
        """
        重载插件（热更新）
        
        先卸载旧版本，再重新加载。
        
        Args:
            plugin_id: 要重载的插件ID
            
        Returns:
            新版本的加载结果
        """
        self._logger.info(f"Reloading plugin: {plugin_id}")
        
        # 先尝试卸载旧版本（如果存在）
        if plugin_id in self._registry:
            await self.unload_plugin(plugin_id)
        
        # 根据manifest找到插件目录并重新加载
        # 遍历所有子目录查找匹配的plugin.json中的id字段
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue
                
            for sub_dir in plugin_dir.iterdir():
                if not sub_dir.is_dir():
                    continue
                    
                manifest_path = sub_dir / "plugin.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            manifest_data = json.load(f)
                        
                        if manifest_data.get("id") == plugin_id:
                            result = await self._load_single_plugin(sub_dir)
                            
                            if result.success:
                                await self._event_bus.publish(
                                    "plugin:reloaded",
                                    {"pluginId": plugin_id, "newVersion": result.manifest.version},
                                    source_plugin_id="system"
                                )
                            
                            return result
                    except Exception as e:
                        continue
        
        return PluginLoadResult(
            success=False,
            plugin_id=plugin_id,
            error="找不到插件目录"
        )

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        """获取插件实例"""
        return self._instances.get(plugin_id)

    def get_plugin_info(self, plugin_id: str) -> Optional[PluginInstanceInfo]:
        """获取插件详细信息"""
        return self._registry.get(plugin_id)

    def list_plugins(
        self,
        category: Optional[PluginCategory] = None,
        status: Optional[PluginStatus] = None,
    ) -> List[Dict[str, Any]]:
        """
        列出所有已加载插件
        
        Args:
            category: 按分类过滤（可选）
            status: 按状态过滤（可选）
            
        Returns:
            插件信息列表
        """
        plugins = []
        
        for pid, info in self._registry.items():
            # 过滤条件
            if category and info.manifest.type != category:
                continue
            if status and info.status != status:
                continue
            
            plugins.append({
                "id": pid,
                "name": info.manifest.name,
                "version": info.manifest.version,
                "type": info.manifest.type.value,
                "status": info.status.value,
                "author": info.manifest.author_name,
                "description": info.manifest.description,
                "icon": info.manifest.display_icon,
                "color": info.manifest.display_color,
                "capabilities": info.manifest.capabilities,
                "pricing_model": info.manifest.pricing_model,
                "price_monthly": info.manifest.price_monthly,
                "execution_count": info.execution_count,
                "error_count": info.error_count,
                "last_execution_at": info.last_execution_at.isoformat() if info.last_execution_at else None,
                "loaded_at": info.loaded_at.isoformat(),
            })
        
        # 按名称排序
        plugins.sort(key=lambda x: x["name"])
        return plugins

    def list_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """按分类列出插件"""
        result = {}
        for cat in PluginCategory:
            plugins = self.list_plugins(category=cat)
            if plugins:
                result[cat.value] = plugins
        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        uptime = (datetime.now() - self._stats["start_time"]).total_seconds()
        
        return {
            **self._stats,
            "uptime_seconds": uptime,
            "loaded_plugins": len(self._registry),
            "max_capacity": self._max_plugins,
            "utilization_percent": round(len(self._registry) / self._max_plugins * 100, 1),
            "categories": {
                cat.value: len([p for p in self._registry.values() if p.manifest.type == cat])
                for cat in PluginCategory
            },
            "event_bus_subscriptions": self._event_bus.list_subscriptions(),
        }

    @property
    def event_bus(self) -> PluginEventBus:
        """获取事件总线实例"""
        return self._event_bus

    async def shutdown(self):
        """关闭管理器，卸载所有插件"""
        self._logger.info("🛑 正在关闭插件管理器...")
        
        plugin_ids = list(self._instances.keys())
        for pid in plugin_ids:
            await self.unload_plugin(pid)
        
        self._logger.info(f"✅ 已卸载全部 {len(plugin_ids)} 个插件")

    def __len__(self):
        """返回已加载插件数量"""
        return len(self._registry)

    def __contains__(self, plugin_id: str):
        """检查插件是否已加载"""
        return plugin_id in self._registry

    def __iter__(self):
        """迭代所有插件ID"""
        return iter(self._registry.keys())