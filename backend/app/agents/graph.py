"""LangGraph orchestration layer.

Corresponds to architecture doc Ch.5 (Layer A).
Red lines:
- Nodes must call Harness, not MCP/LLM directly.
- Routing must be hardcoded (no LLM decisions).
- Use SqliteSaver for checkpoints (persistent, no stale state across restarts).

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
    card_gen_node,
    wechat_push_node,
    feishu_push_node,
    route_after_search,
    route_after_analyze,
    route_after_copywrite,
    route_after_image_gen,
    route_after_image_review,
    route_after_audit,
    route_after_final_review,
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

        use_sqlite = os.environ.get("LANGGRAPH_USE_SQLITE", "1") == "1"

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
                "card_gen": card_gen_node,
                "wechat_push": wechat_push_node,
                "feishu_push": feishu_push_node,
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
    graph.add_node("card_gen", _resolve_node("card_gen", card_gen_node))
    graph.add_node("wechat_push", _resolve_node("wechat_push", wechat_push_node))
    graph.add_node("feishu_push", _resolve_node("feishu_push", feishu_push_node))

    # Set entry point
    graph.set_entry_point("search")

    # Add edges (smart routing with back-edges)
    # search: 失败/空结果 → END，否则 → analyze
    graph.add_conditional_edges(
        "search",
        route_after_search,
        {"analyze": "analyze", "end": END},
    )
    # analyze: 信心不足 → 回 search 补数据，否则 → copywrite
    graph.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {"search": "search", "copywrite": "copywrite"},
    )
    # copywrite: 信心不足 → 回 analyze 换方向，否则 → image_plan
    graph.add_conditional_edges(
        "copywrite",
        route_after_copywrite,
        {"analyze": "analyze", "image_plan": "image_plan"},
    )
    # image_plan → image_gen（确定性，无路由）
    graph.add_edge("image_plan", "image_gen")
    # image_gen: 失败 → 回退 image_plan，否则 → image_review
    graph.add_conditional_edges(
        "image_gen",
        route_after_image_gen,
        {"image_review": "image_review", "image_plan": "image_plan"},
    )
    # image_review: 通过 → audit，拒绝 → 重做 image_gen
    graph.add_conditional_edges(
        "image_review",
        route_after_image_review,
        {"audit": "audit", "image_gen": "image_gen"},
    )
    # audit: 通过 → final_review，需要修改 → 回 copywrite 带修改意见，冲突 → final_review 仲裁
    graph.add_conditional_edges(
        "audit",
        route_after_audit,
        {"copywrite": "copywrite", "final_review": "final_review"},
    )
    # final_review: 通过 → publish，不通过 → 回溯到指定节点
    graph.add_conditional_edges(
        "final_review",
        route_after_final_review,
        {
            "publish": "publish",
            "copywrite": "copywrite",
            "analyze": "analyze",
            "image_gen": "image_gen",
            "search": "search",
        },
    )

    def route_after_publish(state: WorkflowState) -> str:
        model_settings = state.get("model_settings", {}) or {}
        if model_settings.get("enable_card_gen"):
            return "card_gen"
        return "end"

    def route_after_card_gen(state: WorkflowState) -> str:
        model_settings = state.get("model_settings", {}) or {}
        if model_settings.get("enable_wechat_push"):
            return "wechat_push"
        if model_settings.get("enable_feishu_push"):
            return "feishu_push"
        return "end"

    def route_after_wechat_push(state: WorkflowState) -> str:
        model_settings = state.get("model_settings", {}) or {}
        if model_settings.get("enable_feishu_push"):
            return "feishu_push"
        return "end"

    graph.add_conditional_edges(
        "publish",
        route_after_publish,
        {"card_gen": "card_gen", "end": END},
    )
    graph.add_conditional_edges(
        "card_gen",
        route_after_card_gen,
        {"wechat_push": "wechat_push", "feishu_push": "feishu_push", "end": END},
    )
    graph.add_conditional_edges(
        "wechat_push",
        route_after_wechat_push,
        {"feishu_push": "feishu_push", "end": END},
    )
    graph.add_edge("feishu_push", END)

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
        card_gen_node,
        wechat_push_node,
        feishu_push_node,
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
        "card_gen": card_gen_node,
        "wechat_push": wechat_push_node,
        "feishu_push": feishu_push_node,
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

    # 构建邻接表（区分条件边和普通边）
    from collections import defaultdict
    adj: dict[str, list[str]] = defaultdict(list)
    conditional_adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in effective_edges:
        src, tgt = e["source"], e["target"]
        if src not in sorted_ids or tgt not in sorted_ids:
            continue
        condition = e.get("condition")
        if condition:
            conditional_adj[src].append((tgt, condition))
        else:
            adj[src].append(tgt)

    node_set = set(sorted_ids)

    # 内置节点类型 → 对应的 smart_routing 函数
    _BUILTIN_ROUTERS: dict[str, tuple[callable, dict[str, list[str]]]] = {
        "search": (route_after_search, {"end": []}),
        "analyze": (route_after_analyze, {}),
        "copywrite": (route_after_copywrite, {}),
        "image_gen": (route_after_image_gen, {"image_plan": []}),
        "image_review": (route_after_image_review, {}),
        "audit": (route_after_audit, {}),
        "final_review": (route_after_final_review, {}),
    }

    conditional_nodes: set[str] = set()

    # 第一优先级：用户在 graph_definition 边上声明了 condition 的条件路由
    for src, cond_targets in conditional_adj.items():
        if src not in node_set:
            continue
        router_info = _BUILTIN_ROUTERS.get(src)
        if router_info:
            router_func, _ = router_info
            target_map: dict[str, str] = {}
            for tgt, _cond in cond_targets:
                target_map[tgt] = tgt
            if src == "search":
                target_map["end"] = END
            if src == "image_gen" and "image_plan" in node_set:
                target_map["image_plan"] = "image_plan"
            if src == "final_review":
                for fallback in ("publish", "copywrite", "analyze", "image_gen", "search"):
                    if fallback in node_set:
                        target_map.setdefault(fallback, fallback)
            graph.add_conditional_edges(src, router_func, target_map)
            conditional_nodes.add(src)
        else:
            targets = [t for t, _ in cond_targets]
            if len(targets) == 1:
                target_map = {targets[0]: targets[0]}
                if targets[0] not in node_set:
                    target_map = {"end": END}
            else:
                target_map = {t: t for t in targets if t in node_set}
            if not target_map:
                target_map = {"end": END}

            def _make_fan_router(t_map):
                def _router(state):
                    first_key = next(iter(t_map))
                    return first_key
                return _router

            graph.add_conditional_edges(src, _make_fan_router(target_map), target_map)
            conditional_nodes.add(src)

    # 第二优先级：内置节点类型有 smart_routing 函数，且未被用户 condition 覆盖
    for node_type, (router_func, _extra) in _BUILTIN_ROUTERS.items():
        if node_type not in node_set or node_type in conditional_nodes:
            continue
        targets = adj.get(node_type, [])
        if not targets:
            continue

        target_map: dict[str, str] = {}
        if node_type == "search":
            first_target = targets[0]
            target_map = {first_target: first_target, "end": END}
        elif node_type == "image_gen":
            if "image_review" in node_set:
                target_map = {"image_review": "image_review", "image_plan": "image_plan"}
            else:
                first_target = targets[0]
                target_map = {first_target: first_target, "image_plan": "image_plan"}
        elif node_type == "image_review":
            if "audit" in node_set and "image_gen" in node_set:
                target_map = {"audit": "audit", "image_gen": "image_gen"}
            else:
                continue
        elif node_type == "final_review":
            for t in ("publish", "copywrite", "analyze", "image_gen", "search"):
                if t in node_set:
                    target_map[t] = t
            if not target_map:
                continue
        elif node_type == "analyze":
            if "search" in node_set and "copywrite" in node_set:
                target_map = {"search": "search", "copywrite": "copywrite"}
            else:
                continue
        elif node_type == "copywrite":
            if "analyze" in node_set and "image_plan" in node_set:
                target_map = {"analyze": "analyze", "image_plan": "image_plan"}
            else:
                continue
        elif node_type == "audit":
            if "copywrite" in node_set and "final_review" in node_set:
                target_map = {"copywrite": "copywrite", "final_review": "final_review"}
            else:
                continue
        else:
            continue

        graph.add_conditional_edges(node_type, router_func, target_map)
        conditional_nodes.add(node_type)

    # 添加普通边
    for nid in sorted_ids:
        if nid in conditional_nodes:
            continue
        targets = adj.get(nid, [])
        if not targets:
            graph.add_edge(nid, END)
        elif len(targets) == 1:
            graph.add_edge(nid, targets[0])
        else:
            for tgt in targets:
                graph.add_edge(nid, tgt)

    # 确定哪些节点需要 interrupt（审核类节点）
    # 节点 config 可声明 "interrupt": false 跳过人工挂起点，
    # 供定时任务流水线等无人值守场景使用（默认 true，行为不变）。
    node_config_map = {n["type"]: (n.get("config") or {}) for n in nodes_def}
    interrupt_nodes = []
    for nid in sorted_ids:
        if nid in ("copywrite", "image_gen", "image_review", "final_review", "publish"):
            if not node_config_map.get(nid, {}).get("interrupt", True):
                continue
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