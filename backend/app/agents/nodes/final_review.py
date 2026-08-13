from app.agents.nodes._base import NodeStatus, WorkflowState, _dlog, emit_node_event, logger


async def final_review_node(state: WorkflowState) -> dict:
    """Final review node: 人工审核节点（通过或打回）。

    工作机制：
    - interrupt_before=["final_review"] 让工作流在此节点前暂停
    - 用户通过 POST /api/workflows/{id}/review 提交最终审核结果
    - 审核通过 → submit_review resume，节点读到 status=pending（默认），设为 passed
    - 审核打回 → submit_review 通过 update_state 设 status=rejected，节点读到后保持 rejected
    - 路由函数 route_after_final_review 根据 status 决定下一步：
      passed → publish，rejected → copywrite（重新生成文案）
    """
    workflow_id = state["workflow_id"]
    node_id = "final_review"

    # 读取审核状态（submit_review reject 时通过 update_state 设为 rejected）
    review_status = state.get("node_statuses", {}).get(node_id, "pending")
    is_rejected = review_status == NodeStatus.REJECTED.value

    _dlog(f"[{workflow_id}] ===== final_review_node ENTERED ===== review_status={review_status}, is_rejected={is_rejected}")

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(
        f"[{workflow_id}] {node_id} resumed after human review "
        f"(status={review_status})"
    )

    # 读取 copywrite 输出，透传给 publish
    copywrite_output = state.get("node_outputs", {}).get("copywrite", {})
    image_gen_output = state.get("node_outputs", {}).get("image_gen", {})
    image_review_output = state.get("node_outputs", {}).get("image_review", {})

    # 候选模式下完整套装在 image_review.images_base64，旧模式在 image_gen.images_base64
    final_images = (
        image_review_output.get("images_base64")
        or image_gen_output.get("images_base64")
        or []
    )

    review_data = {
        "title": copywrite_output.get("title", ""),
        "content": copywrite_output.get("content", ""),
        "tags": copywrite_output.get("tags", []),
        "images_base64": final_images,
        "review_status": "rejected" if is_rejected else "passed",
        "feedback": "",
    }

    await emit_node_event(workflow_id, node_id, "node_completed", review_data)

    # rejected 时保持 rejected 状态，路由函数会走回退路径（→ copywrite）
    node_status = (
        NodeStatus.REJECTED.value if is_rejected else NodeStatus.PASSED.value
    )

    logger.info(
        f"[{workflow_id}] {node_id} "
        f"{'rejected (rollback to copywrite)' if is_rejected else 'passed'}: "
        f"title={review_data['title'][:30]}"
    )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: node_status},
        "node_outputs": {node_id: review_data},
    }
