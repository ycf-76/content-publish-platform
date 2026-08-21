from app.agents.nodes._base import NodeStatus, WorkflowState, _dlog, emit_node_event, logger


async def publish_node(state: WorkflowState) -> dict:
    """Publish node: LoopExecutor + XhsPublishSkill via MCP."""
    workflow_id = state["workflow_id"]
    node_id = "publish"

    _dlog(f"[{workflow_id}] ===== publish_node ENTERED =====")
    _dlog(f"[{workflow_id}] publish_node state keys: {list(state.keys())}")
    _dlog(f"[{workflow_id}] publish_node node_statuses: {state.get('node_statuses', {})}")
    _dlog(f"[{workflow_id}] publish_node node_outputs keys: {list(state.get('node_outputs', {}).keys())}")

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    # 从 upstream 节点产物里取要发布的字段
    final_review = state.get("node_outputs", {}).get("final_review", {})
    copywrite = state.get("node_outputs", {}).get("copywrite", {})
    image_gen = state.get("node_outputs", {}).get("image_gen", {})
    image_review = state.get("node_outputs", {}).get("image_review", {})
    topic = state.get("topic", "")
    harness_input = {
        "title": (
            final_review.get("title")
            or copywrite.get("title")
            or (topic if topic else "")
        ),
        "content": (
            final_review.get("content")
            or copywrite.get("content")
            or ""
        ),
        # 候选模式下 image_gen.images_base64 为空，完整套装在 image_review.images_base64
        "images_base64": (
            final_review.get("images_base64")
            or image_review.get("images_base64")
            or image_gen.get("images_base64")
            or []
        ),
        "account_id": state.get("account_id", ""),
    }

    _dlog(f"[{workflow_id}] publish_node harness_input: title={harness_input['title'][:30]!r}, "
          f"content_len={len(harness_input['content'])}, images={len(harness_input['images_base64'])}")

    # 参数校验：title 和 content 不能为空
    if not harness_input["title"] or not harness_input["content"]:
        logger.warning(
            f"[{workflow_id}] {node_id} missing title or content, skip publish"
        )
        _dlog(f"[{workflow_id}] publish_node SKIP: missing title or content")
        output = {
            "post_id": "",
            "status": "failed",
            "message": "发布失败：缺少标题或正文（请检查 copywrite / final_review 节点输出）",
        }
    else:
        # 发布进度提示：发布流程涉及 Playwright 操作发布页，耗时 15-30s
        img_count = len(harness_input["images_base64"])
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 10,
            "step": "publish_starting",
            "message": f"正在连接小红书发布页（{img_count} 张图片）...",
        })

        # 直接调用 XhsPublishSkill，不走 LLM Loop
        # 红线：发布是确定性动作（调 MCP → Worker Playwright），不需要 LLM 推理
        # LLM Loop 会导致 LLM 误判参数为占位符，拒绝调用工具
        from app.agents.skills.xhs_publish import XhsPublishSkill

        skill = XhsPublishSkill()
        _dlog(f"[{workflow_id}] publish_node calling XhsPublishSkill.execute()...")
        try:
            output = await skill.execute(harness_input)
            _dlog(f"[{workflow_id}] publish_node skill result: status={output.get('status')}, "
                  f"message={output.get('message', '')[:100]}")
        except Exception as e:
            logger.exception(f"[{workflow_id}] {node_id} publish skill failed: {e}")
            _dlog(f"[{workflow_id}] publish_node skill EXCEPTION: {type(e).__name__}: {e}")
            await emit_node_event(workflow_id, node_id, "node_error",
                                  {"error": str(e), "error_type": type(e).__name__})
            output = {
                "post_id": "",
                "status": "failed",
                "message": f"发布异常: {e}",
            }

    _dlog(f"[{workflow_id}] publish_node FINAL output: {output}")

    # 半自动模式：worker 填好内容但不点击，status=awaiting_manual
    # 节点保持 RUNNING，等前端轮询 /api/workflows/{id}/publish/check 确认结果
    if output.get("status") == "awaiting_manual":
        logger.info(f"[{workflow_id}] {node_id} awaiting manual publish click")
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 90,
            "step": "awaiting_manual_publish",
            "message": output.get("message", "内容已填好，请在浏览器窗口手动点击「发布」按钮"),
        })
        return {
            "current_node": node_id,
            # 不标 COMPLETED，保持 RUNNING，等 check API 更新
            "node_statuses": {node_id: NodeStatus.RUNNING.value},
            "node_outputs": {node_id: output},
        }

    await emit_node_event(workflow_id, node_id, "node_completed", output)

    # 发布成功时记录用户级长期记忆（publish_history）
    # 失败不阻塞工作流，仅记日志
    if output.get("status") == "success" or output.get("post_id"):
        try:
            from app.services import agent_memory
            await agent_memory.record_publish(
                user_id=state.get("user_id", ""),
                workflow_id=workflow_id,
                topic=state.get("topic", ""),
                title=harness_input.get("title", ""),
                post_id=str(output.get("post_id", "")),
            )
        except Exception as mem_err:
            logger.warning(
                f"[{workflow_id}] record_publish failed: {mem_err}"
            )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }