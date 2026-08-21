"""
Creator Platform - Node Registry (节点注册中心)
==============================================

功能：
1. 统一管理所有可用的工作流节点（内置 + 插件）
2. 支持动态注册/注销节点类型
3. 提供节点的 Schema 元数据查询
4. 自动发现并注册插件中的 WorkflowNode

设计原则：
- 单例模式（全局唯一实例）
- 线程安全（支持并发注册和查询）
- 向后兼容（现有代码无需大改）

使用方式：
    from app.core.node_registry import node_registry
    
    # 注册内置节点
    node_registry.register_builtin_node(
        node_type="ai_copywrite",
        display_name="AI文案生成",
        category="creation",
        execute_func=copywrite_node,
        input_schema={...},
        output_schema={...},
        config_schema={...}
    )
    
    # 查询可用节点
    all_nodes = node_registry.list_all_nodes()
    creation_nodes = node_registry.list_nodes_by_category("creation")
    
    # 获取节点定义并执行
    node_def = node_registry.get_node("ai_copywrite")
    result = await node_def.execute_func(inputs, config, ctx)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import threading


logger = logging.getLogger("node_registry")


class NodeCategory(str, Enum):
    """节点分类"""
    DATASOURCE = "datasource"      # 数据源（搜索、监控、RSS）
    ANALYSIS = "analysis"          # 分析（选题分析、竞品分析）
    CREATION = "creation"          # 创作（文案生成、图片生成）
    REVIEW = "review"              # 审核（内容审核、合规检查）
    PROCESS = "process"            # 处理（格式转换、数据处理）
    PUBLISH = "publish"            # 发布（小红书、微博、公众号）
    UTILITY = "utility"            # 工具（通知、日志、统计）
    CUSTOM = "custom"              # 自定义（用户/插件添加的）


@dataclass
class NodeDefinition:
    """
    节点定义（元数据 + 执行函数）
    
    Attributes:
        node_type: 节点类型唯一标识符（如 "ai_copywrite", "xhs_publish"）
        display_name: 显示名称（如 "AI文案生成", "小红书发布器"）
        category: 所属分类（用于UI分组展示）
        description: 功能描述（帮助文档）
        icon: 图标（emoji或图标名）
        version: 版本号（语义化版本）
        
        input_schema: 输入参数JSON Schema（前端渲染表单用）
        output_schema: 输出数据JSON Schema（下游节点校验用）
        config_schema: 配置参数JSON Schema（节点配置面板用）
        
        execute_func: 执行函数引用 async func(inputs, config, ctx) -> dict
        plugin_id: 所属插件ID（None表示内置节点）
        is_builtin: 是否为内置节点
        
        tags: 标签列表（用于搜索筛选）
        author: 作者信息
        created_at: 创建时间
        updated_at: 更新时间
        
        metadata: 扩展元数据字典
        stats: 统计信息字典
    """
    
    # ===== 基本信息 =====
    node_type: str
    display_name: str
    category: str = NodeCategory.CUSTOM.value
    description: str = ""
    icon: str = "📦"
    version: str = "1.0.0"
    
    # ===== Schema 定义 =====
    input_schema: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": True,
    })
    output_schema: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": True,
    })
    config_schema: Dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
    })
    
    # ===== 执行逻辑 =====
    execute_func: Optional[Callable] = None
    plugin_id: Optional[str] = None
    is_builtin: bool = False
    
    # ===== 元信息 =====
    tags: List[str] = field(default_factory=list)
    author: str = "Unknown"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # ===== 扩展字段 =====
    metadata: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.node_type or not self.display_name:
            raise ValueError("node_type and display_name are required")
        
        # 确保 schema 有默认值
        if not self.input_schema:
            self.input_schema = {"type": "object", "properties": {}}
        if not self.output_schema:
            self.output_schema = {"type": "object", "properties": {}}
        if not self.config_schema:
            self.config_schema = {"type": "object", "properties": {}}
    
    async def execute(
        self,
        inputs: Dict[str, Any],
        config: Dict[str, Any],
        ctx: Any,  # PluginContext
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """
        执行节点逻辑（带超时控制）
        
        Args:
            inputs: 上游节点的输出数据
            config: 当前节点的配置参数
            ctx: 插件执行上下文
            timeout: 超时时间（秒）
            
        Returns:
            节点输出数据字典
            
        Raises:
            TimeoutError: 执行超时
            Exception: 执行失败
        """
        if not self.execute_func:
            raise NotImplementedError(f"Node {self.node_type} has no execute_func")
        
        start_time = time.time()
        
        try:
            import asyncio
            
            if asyncio.iscoroutinefunction(self.execute_func):
                result = await asyncio.wait_for(
                    self.execute_func(inputs, config, ctx),
                    timeout=timeout
                )
            else:
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, 
                        lambda: self.execute_func(inputs, config, ctx)
                    ),
                    timeout=timeout
                )
            
            # 更新统计
            exec_time_ms = int((time.time() - start_time) * 1000)
            self.stats["total_executions"] = self.stats.get("total_executions", 0) + 1
            self.stats["total_time_ms"] = self.stats.get("total_time_ms", 0) + exec_time_ms
            self.stats["last_execution_at"] = time.time()
            
            logger.info(f"[{self.node_type}] ✓ 执行成功 ({exec_time_ms}ms)")
            
            return result
            
        except asyncio.TimeoutError:
            exec_time_ms = int((time.time() - start_time) * 1000)
            self.stats["timeout_count"] = self.stats.get("timeout_count", 0) + 1
            logger.error(f"[{self.node_type}] ✗ 执行超时 ({exec_time_ms}ms > {timeout}s)")
            raise TimeoutError(f"Node {self.node_type} execution timed out after {timeout}s")
            
        except Exception as e:
            exec_time_ms = int((time.time() - start_time) * 1000)
            self.stats["error_count"] = self.stats.get("error_count", 0) + 1
            self.stats["last_error"] = str(e)
            logger.error(f"[{self.node_type}] ✗ 执行异常: {e}")
            raise
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于API返回）"""
        return {
            "node_type": self.node_type,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "icon": self.icon,
            "version": self.version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "config_schema": self.config_schema,
            "plugin_id": self.plugin_id,
            "is_builtin": self.is_builtin,
            "tags": self.tags,
            "author": self.author,
            "stats": self.stats,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """简化版序列化（用于列表展示，不含详细Schema）"""
        return {
            "node_type": self.node_type,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description[:100],  # 截断描述
            "icon": self.icon,
            "version": self.version,
            "plugin_id": self.plugin_id,
            "is_builtin": self.is_builtin,
            "tags": self.tags,
        }


class NodeRegistry:
    """
    节点注册中心（单例）
    
    全局唯一的节点管理器，负责：
    - 节点的注册和注销
    - 节点信息的查询
    - 分类和标签过滤
    - 插件节点的自动发现
    
    Usage:
        # 获取单例实例
        from app.core.node_registry import node_registry
        
        # 注册节点
        node_registry.register(node_def)
        
        # 查询节点
        node = node_registry.get("ai_copywrite")
        nodes = node_registry.list_by_category("creation")
        
        # 注销节点
        node_registry.unregister("old_node")
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._registry: Dict[str, NodeDefinition] = {}
        self._categories: Dict[str, List[str]] = {}  # category -> [node_types]
        self._tags_index: Dict[str, Set[str]] = {}   # tag -> set(node_types)
        self._lock = threading.RLock()
        
        self._stats = {
            "total_registered": 0,
            "total_unregistered": 0,
            "builtin_count": 0,
            "plugin_count": 0,
            "created_at": time.time(),
        }
        
        self._initialized = True
        logger.info("✅ NodeRegistry 初始化完成")
    
    def register(self, node_def: NodeDefinition) -> bool:
        """
        注册节点
        
        Args:
            node_def: 节点定义对象
            
        Returns:
            bool: 是否注册成功
            
        Raises:
            ValueError: 参数无效或节点已存在
        """
        if not isinstance(node_def, NodeDefinition):
            raise TypeError("Expected NodeDefinition instance")
        
        with self._lock:
            node_type = node_def.node_type
            
            # 检查是否已存在
            if node_type in self._registry:
                existing = self._registry[node_type]
                
                # 允许同类型更新（版本升级或配置变更）
                if existing.plugin_id == node_def.plugin_id:
                    logger.warning(f"⚠️ 节点已存在，将被覆盖: {node_type}")
                else:
                    # 不同来源的同名节点冲突
                    raise ValueError(
                        f"Node type conflict: '{node_type}' already registered by "
                        f"{existing.plugin_id or 'builtin'}, cannot register from "
                        f"{node_def.plugin_id or 'builtin'}"
                    )
            
            # 注册到主表
            self._registry[node_type] = node_def
            
            # 更新分类索引
            cat = node_def.category
            if cat not in self._categories:
                self._categories[cat] = []
            if node_type not in self._categories[cat]:
                self._categories[cat].append(node_type)
            
            # 更新标签索引
            for tag in node_def.tags:
                if tag not in self._tags_index:
                    self._tags_index[tag] = set()
                self._tags_index[tag].add(node_type)
            
            # 更新统计
            self._stats["total_registered"] += 1
            if node_def.is_builtin:
                self._stats["builtin_count"] += 1
            elif node_def.plugin_id:
                self._stats["plugin_count"] += 1
            
            node_def.updated_at = time.time()
            
            logger.info(
                f"✅ 节点已注册: [{node_def.icon}] {node_def.display_name} "
                f"({node_type}) - {node_def.category}"
            )
            
            return True
    
    def unregister(self, node_type: str) -> bool:
        """
        注销节点
        
        Args:
            node_type: 要注销的节点类型
            
        Returns:
            bool: 是否成功注销
        """
        with self._lock:
            if node_type not in self._registry:
                logger.warning(f"⚠️ 尝试注销不存在的节点: {node_type}")
                return False
            
            node_def = self._registry.pop(node_type)
            
            # 清理分类索引
            cat = node_def.category
            if cat in self._categories and node_type in self._categories[cat]:
                self._categories[cat].remove(node_type)
                if not self._categories[cat]:
                    del self._categories[cat]
            
            # 清理标签索引
            for tag in node_def.tags:
                if tag in self._tags_index:
                    self._tags_index[tag].discard(node_type)
                    if not self._tags_index[tag]:
                        del self._tags_index[tag]
            
            self._stats["total_unregistered"] += 1
            if node_def.is_builtin:
                self._stats["builtin_count"] -= 1
            elif node_def.plugin_id:
                self._stats["plugin_count"] -= 1
            
            logger.info(f"🗑️ 节点已注销: {node_type}")
            
            return True
    
    def get(self, node_type: str) -> Optional[NodeDefinition]:
        """
        获取节点定义
        
        Args:
            node_type: 节点类型标识符
            
        Returns:
            NodeDefinition 或 None
        """
        with self._lock:
            return self._registry.get(node_type)
    
    def exists(self, node_type: str) -> bool:
        """检查节点是否存在"""
        with self._lock:
            return node_type in self._registry
    
    def list_all(
        self,
        include_details: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        列出所有节点
        
        Args:
            include_details: 是否包含详细Schema信息
            
        Returns:
            节点定义列表
        """
        with self._lock:
            nodes = list(self._registry.values())
            
            if include_details:
                return [n.to_dict() for n in nodes]
            else:
                return [n.to_simple_dict() for n in nodes]
    
    def list_by_category(
        self,
        category: str,
        include_details: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        按分类列出节点
        
        Args:
            category: 分类名称
            include_details: 是否包含详细信息
            
        Returns:
            该分类下的节点列表
        """
        with self._lock:
            node_types = self._categories.get(category, [])
            nodes = [self._registry[nt] for nt in node_types if nt in self._registry]
            
            if include_details:
                return [n.to_dict() for n in nodes]
            else:
                return [n.to_simple_dict() for n in nodes]
    
    def list_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        include_details: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        按标签筛选节点
        
        Args:
            tags: 标签列表
            match_all: True=匹配所有标签, False=匹配任一标签
            include_details: 是否包含详细信息
            
        Returns:
            符合条件的节点列表
        """
        with self._lock:
            if match_all:
                # 必须包含所有标签
                result_sets = [self._tags_index.get(tag, set()) for tag in tags]
                if not result_sets:
                    return []
                matching_types = set.intersection(*result_sets)
            else:
                # 包含任一标签即可
                matching_types = set()
                for tag in tags:
                    matching_types.update(self._tags_index.get(tag, set()))
            
            nodes = [self._registry[nt] for nt in matching_types if nt in self._registry]
            
            if include_details:
                return [n.to_dict() for n in nodes]
            else:
                return [n.to_simple_dict() for n in nodes]
    
    def search(
        self,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        搜索节点（按名称、描述、标签模糊匹配）
        
        Args:
            query: 搜索关键词
            limit: 返回数量上限
            
        Returns:
            匹配的节点列表
        """
        query_lower = query.lower().strip()
        
        if not query_lower:
            return self.list_all(include_details=False)[:limit]
        
        with self._lock:
            scored_results = []
            
            for node_def in self._registry.values():
                score = 0
                
                # 名称匹配（权重最高）
                if query_lower in node_def.display_name.lower():
                    score += 10
                if query_lower == node_def.display_name.lower():
                    score += 20
                
                # 类型标识符匹配
                if query_lower in node_def.node_type.lower():
                    score += 8
                
                # 描述匹配
                if query_lower in node_def.description.lower():
                    score += 5
                
                # 标签匹配
                for tag in node_def.tags:
                    if query_lower in tag.lower():
                        score += 3
                
                # 分类匹配
                if query_lower in node_def.category.lower():
                    score += 2
                
                if score > 0:
                    scored_results.append((score, node_def))
            
            # 按分数降序排列
            scored_results.sort(key=lambda x: x[0], reverse=True)
            
            # 取前N个
            top_results = scored_results[:limit]
            
            return [n.to_simple_dict() for _, n in top_results]
    
    def get_categories(self) -> List[Dict[str, Any]]:
        """
        获取所有分类及其节点数量
        
        Returns:
            [{"category": "...", "label": "...", "count": N}, ...]
        """
        CATEGORY_LABELS = {
            "datasource": "数据源",
            "analysis": "分析",
            "creation": "内容创作",
            "review": "审核",
            "process": "处理",
            "publish": "发布",
            "utility": "工具",
            "custom": "自定义",
        }
        with self._lock:
            categories = []
            
            for cat, node_types in self._categories.items():
                label = CATEGORY_LABELS.get(cat, cat)
                
                categories.append({
                    "category": cat,
                    "label": label,
                    "count": len(node_types),
                })
            
            # 按节点数量降序排序
            categories.sort(key=lambda x: x["count"], reverse=True)
            
            return categories
    
    def get_stats(self) -> Dict[str, Any]:
        """获取注册中心统计信息"""
        with self._lock:
            return {
                **self._stats,
                "current_total": len(self._registry),
                "category_count": len(self._categories),
                "tag_count": len(self._tags_index),
            }
    
    def register_builtin_node(
        self,
        *,
        node_type: str,
        display_name: str,
        category: str = NodeCategory.CUSTOM.value,
        execute_func: Callable,
        input_schema: Optional[Dict] = None,
        output_schema: Optional[Dict] = None,
        config_schema: Optional[Dict] = None,
        icon: str = "📦",
        description: str = "",
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> NodeDefinition:
        """
        便捷方法：注册内置节点
        
        Args:
            node_type: 节点类型标识
            display_name: 显示名称
            category: 分类
            execute_func: 执行函数
            input_schema: 输入Schema
            output_schema: 输出Schema
            config_schema: 配置Schema
            icon: 图标
            description: 描述
            tags: 标签列表
            **kwargs: 其他NodeDefinition参数
            
        Returns:
            创建并注册的NodeDefinition对象
        """
        node_def = NodeDefinition(
            node_type=node_type,
            display_name=display_name,
            category=category,
            execute_func=execute_func,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            config_schema=config_schema or {},
            icon=icon,
            description=description,
            tags=tags or [],
            is_builtin=True,
            author="Platform Team",
            **kwargs,
        )
        
        self.register(node_def)
        return node_def
    
    def clear_all(self) -> int:
        """
        清空所有节点（仅用于测试）
        
        Returns:
            清除的节点数量
        """
        with self._lock:
            count = len(self._registry)
            self._registry.clear()
            self._categories.clear()
            self._tags_index.clear()
            logger.warning(f"⚠️ 已清空所有注册节点 (共{count}个)")
            return count
    
    def __len__(self) -> int:
        """返回已注册节点总数"""
        with self._lock:
            return len(self._registry)
    
    def __contains__(self, node_type: str) -> bool:
        """支持 'in' 操作符"""
        return self.exists(node_type)
    
    def __iter__(self):
        """支持迭代"""
        with self._lock:
            return iter(list(self._registry.values()))


# ===== 全局单例实例 =====

# 模块级单例（延迟初始化）
_node_registry_instance: Optional[NodeRegistry] = None
_registry_lock = threading.Lock()


def get_node_registry() -> NodeRegistry:
    """
    获取全局节点注册中心单例
    
    Usage:
        from app.core.node_registry import get_node_registry
        
        registry = get_node_registry()
        registry.register(...)
    """
    global _node_registry_instance
    
    if _node_registry_instance is None:
        with _registry_lock:
            if _node_registry_instance is None:
                _node_registry_instance = NodeRegistry()
    
    return _node_registry_instance


# 为了方便使用，导出一个简短的全局变量名
# （在模块首次导入时自动创建单例）
try:
    node_registry = get_node_registry()
except Exception as e:
    logger.error(f"❌ 创建 NodeRegistry 单例失败: {e}")
    node_registry = None


# ===== 内置节点自动注册函数 =====

def register_default_workflow_nodes():
    """
    注册默认的工作流节点（向后兼容）
    
    在应用启动时调用此函数，将现有的12个硬编码节点
    注册到 NodeRegistry 中，使其可以通过统一接口访问。
    
    此函数不会修改现有代码的行为，只是增加了一个
    动态查询和管理这些节点的入口。
    """
    global node_registry
    
    if node_registry is None:
        logger.error("❌ NodeRegistry 未初始化，无法注册默认节点")
        return
    
    try:
        # 导入现有的节点函数
        from app.agents.nodes.search import search_node
        from app.agents.nodes.analyze import analyze_node
        from app.agents.nodes.copywrite import copywrite_node
        from app.agents.nodes.image_plan import image_plan_node
        from app.agents.nodes.image_gen import image_gen_node
        from app.agents.nodes.image_review import image_review_node
        from app.agents.nodes.audit import audit_node
        from app.agents.nodes.final_review import final_review_node
        from app.agents.nodes.publish import publish_node
        
        # ===== 数据源类节点 =====
        node_registry.register_builtin_node(
            node_type="search",
            display_name="智能搜索",
            category="datasource",
            execute_func=search_node,
            icon="🔍",
            description="搜索小红书/全网热点内容，支持关键词和多源聚合",
            tags=["search", "xiaohongshu", "trending", "datasource"],
            input_schema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "搜索主题/关键词"
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "数据源列表（可选）",
                        "default": ["xiaohongshu", "google"]
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 50,
                        "default": 20,
                        "description": "返回结果数量上限"
                    }
                },
                "required": ["topic"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "description": "搜索结果列表"
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "提取的关键词"
                    },
                    "summary": {
                        "type": "string",
                        "description": "搜索结果摘要"
                    }
                }
            },
            config_schema={
                "type": "object",
                "properties": {
                    "use_cache": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否使用缓存"
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 10,
                        "maximum": 120,
                        "default": 30,
                        "description": "超时时间（秒）"
                    }
                }
            }
        )
        
        # ===== 分析类节点 =====
        node_registry.register_builtin_node(
            node_type="analyze",
            display_name="AI选题分析",
            category="analysis",
            execute_func=analyze_node,
            icon="📊",
            description="使用AI分析选题价值、竞争度和可行性",
            tags=["analysis", "ai", "topic", "strategy"],
            input_schema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "待分析的选题"
                    },
                    "search_results": {
                        "type": "array",
                        "description": "上游搜索节点的输出"
                    },
                    "context": {
                        "type": "object",
                        "description": "额外上下文信息"
                    }
                },
                "required": ["topic"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "score": {
                        "type": "number",
                        "description": "综合评分 (0-100)"
                    },
                    "suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "优化建议"
                    },
                    "competitors": {
                        "type": "array",
                        "description": "竞品分析结果"
                    },
                    "recommendation": {
                        "type": "string",
                        "enum": ["recommended", "neutral", "not_recommended"],
                        "description": "推荐程度"
                    }
                }
            }
        )
        
        # ===== 创作类节点 =====
        node_registry.register_builtin_node(
            node_type="copywrite",
            display_name="AI文案生成",
            category="creation",
            execute_func=copywrite_node,
            icon="✍️",
            description="使用DeepSeek AI生成高质量营销文案（标题+正文+关键词）",
            tags=["ai", "copywriting", "deepseek", "content", "creation"],
            input_schema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "创作主题"
                    },
                    "style": {
                        "type": "string",
                        "enum": ["professional", "casual", "humorous", "emotional"],
                        "default": "casual",
                        "description": "文案风格"
                    },
                    "tone": {
                        "type": "string",
                        "description": "语调要求"
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "必须包含的关键词"
                    },
                    "reference": {
                        "type": "string",
                        "description": "参考文案（可选）"
                    },
                    "analysis_result": {
                        "type": "object",
                        "description": "上游分析节点的输出"
                    }
                },
                "required": ["topic"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "生成的标题"
                    },
                    "content": {
                        "type": "string",
                        "description": "生成的正文内容"
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "提取/生成的关键词"
                    },
                    "hashtags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "推荐的话题标签"
                    },
                    "word_count": {
                        "type": "integer",
                        "description": "正文字数"
                    }
                }
            },
            config_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "deepseek-chat",
                        "description": "使用的AI模型"
                    },
                    "temperature": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 2,
                        "default": 0.7,
                        "description": "创造性（越高越发散）"
                    },
                    "max_tokens": {
                        "type": "integer",
                        "minimum": 500,
                        "maximum": 8000,
                        "default": 2000,
                        "description": "最大生成长度"
                    },
                    "language": {
                        "type": "string",
                        "default": "zh-CN",
                        "description": "输出语言"
                    }
                }
            }
        )
        
        node_registry.register_builtin_node(
            node_type="image_plan",
            display_name="AI图片规划",
            category="creation",
            execute_func=image_plan_node,
            icon="🎨",
            description="根据文案内容规划图片风格、构图和视觉元素",
            tags=["ai", "image", "plan", "visual", "design"],
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "笔记标题"
                    },
                    "content": {
                        "type": "string",
                        "description": "笔记正文"
                    },
                    "style_preference": {
                        "type": "string",
                        "description": "风格偏好"
                    },
                    "image_count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 9,
                        "default": 4,
                        "description": "图片数量"
                    }
                },
                "required": ["title", "content"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "image_plans": {
                        "type": "array",
                        "description": "每张图片的规划详情"
                    },
                    "overall_style": {
                        "type": "string",
                        "description": "整体视觉风格建议"
                    },
                    "color_palette": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "推荐配色方案"
                    }
                }
            }
        )
        
        node_registry.register_builtin_node(
            node_type="image_gen",
            display_name="AI图片生成",
            category="creation",
            execute_func=image_gen_node,
            icon="🖼️",
            description="根据规划生成高质量配图（支持多种风格）",
            tags=["ai", "image", "generation", "dall-e", "midjourney"],
            input_schema={
                "type": "object",
                "properties": {
                    "image_plans": {
                        "type": "array",
                        "description": "上游图片规划节点的输出"
                    },
                    "prompts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "图片生成提示词"
                    },
                    "style": {
                        "type": "string",
                        "description": "图片风格"
                    },
                    "size": {
                        "type": "string",
                        "enum": ["1024x1024", "1792x1024", "1024x1792"],
                        "default": "1024x1024",
                        "description": "图片尺寸"
                    }
                },
                "required": ["prompts"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "images_base64": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Base64编码的图片列表"
                    },
                    "images_url": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "图片URL列表（如果上传了）"
                    },
                    "metadata": {
                        "type": "array",
                        "description": "每张图片的元数据"
                    }
                }
            },
            config_schema={
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "enum": ["dall-e-3", "dall-e-2", "stable-diffusion", "midjourney"],
                        "default": "dall-e-3",
                        "description": "图片生成服务提供商"
                    },
                    "quality": {
                        "type": "string",
                        "enum": ["standard", "hd"],
                        "default": "hd",
                        "description": "图片质量"
                    }
                }
            }
        )
        
        # ===== 审核类节点 =====
        node_registry.register_builtin_node(
            node_type="image_review",
            display_name="图片审核",
            category="review",
            execute_func=image_review_node,
            icon="🔍",
            description="审核生成图片的质量、合规性和与文案的匹配度",
            tags=["review", "image", "quality", "compliance"],
            input_schema={
                "type": "object",
                "properties": {
                    "images_base64": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "待审核的图片"
                    },
                    "title": {
                        "type": "string",
                        "description": "关联的笔记标题"
                    },
                    "content": {
                        "type": "string",
                        "description": "关联的笔记正文"
                    },
                    "strictness": {
                        "type": "string",
                        "enum": ["loose", "normal", "strict"],
                        "default": "normal",
                        "description": "审核严格度"
                    }
                },
                "required": ["images_base64"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "approved_images": {
                        "type": "array",
                        "description": "通过审核的图片"
                    },
                    "rejected_images": {
                        "type": "array",
                        "description": "被拒绝的图片及原因"
                    },
                    "suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "优化建议"
                    },
                    "overall_score": {
                        "type": "number",
                        "description": "整体质量评分 (0-100)"
                    }
                }
            }
        )
        
        node_registry.register_builtin_node(
            node_type="audit",
            display_name="合规审核",
            category="review",
            execute_func=audit_node,
            icon="✅",
            description="检查内容的合规性（敏感词、广告法、平台规则）",
            tags=["compliance", "legal", "safety", "moderation"],
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "待审核的标题"
                    },
                    "content": {
                        "type": "string",
                        "description": "待审核的正文"
                    },
                    "platform": {
                        "type": "string",
                        "default": "xiaohongshu",
                        "description": "目标平台"
                    },
                    "check_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要检查的项目",
                        "default": ["sensitive_words", "advertising", "copyright", "platform_rules"]
                    }
                },
                "required": ["title", "content"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "passed": {
                        "type": "boolean",
                        "description": "是否通过审核"
                    },
                    "issues": {
                        "type": "array",
                        "description": "发现的问题列表"
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "风险等级"
                    },
                    "suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "修改建议"
                    }
                }
            }
        )
        
        node_registry.register_builtin_node(
            node_type="final_review",
            display_name="终审确认",
            category="review",
            execute_func=final_review_node,
            icon="👁️",
            description="最终人工/AI审核，确认内容质量和可发布性",
            tags=["review", "final", "quality-control", "approval"],
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string"
                    },
                    "content": {
                        "type": "string"
                    },
                    "images_base64": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "audit_result": {
                        "type": "object",
                        "description": "合规审核结果"
                    },
                    "image_review_result": {
                        "type": "object",
                        "description": "图片审核结果"
                    },
                    "auto_approve": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否自动批准（跳过人工确认）"
                    }
                },
                "required": ["title", "content"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "approved": {
                        "type": "boolean",
                        "description": "是否批准发布"
                    },
                    "final_title": {
                        "type": "string",
                        "description": "最终确定的标题"
                    },
                    "final_content": {
                        "type": "string",
                        "description": "最终确定的正文"
                    },
                    "final_images": {
                        "type": "array",
                        "description": "最终确定使用的图片"
                    },
                    "feedback": {
                        "type": "string",
                        "description": "审批意见"
                    }
                }
            }
        )
        
        # ===== 发布类节点 =====
        node_registry.register_builtin_node(
            node_type="publish",
            display_name="发布到小红书",
            category="publish",
            execute_func=publish_node,
            icon="📕",
            description="将审核通过的图文笔记发布到小红书平台",
            tags=["publish", "xiaohongshu", "social-media", "distribution"],
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "笔记标题（≤20字）"
                    },
                    "content": {
                        "type": "string",
                        "description": "笔记正文"
                    },
                    "images_base64": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Base64编码的图片（最多9张）"
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "话题标签"
                    },
                    "account_id": {
                        "type": "string",
                        "description": "小红书账号ID"
                    },
                    "publish_mode": {
                        "type": "string",
                        "enum": ["auto", "semi_auto", "manual"],
                        "default": "semi_auto",
                        "description": "发布模式"
                    }
                },
                "required": ["title", "content"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "post_id": {
                        "type": "string",
                        "description": "发布的笔记ID"
                    },
                    "post_url": {
                        "type": "string",
                        "description": "笔记链接"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["success", "failed", "pending"],
                        "description": "发布状态"
                    },
                    "message": {
                        "type": "string",
                        "description": "状态消息"
                    }
                }
            },
            config_schema={
                "type": "object",
                "properties": {
                    "retry_count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 3,
                        "default": 2,
                        "description": "失败重试次数"
                    },
                    "delay_between_retries": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 60,
                        "default": 10,
                        "description": "重试间隔（秒）"
                    }
                }
            }
        )
        
        logger.info(
            f"✅ 已注册 {len(node_registry)} 个默认工作流节点 "
            f"(内置: {node_registry.get_stats()['builtin_count']})"
        )
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ 导入节点模块失败: {e}")
        return False
    except Exception as e:
        logger.exception(f"❌ 注册默认节点异常: {e}")
        return False


if __name__ == "__main__":
    """
    本地测试入口
    """
    import asyncio
    
    async def test_registry():
        print("=" * 60)
        print("  NodeRegistry 测试")
        print("=" * 60)
        
        # 获取注册中心
        registry = get_node_registry()
        
        # 测试1: 注册默认节点
        print("\n[Test 1] 注册默认工作流节点:")
        success = register_default_workflow_nodes()
        print(f"  结果: {'✅ 成功' if success else '❌ 失败'}")
        print(f"  当前节点数: {len(registry)}")
        
        # 测试2: 查询所有节点
        print("\n[Test 2] 列出所有节点:")
        all_nodes = registry.list_all()
        for node in all_nodes:
            print(f"  [{node['icon']}] {node['display_name']} ({node['node_type']}) - {node['category']}")
        
        # 测试3: 按分类查询
        print("\n[Test 3] 按分类查询:")
        categories = registry.get_categories()
        for cat in categories:
            print(f"  {cat['category']}: {cat['count']}个节点")
        
        creation_nodes = registry.list_by_category("creation")
        print(f"\n  创作类节点 ({len(creation_nodes)}个):")
        for node in creation_nodes:
            print(f"    - {node['display_name']}")
        
        # 测试4: 搜索节点
        print("\n[Test 4] 搜索节点 (关键词: AI):")
        results = registry.search("AI", limit=5)
        for node in results:
            print(f"  - {node['display_name']}")
        
        # 测试5: 获取单个节点详情
        print("\n[Test 5] 获取节点详情:")
        copywrite_node_def = registry.get("copywrite")
        if copywrite_node_def:
            detail = copywrite_node_def.to_dict()
            print(f"  节点类型: {detail['node_type']}")
            print(f"  显示名称: {detail['display_name']}")
            print(f"  输入Schema: {list(detail['input_schema']['properties'].keys())}")
            print(f"  输出Schema: {list(detail['output_schema']['properties'].keys())}")
            print(f"  配置Schema: {list(detail['config_schema']['properties'].keys())}")
        
        # 测试6: 统计信息
        print("\n[Test 6] 统计信息:")
        stats = registry.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        print("\n" + "=" * 60)
        print("  所有测试完成!")
        print("=" * 60)
    
    asyncio.run(test_registry())