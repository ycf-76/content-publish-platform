from app.agents.nodes._base import (
    NodeStatus, WorkflowState, _dlog, emit_node_event, logger,
    build_belief_dict, build_loop_counter_update,
)


async def image_review_node(state: WorkflowState) -> dict:
    """Image review node: 人工审核节点（通过/打回 blueprint 渲染结果）。

    工作机制：
    - interrupt_before=["image_review"] 让工作流在此节点前暂停
    - 用户通过 POST /api/workflows/{id}/review 提交审核结果
    - blueprint 模式：image_gen 已渲染 4 张卡，本节点只做通过/打回判定
    - 打回时回退到 image_gen（重新生成 blueprint 并渲染）

    路由：
    - passed → audit
    - rejected → image_gen（重新生成）
    """
    workflow_id = state["workflow_id"]
    node_id = "image_review"

    # 读取审核状态（submit_review reject 时通过 update_state 设为 rejected）
    review_status = state.get("node_statuses", {}).get(node_id, "pending")
    is_rejected = review_status == NodeStatus.REJECTED.value

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(
        f"[{workflow_id}] {node_id} resumed after human review "
        f"(status={review_status})"
    )

    # 读取 image_gen 输出
    image_gen_output = state.get("node_outputs", {}).get("image_gen", {})
    image_urls = image_gen_output.get("image_urls", [])
    image_details = image_gen_output.get("image_details", [])
    image_prompts = image_gen_output.get("image_prompts", [])
    style = image_gen_output.get("style", "")
    image_count = image_gen_output.get("image_count", len(image_urls))
    plan_context = image_gen_output.get("plan_context", {}) or {}
    card_draft_summary = image_gen_output.get("card_draft_summary", {}) or {}
    validation = image_gen_output.get("validation", {}) or {}

    _dlog(
        f"[{workflow_id}] {node_id} diagnose: "
        f"is_rejected={is_rejected}, "
        f"is_blueprint_mode={image_gen_output.get('is_blueprint_mode', False)}, "
        f"image_count={image_count}, "
        f"image_urls={len(image_urls)}, "
        f"review_status={review_status}, "
        f"template={plan_context.get('template', '')}, "
        f"count_match={validation.get('count_match', 'N/A')}"
    )

    # 读取用户提交的审核反馈（submit_review 接口通过 update_state 写入）
    user_feedback = state.get("review_feedback", "")
    if not user_feedback:
        user_feedback = state.get("node_outputs", {}).get(node_id, {}).get("feedback", "")

    # 打包审核数据（供后续节点使用）
    review_data = {
        "image_count": image_count,
        "style": style,
        "image_details": image_details,
        "image_prompts": image_prompts,
        "prompt_source": image_gen_output.get("prompt_source", "blueprint"),
        "review_status": "rejected" if is_rejected else "passed",
        "feedback": user_feedback,
        "selected_indices": list(range(image_count)),
        "is_blueprint_mode": image_gen_output.get("is_blueprint_mode", False),
        "blueprint": image_gen_output.get("blueprint"),
        "image_urls": image_urls,
        "plan_context": plan_context,
        "card_draft_summary": card_draft_summary,
        "validation": validation,
    }

    await emit_node_event(workflow_id, node_id, "node_completed", review_data)

    # rejected 时保持 rejected 状态，路由函数会走回退路径（→ image_gen）
    node_status = (
        NodeStatus.REJECTED.value if is_rejected else NodeStatus.PASSED.value
    )

    logger.info(
        f"[{workflow_id}] {node_id} "
        f"{'rejected (rollback to image_gen)' if is_rejected else 'passed'}: "
        f"image_count={image_count}, style={style[:40]}"
    )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: node_status},
        "node_outputs": {node_id: review_data},
        "agent_beliefs": build_belief_dict(node_id, review_data),
        "loop_counters": build_loop_counter_update(state, node_id),
    }


def _build_belief(node_id: str, output: dict) -> dict:
    """从节点输出提取信念，写入 state.agent_beliefs。"""
    return build_belief_dict(node_id, output)