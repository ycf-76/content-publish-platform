"""LangGraph orchestration layer.

Corresponds to architecture doc Ch.5 (Layer A).
Red lines:
- Nodes must call Harness, not MCP/LLM directly.
- Routing must be hardcoded (no LLM decisions).
- Use SqliteSaver for checkpoints (persistent, no stale state across restarts).
- 软语义节点（quality_check_*）是分散式守卫，只判质量不做路由决策。

所有节点函数、状态定义、路由函数已拆分到 app.agents.nodes 包，
本文件仅保留：
1. LangGraph checkpointer 初始化（init_global_checkpointer / get_global_checkpointer）
2. 工作流图构建（build_workflow_graph）
3. 从 nodes 包 re-export，保持 `from app.agents.graph import X` 向后兼容
"""

from __future__ import annotations

import logging

# Optional imports for LangGraph
try:
    from langgraph.graph import END, StateGraph
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    END = None
    StateGraph = None
    AsyncSqliteSaver = None

# PostgresSaver 仅在需要 PostgreSQL checkpointer 时使用，可选
try:
    from langgraph.checkpoint.postgres import PostgresSaver  # noqa: F401
except ImportError:
    PostgresSaver = None


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Re-export from nodes package (backward compatibility)
# ---------------------------------------------------------------------------

from app.agents.nodes import (  # noqa: E402
    WorkflowState,
    NodeStatus,
    initial_state,
    _merge_dict,
    _dlog,
    emit_workflow_event,
    emit_node_event,
    _run_node_harness,
    logger as _nodes_logger,
    search_node,
    analyze_node,
    image_plan_node,
    image_gen_node,
    image_review_node,
    copywrite_node,
    audit_node,
    final_review_node,
    publish_node,
    route_after_search,
    route_after_image_gen,
    route_after_image_review,
    route_after_final_review,
    rollback_to_node,
)


# ---------------------------------------------------------------------------
# Global AsyncSqliteSaver singleton (persistent checkpointer)
# ---------------------------------------------------------------------------

_global_checkpointer = None


async def init_global_checkpointer():
    """在应用 lifespan 启动时初始化全局 AsyncSqliteSaver 单例。

    必须在 async context 中调用（aiosqlite.connect 需要 await）。
    全局共享保证：start_workflow 启动 graph 和 submit_review/inject resume graph
    必须使用同一个 checkpointer 实例，否则 thread_id 无法关联状态。

    持久化到 backend/data/langgraph_checkpoints.sqlite：
    - 后端重启后 checkpoint 保留，中断的工作流可继续 resume
    - AsyncSqliteSaver 配合 astream(input) / astream(None) resume 使用
    """
    global _global_checkpointer
    if _global_checkpointer is None:
        import os

        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "langgraph_checkpoints.sqlite")

        use_sqlite = os.environ.get("LANGGRAPH_USE_SQLITE") == "1"

        if use_sqlite and AsyncSqliteSaver is not None:
            conn = None
            try:
                import sqlite3
                import aiosqlite

                priming = sqlite3.connect(db_path, check_same_thread=False)
                try:
                    priming.execute("PRAGMA journal_mode=WAL;")
                    priming.execute("PRAGMA busy_timeout=5000;")
                    priming.execute("PRAGMA synchronous=NORMAL;")
                    priming.commit()
                finally:
                    priming.close()

                conn = await aiosqlite.connect(db_path)
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA busy_timeout=5000;")
                _global_checkpointer = AsyncSqliteSaver(conn)
                await _global_checkpointer.setup()

                await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

                logger.info(f"[graph] AsyncSqliteSaver initialized + write-tested at {db_path}")
                import sys
                print("[graph] init_global_checkpointer OK: AsyncSqliteSaver", file=sys.stderr, flush=True)
                return _global_checkpointer
            except Exception as e:
                logger.warning(
                    f"[graph] AsyncSqliteSaver init/write-test failed, falling back to MemorySaver: {e}"
                )
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass
                _global_checkpointer = None

        try:
            from langgraph.checkpoint.memory import MemorySaver
            _global_checkpointer = MemorySaver()
            logger.info("[graph] MemorySaver initialized (checkpoints not persisted across restarts)")
            import sys
            print("[graph] init_global_checkpointer OK: MemorySaver", file=sys.stderr, flush=True)
        except Exception as e:
            logger.error(f"[graph] MemorySaver init also failed: {e}")
            _global_checkpointer = None
    return _global_checkpointer


