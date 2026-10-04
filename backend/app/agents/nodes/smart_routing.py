"""Smart Routing — 三层路由取代硬编码路由。

Layer 1: 确定性规则（保留原 routing.py 的逻辑，0 LLM 成本）
Layer 2: 信心路由（基于 AgentBelief，0 LLM 成本）
Layer 3: 协商路由（仅在 agent 间冲突时，1次 LLM，暂未实现）

回溯保护：同一节点最多回溯 _MAX_LOOP_COUNT 次，防止死循环。
回溯带上下文：节点读 agent_beliefs 获取上游的修改意见/补充请求。
"""

from __future__ import annotations

import logging

from app.agents.belief import AgentBelief, Confidence, belief_from_output
from app.agents.nodes._base import NodeStatus, WorkflowState, _dlog, logger

_MAX_LOOP_COUNTS = {
    "search": 4,
    "analyze": 3,
    "copywrite": 2,
    "image_gen": 2,
}

_DEFAULT_MAX_LOOP = 3


def _max_loops_for(target: str) -> int:
    return _MAX_LOOP_COUNTS.get(target, _DEFAULT_MAX_LOOP)


def _loop_count(state: WorkflowState, target: str) -> int:
    """统计某个节点被回溯访问的次数。"""
    return state.get("loop_counters", {}).get(target, 0)


def _increment_loop(state: WorkflowState, target: str) -> dict:
    """返回 loop_counters 的增量（用于节点 return dict）。"""
    current = _loop_count(state, target)
    return {"loop_counters": {target: current + 1}}


def _read_belief(state: WorkflowState, node_id: str) -> AgentBelief:
    """从 state 读已存信念，fallback 到从 output 重算（兼容旧 checkpoint）。"""
    belief_dict = state.get("agent_beliefs", {}).get(node_id)
    if belief_dict and isinstance(belief_dict, dict):
        try:
            return AgentBelief(**belief_dict)
        except Exception:
            pass
    output = state.get("node_outputs", {}).get(node_id, {})
    return belief_from_output(node_id, output)


def route_after_search(state: WorkflowState) -> str:
    """Layer 1: search 异常 → end，否则 → analyze（让 analyze 判断数据够不够）。

    注意：search 信心不足不直接 end，交给 analyze 判断。
    analyze 信心不足时会回溯到 search 补数据。
    """
    search_status = state.get("node_statuses", {}).get("search", "pending")
    if search_status == NodeStatus.ERROR.value:
        return "end"

    output = state.get("node_outputs", {}).get("search", {})
    if not output:
        return "end"

    return "analyze"


def route_after_analyze(state: WorkflowState) -> str:
    """Layer 2: analyze 根据自身信心决定走向。

    - 信心不足 → 回 search 补数据（带更精确的关键词）
    - 信心充足 → 继续 copywrite
    """
    belief = _read_belief(state, "analyze")
    wf = state.get("workflow_id", "?")

    if belief.verdict == "insufficient" and belief.request_to == "search":
        loop = _loop_count(state, "search")
        max_loops = _max_loops_for("search")
        if loop < max_loops:
            logger.info(
                f"[{wf}] [smart_routing] analyze 信心不足({belief.confidence:.1f})，"
                f"回 search 补数据(loop={loop+1}/{max_loops}): {belief.reasoning}"
            )
            return "search"
        logger.warning(
            f"[{wf}] [smart_routing] search 回溯次数用尽({loop})，强行继续到 copywrite"
        )

    return "copywrite"


def route_after_copywrite(state: WorkflowState) -> str:
    """Layer 2: copywrite 根据自身信心决定走向。

    - 信心不足 → 回 analyze 换方向
    - 信心充足 → 继续 image_plan
    """
    belief = _read_belief(state, "copywrite")
    wf = state.get("workflow_id", "?")

    if belief.verdict == "insufficient" and belief.request_to == "analyze":
        loop = _loop_count(state, "analyze")
        max_loops = _max_loops_for("analyze")
        if loop < max_loops:
            logger.info(
                f"[{wf}] [smart_routing] copywrite 信心不足，"
                f"回 analyze 换方向(loop={loop+1}/{max_loops}): {belief.reasoning}"
            )
            return "analyze"
        logger.warning(
            f"[{wf}] [smart_routing] analyze 回溯次数用尽({loop})，强行继续到 image_plan"
        )

    return "image_plan"


