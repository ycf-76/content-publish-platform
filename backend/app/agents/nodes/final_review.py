from app.agents.nodes._base import (
    NodeStatus, WorkflowState, _dlog, emit_node_event, logger,
    build_belief_dict, build_loop_counter_update, read_upstream_belief,
)


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

    # 读取双方信念，做仲裁决策
    audit_belief = read_upstream_belief(state, "audit")
    copywrite_belief = read_upstream_belief(state, "copywrite")
    arbitration = None

    # 检查 audit 是否被跳过（LLM 不可用）
    audit_output = state.get("node_outputs", {}).get("audit", {})
    audit_skipped = audit_output.get("_skipped", False)

    if audit_skipped:
        arbitration = {
            "conflict": False,
            "audit_skipped": True,
            "resolution": "audit_skipped_needs_human_confirm",
        }
        logger.warning(
            f"[{workflow_id}] {node_id} 审核被跳过（LLM 不可用），"
            f"需人工确认后发布"
        )
    elif audit_belief and copywrite_belief:
        audit_verdict = audit_belief.get("verdict", "sufficient")
        cw_verdict = copywrite_belief.get("verdict", "sufficient")
        audit_conf = audit_belief.get("confidence", 1.0)
        cw_conf = copywrite_belief.get("confidence", 1.0)

        # audit 和 copywrite 意见冲突时，final_review 做仲裁
        if audit_verdict in ("needs_revision", "rejected") and cw_verdict == "sufficient":
            arbitration = {
                "conflict": True,
                "audit_verdict": audit_verdict,
                "copywrite_verdict": cw_verdict,
                "audit_confidence": audit_conf,
                "copywrite_confidence": cw_conf,
                "resolution": "audit_wins" if audit_conf > cw_conf else "copywrite_wins",
            }
            logger.info(
                f"[{workflow_id}] {node_id} 信念冲突仲裁: "
                f"audit={audit_verdict}({audit_conf}) vs "
                f"copywrite={cw_verdict}({cw_conf}) → "
                f"{arbitration['resolution']}"
            )
        elif audit_verdict == cw_verdict:
            arbitration = {"conflict": False, "consensus": audit_verdict}
            logger.info(
                f"[{workflow_id}] {node_id} 双方一致: verdict={audit_verdict}"
            )

    final_image_urls = (
        image_review_output.get("image_urls")
        or image_gen_output.get("image_urls")
        or []
    )

    review_data = {
        "title": copywrite_output.get("title", ""),
        "content": copywrite_output.get("content", ""),
        "tags": copywrite_output.get("tags", []),
        "image_urls": final_image_urls,
        "review_status": "rejected" if is_rejected else "passed",
        "feedback": "",
        "arbitration": arbitration,
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
        "agent_beliefs": build_belief_dict(node_id, review_data),
        "loop_counters": build_loop_counter_update(state, node_id),
    }


def _build_belief(node_id: str, output: dict) -> dict:
    """从节点输出提取信念，写入 state.agent_beliefs。"""
    return build_belief_dict(node_id, output)