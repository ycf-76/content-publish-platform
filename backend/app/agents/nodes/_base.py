"""工作流节点共享基础设施。

所有节点模块（search.py / analyze.py / ...）都从这里 import：
- NodeStatus / WorkflowState / initial_state：状态定义
- emit_node_event / emit_workflow_event：SSE 事件
- _run_node_harness：统一 harness 调用封装
- _dlog：发布流程诊断日志
- _merge_dict：LangGraph reducer

红线：
- 不 import langgraph / fastapi（保持节点模块可独立测试）
- 不依赖具体 LLM / MCP / DB（由节点函数内部 lazy import）
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import TYPE_CHECKING, Annotated, TypedDict

from app.services.sse_bus import sse_bus


# ----------------------------------------------------------------------
# Logger & 诊断日志
# ----------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ===== DEBUG: 发布流程诊断日志（写到独立文件，便于排查 publish 不执行的问题） =====
_debug_logger = logging.getLogger("publish_debug")
if not _debug_logger.handlers:
    _debug_logger.setLevel(logging.DEBUG)
    try:
        _log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "logs",
        )
        os.makedirs(_log_dir, exist_ok=True)
        _fh = logging.FileHandler(
            os.path.join(_log_dir, "publish_debug.log"), encoding="utf-8"
        )
        _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        _debug_logger.addHandler(_fh)
    except Exception:
        pass
_debug_logger.propagate = False


def _dlog(msg: str) -> None:
    """发布流程诊断日志（写到 backend/logs/publish_debug.log）。"""
    _debug_logger.info(msg)


# ----------------------------------------------------------------------
# LangGraph reducer
# ----------------------------------------------------------------------


def _merge_dict(left: dict, right: dict | None) -> dict:
    """LangGraph reducer for dict fields: merge right into left (non-destructive).

    用于 node_outputs / node_statuses：每个节点返回自己的部分，
    reducer 会合并到现有 state 中，而不是覆盖整个 dict。
    """
    if right is None:
        return left or {}
    result = dict(left or {})
    result.update(right)
    return result


# ----------------------------------------------------------------------
# Node Status Enum (9 states, matching protocol Ch.4)
# ----------------------------------------------------------------------


class NodeStatus(str, Enum):  # ruff: noqa: UP042
    """Node status enum matching protocol."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    PASSED = "passed"
    REJECTED = "rejected"
    ERROR = "error"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    TERMINATED = "terminated"


# ----------------------------------------------------------------------
# Workflow State (TypedDict for LangGraph)
# ----------------------------------------------------------------------


class WorkflowState(TypedDict, total=False):
    """Workflow state passed between LangGraph nodes.

    D6: No stale state field. Recovery uses LangGraph native checkpoint.
    """

    workflow_id: str
    user_id: str
    account_id: str
    topic: str
    # topic 兼容旧工作流；新工作流将搜索词和创作要求拆开传递
    search_keyword: str
    creative_brief: str
    current_node: str
    # Annotated reducer：节点返回的部分 dict 会被合并到现有 state，
    # 而不是覆盖整个 node_statuses / node_outputs。
    node_statuses: Annotated[dict[str, str], _merge_dict]  # node_key -> NodeStatus.value
    node_outputs: Annotated[dict[str, dict], _merge_dict]  # node_key -> output_data
    node_errors: Annotated[dict[str, dict], _merge_dict]  # node_key -> error info
    recovery_attempts: Annotated[dict[str, int], _merge_dict]  # node_key -> attempts count
    pending_reviews: list[dict]  # current pending reviews
    pending_suggestions: list[dict]  # supervisor suggestions
    suspended_until: str | None  # ISO datetime for D15 suspension
    # 用户在右侧工作区选择的模型/温度/风格配置（透传到各节点）
    model_settings: dict
    # 选题池参考素材（从选题池"发起新工作流"时携带）
    reference: dict
    # 用户级长期记忆（工作流启动时从 AgentMemory 加载）
    user_memory: dict
    # Phase 4：用户本地图片资产与无模板图片模式
    image_assets: list[dict]
    asset_mode: bool
    # Phase 5：目标平台与输出比例
    platform: str
    format_name: str
    # 智能体信念系统：每个 agent 的信念快照（agent_id -> belief dict）
    agent_beliefs: Annotated[dict[str, dict], _merge_dict]
    # 协商记录（audit vs copywrite 冲突仲裁等）
    negotiations: list[dict]
    # 回溯计数器（node_id -> 回溯次数），防死循环
    loop_counters: Annotated[dict[str, int], _merge_dict]
    # D18 创作者画像：启动工作流时从 DB 读取注入（UserProfile.model_dump()）
    # 红线：启动时一次性注入 state，节点内禁止自己读 DB 查画像
    user_profile: dict | None
    # D19 自我进化机制：预留字段恒 None，禁止实现任何注入逻辑
    experience_hints: dict | None