def get_global_checkpointer():
    """获取已初始化的全局 AsyncSqliteSaver 单例。

    注意：必须在应用启动时调用 init_global_checkpointer() 完成初始化后才能使用。
    若未初始化，返回 None（build_workflow_graph 会因缺少 checkpointer 跳过 interrupt 支持）。
    """
    if _global_checkpointer is None:
        import sys
        print("[graph] WARNING: get_global_checkpointer() returns None — init not called?", file=sys.stderr, flush=True)
    return _global_checkpointer


# ---------------------------------------------------------------------------
# Graph Builder (optional, requires LangGraph)
# ---------------------------------------------------------------------------


def build_workflow_graph(checkpointer=None):
    """Build the workflow graph with all nodes and edges.

    支持插件节点替换：如果 NodeRegistry 中注册了与内置节点同名的插件节点，
    将自动使用插件版本替代内置版本（向后兼容）。

    Returns None if LangGraph is not available.
    """
    if not LANGGRAPH_AVAILABLE:
        logger.warning("LangGraph not available, graph building disabled")
        return None

    # 获取节点函数映射（内置 + 插件）
    node_funcs = _get_node_func_map()

    def _resolve_node(node_type: str, default_func):
        """
        解析节点执行函数：优先使用插件版本，fallback 到内置版本
        
        Args:
            node_type: 节点类型标识符（如 "copywrite"）
            default_func: 内置默认函数
            
        Returns:
            实际使用的执行函数（可能是插件版本）
        """
        if node_type in node_funcs:
            plugin_func = node_funcs[node_type]
            
            # 检查是否来自插件（非内置函数）
            builtin_funcs = {
                "search": search_node,
                "analyze": analyze_node,
                "copywrite": copywrite_node,
                "image_plan": image_plan_node,
                "image_gen": image_gen_node,
                "image_review": image_review_node,
                "audit": audit_node,
                "final_review": final_review_node,
                "publish": publish_node,
            }
            
            if plugin_func != builtin_funcs.get(node_type):
                logger.info(f"[build_workflow_graph] ✅ Using PLUGIN version for '{node_type}'")
                return plugin_func
            else:
                return default_func
        else:
            return default_func

    graph = StateGraph(WorkflowState)

    # Add nodes (支持插件替换)
    graph.add_node("search", _resolve_node("search", search_node))
    graph.add_node("analyze", _resolve_node("analyze", analyze_node))
    graph.add_node("copywrite", _resolve_node("copywrite", copywrite_node))  # ⭐ 常用替换点
    graph.add_node("image_plan", _resolve_node("image_plan", image_plan_node))
    graph.add_node("image_gen", _resolve_node("image_gen", image_gen_node))
    graph.add_node("image_review", _resolve_node("image_review", image_review_node))
    graph.add_node("audit", _resolve_node("audit", audit_node))
    graph.add_node("final_review", _resolve_node("final_review", final_review_node))
    graph.add_node("publish", _resolve_node("publish", publish_node))

    # Set entry point
    graph.set_entry_point("search")

    # Add edges (hardcoded routing)
    # search 失败（空结果/异常）→ END，避免后续节点白跑
    graph.add_conditional_edges(
        "search",
        route_after_search,
        {"analyze": "analyze", "end": END},
    )
    graph.add_edge("analyze", "copywrite")
    graph.add_edge("copywrite", "image_plan")
    # 第一期新增：image_plan 先规划图片类型+模板数据，再交给 image_gen 渲染
    graph.add_edge("image_plan", "image_gen")
    # image_gen 失败（欠费/认证/限流）→ END，避免后续 image_review/audit 白跑
    graph.add_conditional_edges(
        "image_gen",
        route_after_image_gen,
        {"image_review": "image_review", "end": END},
    )
    # 图片审核通过 → audit；拒绝 → 重做 image_gen
    graph.add_conditional_edges(
        "image_review",
        route_after_image_review,
        {"audit": "audit", "image_gen": "image_gen"},
    )
    graph.add_edge("audit", "final_review")
    graph.add_conditional_edges(
        "final_review",
        route_after_final_review,
        {"publish": "publish", "rollback": "copywrite"},
    )
    graph.add_edge("publish", END)

    # Compile：使用 interrupt_before 在创作决策点暂停，把选择权还给用户
    # - 必须提供 checkpointer（SqliteSaver 单例），否则 interrupt 后无法 resume
    # - copywrite 前 interrupt：analyze 完成后，用户选方向/调性
    # - image_gen 前 interrupt：image_plan 完成后，前端卡片编辑器加载 card_draft，用户编辑出图后 inject
    # - image_review 前 interrupt：image_gen 完成后，用户调图片
    # - final_review 前 interrupt：audit 完成后，手机预览+终审确认
    # - publish 前 interrupt：安全门，用户确认发布
    # resume 机制：调用方使用相同 thread_id 调 graph.astream(None, config)
    if checkpointer is None:
        checkpointer = get_global_checkpointer()

    compile_kwargs: dict = {
        "interrupt_before": ["copywrite", "image_gen", "image_review", "final_review", "publish"],
        # - copywrite 前：analyze 完成后，用户选方向/调性
        # - image_gen 前：image_plan 完成后，前端卡片编辑器加载 card_draft，用户编辑出图后 inject
        # - image_review 前：image_gen 完成后，用户调图片
        # - final_review 前：audit 完成后，手机预览+终审确认
        # - publish 前：安全门，用户确认发布
        "checkpointer": checkpointer,
    }

    return graph.compile(**compile_kwargs)