def route_after_image_gen(state: WorkflowState) -> str:
    """Layer 1: image_gen 失败 → 回退 image_plan 重新规划，否则 → image_review。

    用户可能只是忘了 inject 图片，回退到 image_plan 比终止工作流更友好。
    """
    ig_status = state.get("node_statuses", {}).get("image_gen", "pending")
    if ig_status == NodeStatus.ERROR.value:
        return "image_plan"
    return "image_review"


def route_after_image_review(state: WorkflowState) -> str:
    """图片审核：通过 → audit，拒绝 → 重做 image_gen。"""
    review_status = state.get("node_statuses", {}).get("image_review", "pending")
    if review_status == NodeStatus.PASSED.value:
        return "audit"
    return "image_gen"


def route_after_audit(state: WorkflowState) -> str:
    """Layer 2+3: audit 是关键协商点。

    - 通过 → final_review
    - 需要修改（有 compromise）→ 回 copywrite 带修改意见
    - 坚决拒绝 → 检查 copywrite 信念，冲突则走 final_review 仲裁
    """
    belief = _read_belief(state, "audit")
    wf = state.get("workflow_id", "?")

    if belief.verdict == "sufficient":
        return "final_review"

    if belief.verdict == "needs_revision" and belief.compromise:
        logger.info(
            f"[{wf}] [smart_routing] audit 建议修改，回 copywrite 带修改意见: "
            f"{belief.reasoning}"
        )
        return "copywrite"

    if belief.verdict == "rejected":
        cw_belief = _read_belief(state, "copywrite")

        if cw_belief.verdict == "sufficient" and cw_belief.confidence >= Confidence.HIGH.value:
            logger.info(
                f"[{wf}] [smart_routing] audit vs copywrite 冲突！"
                f"audit={belief.verdict} copywrite={cw_belief.verdict}，"
                f"走 final_review 仲裁"
            )
            return "final_review"

        logger.info(
            f"[{wf}] [smart_routing] audit 拒绝，copywrite 也承认有问题，"
            f"回 copywrite 修改: {belief.reasoning}"
        )
        return "copywrite"

    return "final_review"


def route_after_final_review(state: WorkflowState) -> str:
    """final_review: 通过 → publish，不通过 → 回溯到 copywrite。

    红线：rollback 目标硬编码为 copywrite（final_review 打回几乎总是文案问题），
    不从 output 读取（防止 LLM 填充非预期值导致路由到错误节点）。
    """
    review_status = state.get("node_statuses", {}).get("final_review", "pending")
    wf = state.get("workflow_id", "?")

    if review_status == NodeStatus.PASSED.value:
        _dlog(f"[{wf}] route_after_final_review: status={review_status} -> 'publish'")
        return "publish"

    rollback_target = "copywrite"
    loop = _loop_count(state, rollback_target)
    max_loops = _max_loops_for(rollback_target)

    if loop < max_loops:
        _dlog(
            f"[{wf}] route_after_final_review: rollback to '{rollback_target}' "
            f"(loop={loop+1}/{max_loops})"
        )
        return rollback_target

    _dlog(
        f"[{wf}] route_after_final_review: rollback target '{rollback_target}' "
        f"loop exhausted({loop}), forcing publish"
    )
    # 回溯次数用尽，发 SSE 警告
    try:
        from app.services.sse_bus import sse_bus
        import asyncio
        asyncio.get_event_loop().create_task(
            sse_bus.publish(wf, "workflow_warning", {
                "workflow_id": wf,
                "message": "回溯次数用尽，内容可能未完全优化，即将发布",
            })
        )
    except Exception:
        pass
    return "publish"