def initial_state(
    workflow_id: str,
    user_id: str,
    account_id: str,
    topic: str,
    search_keyword: str = "",
    creative_brief: str = "",
    model_settings: dict | None = None,
    reference: dict | None = None,
    user_memory: dict | None = None,
    image_assets: list[dict] | None = None,
    asset_mode: bool = False,
    platform: str = "xiaohongshu",
    format_name: str = "",
    node_types: list[str] | None = None,
    user_profile: dict | None = None,
) -> WorkflowState:
    """Create initial workflow state.

    Args:
        node_types: 动态节点类型列表。如果为 None，使用默认9个节点。
                    传入后，node_statuses 只包含这些节点。
        user_profile: D18 创作者画像（UserProfile.model_dump()）。
                     启动工作流时由 WorkflowService 从 DB 读取注入。
    """
    if node_types is None:
        node_types = [
            "search", "analyze", "copywrite", "image_plan",
            "image_gen", "image_review", "audit", "final_review", "publish",
            "card_gen", "wechat_push", "feishu_push",
        ]

    node_statuses_init = {nt: NodeStatus.PENDING.value for nt in node_types}

    return WorkflowState(
        workflow_id=workflow_id,
        user_id=user_id,
        account_id=account_id,
        topic=topic,
        search_keyword=(search_keyword or topic).strip(),
        creative_brief=(creative_brief or "").strip(),
        current_node=node_types[0] if node_types else "search",
        node_statuses=node_statuses_init,
        node_outputs={},
        node_errors={},
        recovery_attempts={},
        pending_reviews=[],
        pending_suggestions=[],
        suspended_until=None,
        model_settings=dict(model_settings or {}),
        reference=dict(reference or {}),
        user_memory=dict(user_memory or {}),
        image_assets=list(image_assets or []),
        asset_mode=asset_mode,
        platform=platform,
        format_name=format_name,
        agent_beliefs={},
        negotiations=[],
        loop_counters={},
        # D18: 启动时一次性注入画像（节点从 state 读取，禁止自己查 DB）
        user_profile=dict(user_profile) if user_profile else None,
        # D19: 预留恒 None（红线：禁止实现任何注入逻辑）
        experience_hints=None,
    )


# ----------------------------------------------------------------------
# SSE Event Helpers
# ----------------------------------------------------------------------