# ---------------------------------------------------------------------------
# Dynamic Graph Builder (from graph_definition)
# ---------------------------------------------------------------------------

# 节点类型到执行函数的映射
_NODE_FUNC_MAP: dict[str, Callable] | None = None


def _get_node_func_map() -> dict[str, Callable]:
    """懒加载节点函数映射（内置节点 + 插件节点）"""
    global _NODE_FUNC_MAP
    if _NODE_FUNC_MAP is not None:
        return _NODE_FUNC_MAP

    from app.agents.nodes import (
        search_node,
        analyze_node,
        copywrite_node,
        image_plan_node,
        image_gen_node,
        image_review_node,
        audit_node,
        final_review_node,
        publish_node,
    )

    # 1. 注册内置节点
    _NODE_FUNC_MAP = {
        "search": search_node,
        "analyze": analyze_node,
        "copywrite": copywrite_node,
        "image_plan": image_plan_node,
        "image_gen": image_gen_node,
        "image_review": image_review_node,
        "audit": audit_node,
        "final_review": final_review_node,
        "publish": publish_node,
    }

    # 2. 集成 NodeRegistry 中的插件节点
    try:
        from app.core.node_registry import node_registry
        
        plugin_nodes_count = 0
        for node_type, node_def in node_registry._registry.items():
            # 只注册有执行函数的插件节点（跳过纯内置节点）
            if node_def.execute_func and node_def.plugin_id:
                # ✅ 允许插件覆盖内置节点（用户明确安装的插件优先级更高）
                is_override = node_type in _NODE_FUNC_MAP
                
                _NODE_FUNC_MAP[node_type] = node_def.execute_func
                plugin_nodes_count += 1
                
                if is_override:
                    logger.info(
                        f"[node_func_map] 🔄 OVERRIDDEN built-in '{node_type}' "
                        f"with plugin: {node_def.plugin_id}"
                    )
                else:
                    logger.info(
                        f"[node_func_map] ✅ Registered plugin node: {node_type} "
                        f"(plugin: {node_def.plugin_id})"
                    )
        
        if plugin_nodes_count > 0:
            logger.info(f"[node_func_map] 🎉 Total {plugin_nodes_count} plugin nodes registered (overrides allowed)")
            
    except Exception as e:
        logger.warning(f"[node_func_map] ⚠️ Failed to load plugin nodes from NodeRegistry: {e}")
        import traceback
        traceback.print_exc()

    return _NODE_FUNC_MAP


