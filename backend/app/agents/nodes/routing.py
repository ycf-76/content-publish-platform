from app.agents.nodes._base import NodeStatus, WorkflowState, _dlog, logger


def route_after_search(state: WorkflowState) -> str:
    """Route after search: success -> analyze, error/empty -> END.

    关键节点失败终止：search 空结果或异常时直接结束工作流，
    避免后续 analyze/image_gen 节点白跑浪费 LLM + 图片 token。
    """
    search_status = state.get("node_statuses", {}).get("search", "pending")
    if search_status == NodeStatus.ERROR.value:
        return "end"
    return "analyze"


def route_after_image_gen(state: WorkflowState) -> str:
    """Route after image_gen: success -> image_review, error -> END.

    图片生成全失败（欠费/认证失败/限流耗尽）时终止工作流，
    避免后续 image_review/copywrite 节点白跑。
    """
    ig_status = state.get("node_statuses", {}).get("image_gen", "pending")
    if ig_status == NodeStatus.ERROR.value:
        return "end"
    return "image_review"


def route_after_analyze(state: WorkflowState) -> str:
    """Route after quality_check_analyze: 始终继续到 copywrite。

    工作流顺序调整（v2）：copywrite 移到 image_gen 之前，
    让图片生成/卡片渲染能基于最终文案执行，而非选题方向。

    MVP 阶段：quality_check 仅作为建议权，不影响路由。
    """
    return "copywrite"


def route_after_copywrite(state: WorkflowState) -> str:
    """Route after quality_check_copywrite: 始终继续到 image_plan。

    工作流顺序（v3）：copywrite → image_plan → image_gen → image_review
    image_plan 先规划图片类型和模板数据，image_gen 根据规划渲染。

    MVP 阶段：quality_check 仅作为建议权，不影响路由。
    """
    return "image_plan"


def route_after_image_review(state: WorkflowState) -> str:
    """Route after image review: pass -> audit, reject -> image_gen.

    工作流顺序调整（v2）：图片审核通过后进入 audit（而非 copywrite），
    因为 copywrite 已经在 image_gen 之前执行完了。
    """
    review_status = state.get("node_statuses", {}).get("image_review", "pending")
    if review_status == NodeStatus.PASSED.value:
        return "audit"
    return "image_gen"


def route_after_final_review(state: WorkflowState) -> str:
    """Route after final review: pass -> publish, reject -> rollback."""
    review_status = state.get("node_statuses", {}).get("final_review", "pending")
    wf = state.get("workflow_id", "?")
    if review_status == NodeStatus.PASSED.value:
        _dlog(f"[{wf}] route_after_final_review: status={review_status} -> 'publish'")
        return "publish"
    _dlog(f"[{wf}] route_after_final_review: status={review_status} -> 'rollback'")
    return "rollback"


def route_after_audit(state: WorkflowState) -> str:
    """Route after quality_check_audit: 始终继续到 final_review。

    MVP 阶段：quality_check 仅作为建议权，不影响路由。
    软语义 fail 的 suggestion 会写入 DB 并推送给前端，
    用户在 final_review 审核时可参考 suggestion 决定是否通过。
    """
    return "final_review"


async def rollback_to_node(state: WorkflowState, target_node: str) -> dict:
    """Rollback to target node."""
    workflow_id = state["workflow_id"]
    logger.info(f"[{workflow_id}] Rolling back to {target_node}")

    # Reset target node and downstream nodes to pending
    # 工作流顺序（v3）：search → analyze → copywrite → image_plan → image_gen → image_review → audit → final_review → publish
    node_order = ["search", "analyze", "copywrite", "image_plan", "image_gen", "image_review", "audit", "final_review", "publish"]
    target_idx = node_order.index(target_node)

    new_statuses = {}
    for i, node in enumerate(node_order):
        if i >= target_idx:
            new_statuses[node] = NodeStatus.PENDING.value

    return {"node_statuses": new_statuses}