async def emit_workflow_event(
    workflow_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """Emit workflow-level SSE event."""
    await sse_bus.publish(workflow_id, event_type, payload)


async def emit_node_event(
    workflow_id: str,
    node_id: str,
    event_type: str,
    payload: dict | None = None,
) -> None:
    """Emit node-level SSE event."""
    await sse_bus.publish(
        workflow_id,
        event_type,
        {"node_id": node_id, **(payload or {})},
    )


# ----------------------------------------------------------------------
# 统一 Harness 调用封装
# ----------------------------------------------------------------------


async def _run_node_harness(
    node_id: str,
    workflow_id: str,
    state: WorkflowState,
    harness_factory: str,
    harness_input: dict,
    fallback_output: dict,
) -> dict:
    """统一调用 harness 的封装。

    - harness_factory: app.engine.factory 里的函数名
    - 失败时发 node_error 事件，并把 fallback_output 作为 node_outputs 写回状态，
      保证 workflow 不因单节点崩溃而中断。
    - 把 workflow_id 写入 current_workflow_id ContextVar，让 MCP 层能感知上下文。
    """
    from app.engine.schemas import WorkflowContext
    from app.engine import factory as harness_factory_mod
    from app.services.context import current_workflow_id

    factory_fn = getattr(harness_factory_mod, harness_factory, None)
    if factory_fn is None:
        logger.error(f"[{workflow_id}] {node_id} unknown harness factory: {harness_factory}")
        await emit_node_event(workflow_id, node_id, "node_error",
                              {"error": f"unknown factory: {harness_factory}"})
        return dict(fallback_output)

    context = WorkflowContext(
        workflow_id=workflow_id,
        node_id=node_id,
        user_id=state.get("user_id", ""),
        account_id=state.get("account_id", ""),
        topic=state.get("topic", ""),
        upstream_outputs=state.get("node_outputs", {}),
        # D18: 画像从 state 透传给 harness（prompt 渲染可从 context.user_profile 取）
        user_profile=state.get("user_profile") or None,
    )

    token = current_workflow_id.set(workflow_id)
    try:
        harness = factory_fn(workflow_id)
        agent_output = await harness.run(harness_input, context)
        output = dict(agent_output.output)
        # 透传 trace 元数据（不写库，仅 SSE 用）
        output["_token_usage"] = agent_output.token_usage
        output["_duration_ms"] = agent_output.duration_ms
        output["_model_used"] = agent_output.model_used or ""
        return output
    except Exception as e:
        logger.exception(f"[{workflow_id}] {node_id} harness run failed: {e}")
        await emit_node_event(workflow_id, node_id, "node_error",
                              {"error": str(e), "error_type": type(e).__name__})
        return {**fallback_output, "_error": str(e)}
    finally:
        current_workflow_id.reset(token)


# ----------------------------------------------------------------------
# 智能体信念 + 回溯计数器 辅助函数
# ----------------------------------------------------------------------


def build_belief_dict(node_id: str, output: dict) -> dict:
    """从节点输出提取信念，返回 agent_beliefs 增量 dict。"""
    from app.agents.belief import belief_from_output
    belief = belief_from_output(node_id, output)
    return {node_id: belief.to_dict()}


def build_loop_counter_update(state: WorkflowState, node_id: str) -> dict:
    """检测当前节点是否被回溯到，返回 loop_counters 增量 dict。

    判断逻辑：如果 node_statuses[node_id] 已经是 COMPLETED，
    说明这个节点之前已经执行过，现在是回溯重跑。
    """
    current_status = state.get("node_statuses", {}).get(node_id, "")
    if current_status in (NodeStatus.COMPLETED.value, NodeStatus.PASSED.value):
        current_count = state.get("loop_counters", {}).get(node_id, 0)
        return {node_id: current_count + 1}
    return {}


def read_upstream_belief(state: WorkflowState, upstream_node_id: str) -> dict | None:
    """读取上游节点的信念（回溯带上下文）。

    用法：在节点函数里调用 read_upstream_belief(state, "audit")
    获取 audit 的修改意见/补充请求。
    """
    return state.get("agent_beliefs", {}).get(upstream_node_id)


def safe_get_selected_direction(analyze_output: dict, recommendations: list | None = None) -> int:
    """安全提取 selected_direction 索引（共享函数，去重三节点重复逻辑）。

    analyze / copywrite / image_plan 三个节点都需要从 analyze_output 取
    selected_direction 并做边界检查。统一在此处理。

    Returns:
        合法的索引（0 ~ len(recommendations)-1），默认 0。
    """
    if recommendations is None:
        insights = (analyze_output.get("insights") or {}) if isinstance(analyze_output, dict) else {}
        recommendations = insights.get("recommendations") or []
    rec_count = len(recommendations) if isinstance(recommendations, list) else 0

    raw = (analyze_output.get("selected_direction", 0)
           if isinstance(analyze_output, dict) else 0)
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        idx = 0
    if idx < 0 or idx >= rec_count:
        idx = 0
    return idx