def refresh_node_func_map():
    """
    强制刷新节点函数映射（安装/卸载插件后调用）
    
    Usage:
        # 安装新插件后调用
        from app.agents.graph import refresh_node_func_map
        refresh_node_func_map()
    """
    global _NODE_FUNC_MAP
    _NODE_FUNC_MAP = None  # 清除缓存，下次调用时会重新加载
    logger.info("[node_func_map] 🔄 Cache cleared, will reload on next access")


def _topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """对图定义做拓扑排序，返回节点 ID 的合法执行顺序。

    Args:
        nodes: [{id, type, config, position}, ...]
        edges: [{id, source, target}, ...]

    Returns:
        拓扑排序后的节点 ID 列表

    Raises:
        ValueError: 如果检测到环
    """
    from collections import defaultdict, deque

    node_ids = {n["id"] for n in nodes}
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = defaultdict(list)

    for e in edges:
        src, tgt = e["source"], e["target"]
        if src in node_ids and tgt in node_ids:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    result: list[str] = []

    while queue:
        nid = queue.popleft()
        result.append(nid)
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(node_ids):
        raise ValueError("图定义中存在环，无法拓扑排序")

    return result


def build_dynamic_workflow_graph(
    graph_definition: dict,
    checkpointer=None,
):
    """根据 graph_definition 动态构建 LangGraph 工作流图。

    与 build_workflow_graph（硬编码图）不同，此函数根据用户在可视化编辑器中
    定义的节点和边来构建图，支持任意节点组合和连接顺序。

    Args:
        graph_definition: {
            "nodes": [{"id": "node_1", "type": "search", "config": {}, "position": {...}}, ...],
            "edges": [{"id": "edge_1", "source": "node_1", "target": "node_2"}, ...]
        }
        checkpointer: LangGraph checkpointer 实例

    Returns:
        编译后的 LangGraph 图，或 None（如果 LangGraph 不可用）
    """
    if not LANGGRAPH_AVAILABLE:
        logger.warning("LangGraph not available, dynamic graph building disabled")
        return None

    nodes_def = graph_definition.get("nodes", [])
    edges_def = graph_definition.get("edges", [])

    if not nodes_def:
        logger.warning("build_dynamic_workflow_graph: empty nodes list")
        return None

    func_map = _get_node_func_map()

    # 构建节点 ID -> 节点类型 的映射
    node_id_to_type: dict[str, str] = {}
    type_to_node_id: dict[str, str] = {}
    for n in nodes_def:
        node_id_to_type[n["id"]] = n["type"]
        node_type = n["type"]
        if node_type in type_to_node_id:
            logger.error(
                "build_dynamic_workflow_graph: duplicate node type '%s' "
                "(nodes %s and %s); dynamic built-in nodes must be unique",
                node_type,
                type_to_node_id[node_type],
                n["id"],
            )
            return None
        type_to_node_id[node_type] = n["id"]

    # 验证所有节点类型都有对应的执行函数
    for n in nodes_def:
        if n["type"] not in func_map:
            logger.error(f"build_dynamic_workflow_graph: unknown node type '{n['type']}'")
            return None

    # LangGraph 节点名使用 node_type，而不是画布上的随机 id。
    # 节点函数、SSE 状态、DB 持久化和 interrupt/resume 都按 node_type 识别。
    effective_nodes = [
        {**n, "id": n["type"]}
        for n in nodes_def
    ]
    effective_edges = [
        {
            **e,
            "source": node_id_to_type[e["source"]],
            "target": node_id_to_type[e["target"]],
        }
        for e in edges_def
        if e.get("source") in node_id_to_type and e.get("target") in node_id_to_type
    ]

    # 拓扑排序确定执行顺序
    try:
        sorted_ids = _topological_sort(effective_nodes, effective_edges)
    except ValueError as e:
        logger.error(f"build_dynamic_workflow_graph: {e}")
        return None

    # 构建 LangGraph 图
    graph = StateGraph(WorkflowState)

    # 添加节点
    for nid in sorted_ids:
        node_func = func_map[nid]
        graph.add_node(nid, node_func)

    # 设置入口点（拓扑排序的第一个节点）
    graph.set_entry_point(sorted_ids[0])

    # 构建邻接表
    from collections import defaultdict
    adj: dict[str, list[str]] = defaultdict(list)
    for e in effective_edges:
        src, tgt = e["source"], e["target"]
        if src in sorted_ids and tgt in sorted_ids:
            adj[src].append(tgt)

    node_set = set(sorted_ids)

    # 为关键节点保留固定工作流里的条件路由。只有目标节点真的出现在当前图中时
    # 才启用，避免自定义轻量图因缺少目标节点而无法编译。
    conditional_nodes: set[str] = set()

    # search 节点始终加条件路由保护：搜索失败（空结果）→ END
    if "search" in node_set:
        search_targets = adj.get("search", [])
        if search_targets:
            first_target = search_targets[0]
            graph.add_conditional_edges(
                "search",
                route_after_search,
                {first_target: first_target, "end": END},
            )
        else:
            graph.add_conditional_edges(
                "search",
                route_after_search,
                {"end": END},
            )
        conditional_nodes.add("search")

    if "image_gen" in node_set:
        image_gen_targets = adj.get("image_gen", [])
        if "image_review" in node_set:
            graph.add_conditional_edges(
                "image_gen",
                route_after_image_gen,
                {"image_review": "image_review", "end": END},
            )
            conditional_nodes.add("image_gen")
        elif image_gen_targets:
            first_target = image_gen_targets[0]
            graph.add_conditional_edges(
                "image_gen",
                route_after_image_gen,
                {first_target: first_target, "end": END},
            )
            conditional_nodes.add("image_gen")

    if (
        "image_review" in node_set
        and "audit" in node_set
        and "image_gen" in node_set
    ):
        graph.add_conditional_edges(
            "image_review",
            route_after_image_review,
            {"audit": "audit", "image_gen": "image_gen"},
        )
        conditional_nodes.add("image_review")

    if (
        "final_review" in node_set
        and "publish" in node_set
        and "copywrite" in node_set
    ):
        graph.add_conditional_edges(
            "final_review",
            route_after_final_review,
            {"publish": "publish", "rollback": "copywrite"},
        )
        conditional_nodes.add("final_review")

    # 添加普通边
    for nid in sorted_ids:
        if nid in conditional_nodes:
            continue
        targets = adj.get(nid, [])
        if not targets:
            # 没有出边的节点 → 连到 END
            graph.add_edge(nid, END)
        elif len(targets) == 1:
            # 单一后继 → 直连
            graph.add_edge(nid, targets[0])
        else:
            # 多个后继 → 简单扇出（并行执行）
            # 注意：LangGraph 的 fan-out 会并行执行所有后继节点
            for tgt in targets:
                graph.add_edge(nid, tgt)

    # 确定哪些节点需要 interrupt（审核类节点）
    interrupt_nodes = []
    for nid in sorted_ids:
        if nid in ("copywrite", "image_gen", "image_review", "final_review", "publish"):
            interrupt_nodes.append(nid)

    if checkpointer is None:
        checkpointer = get_global_checkpointer()

    compile_kwargs: dict = {
        "checkpointer": checkpointer,
    }
    if interrupt_nodes:
        compile_kwargs["interrupt_before"] = interrupt_nodes

    logger.info(
        f"[dynamic_graph] Built dynamic graph: {len(sorted_ids)} nodes, "
        f"{len(edges_def)} edges, interrupts={interrupt_nodes}"
    )

    return graph.compile(**compile_kwargs)