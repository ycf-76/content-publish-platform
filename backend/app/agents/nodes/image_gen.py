from app.agents.nodes._base import NodeStatus, WorkflowState, _dlog, emit_node_event, logger
from app.services.sse_bus import sse_bus


async def image_gen_node(state: WorkflowState) -> dict:
    """Image generation node: 接收前端卡片编辑器注入的图片，校验并打包到 image_review。

    工作机制：
    - image_plan 完成后，工作流在 image_gen 前 interrupt 暂停
    - 前端卡片编辑器加载 card_draft，用户调整后 html2canvas 出图
    - 前端调 inject-card-images 接口，把图片 base64 + plan_context 写入 state
    - inject 接口 resume 工作流，image_gen_node 执行
    - 本节点读取 image_plan 的规划 + inject 的图片 + plan_context
    - 校验图片数量、对比模板变更，打包完整上下文给下游

    红线：
    - 本节点不再主动渲染（不调 Playwright，不调通义万相）
    - 图片完全由前端卡片编辑器生成
    - 本节点做校验和打包，不做生成
    """
    import time

    workflow_id = state["workflow_id"]
    node_id = "image_gen"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    # 读取 image_plan 的规划（建立显式数据依赖）
    plan_output = state.get("node_outputs", {}).get("image_plan", {}) or {}
    card_draft = plan_output.get("card_draft", {})
    original_template = card_draft.get("suggested_template", "")
    original_accent = card_draft.get("custom_accent", "")
    original_page_count = len(card_draft.get("pages", []))

    # 读取 inject 的图片 + plan_context
    image_gen_output = state.get("node_outputs", {}).get("image_gen", {}) or {}
    injected_images = image_gen_output.get("images_base64", [])
    plan_context = image_gen_output.get("plan_context", {}) or {}

    if injected_images:
        # 校验：图片数量是否和规划一致
        final_template = plan_context.get("template", "")
        final_accent = plan_context.get("accent", "")
        final_page_count = plan_context.get("page_count", 0)
        final_page_types = plan_context.get("page_types", [])
        actual_count = len(injected_images)
        count_match = (final_page_count == 0) or (actual_count == final_page_count)
        template_changed = bool(original_template and final_template and original_template != final_template)

        logger.info(
            f"[{workflow_id}] {node_id} received {actual_count} injected images, "
            f"template={final_template}, accent={final_accent}, "
            f"count_match={count_match}, template_changed={template_changed}"
        )

        output = {
            "images_base64": injected_images,
            "image_count": actual_count,
            "image_details": image_gen_output.get("image_details", []),
            "image_prompts": [],
            "style": image_gen_output.get("style", "卡片编辑器"),
            "is_candidate_mode": False,
            "is_blueprint_mode": False,
            "is_card_editor_mode": True,
            "plan_context": plan_context,
            "card_draft_summary": {
                "original_template": original_template,
                "final_template": final_template,
                "original_accent": original_accent,
                "final_accent": final_accent,
                "original_page_count": original_page_count,
                "final_page_count": final_page_count,
                "template_changed": template_changed,
                "page_types": final_page_types,
            },
            "validation": {
                "count_match": count_match,
                "expected_count": final_page_count or original_page_count,
                "actual_count": actual_count,
            },
            "_model_used": "card_editor_inject",
            "_duration_ms": int((time.time() - start_time) * 1000),
            "_token_usage": {"prompt": 0, "completion": 0, "total": 0},
            "_source": "card_editor_inject",
        }
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 100,
            "current_node": node_id,
            "message": f"卡片编辑器出图完成（{actual_count} 张）",
        })
        await emit_node_event(workflow_id, node_id, "node_completed", output)
        return {
            "current_node": node_id,
            "node_statuses": {node_id: NodeStatus.COMPLETED.value},
            "node_outputs": {node_id: output},
        }

    # 没有注入图片：报错（正常不应走到这里，因为 interrupt 在 image_gen 前）
    err_msg = "image_gen 未收到前端注入的图片，请确认卡片编辑器已生成图片"
    logger.error(f"[{workflow_id}] {node_id} {err_msg}")
    await sse_bus.publish(workflow_id, "workflow_error", {
        "workflow_id": workflow_id,
        "node_id": node_id,
        "error_type": "no_injected_images",
        "message": err_msg,
        "suggestion": "在工作区卡片编辑器中调整文案后，点击「生成图片」按钮",
    })
    output = {
        "images_base64": [],
        "image_count": 0,
        "image_details": [],
        "image_prompts": [],
        "style": "",
        "is_card_editor_mode": True,
        "_model_used": "card_editor_inject",
        "_error": err_msg,
        "_duration_ms": int((time.time() - start_time) * 1000),
        "_source": "no_injected_images",
    }
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "error"})
    await emit_node_event(workflow_id, node_id, "node_error", output)
    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.ERROR.value},
        "node_outputs": {node_id: output},
    }
