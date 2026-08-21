from app.agents.nodes._base import NodeStatus, WorkflowState, emit_node_event, logger
from app.agents.nodes.image_plan_planner import ContentPlanner
from app.templates.registry import get_template_registry


async def image_plan_node(state: WorkflowState) -> dict:
    """Plan card content and template for the image editor.

    The heavy content planning logic lives in image_plan_planner.py.
    This node only extracts state, invokes the planner, and assembles output.
    """
    import time

    workflow_id = state["workflow_id"]
    node_id = "image_plan"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(
        workflow_id,
        node_id,
        "node_status_changed",
        {"status": "running"},
    )

    copywrite_output = state.get("node_outputs", {}).get("copywrite", {}) or {}
    title = copywrite_output.get("title", "")
    content = copywrite_output.get("content", "")
    tags = copywrite_output.get("tags", [])
    key_points = copywrite_output.get("key_points", [])
    structured_items = copywrite_output.get("structured_items", []) or []
    topic = state.get("topic", "")
    image_assets = state.get("image_assets") or []
    asset_mode = bool(state.get("asset_mode"))

    analyze_output = state.get("node_outputs", {}).get("analyze", {}) or {}
    analyze_insights = analyze_output.get("insights", {}) or {}
    analyze_recommendations = analyze_insights.get("recommendations") or []
    visual_suggestion = ""
    analyze_content_type = ""
    selected_direction = analyze_output.get("selected_direction", 0)
    try:
        selected_direction = int(selected_direction)
    except (TypeError, ValueError):
        selected_direction = 0
    if selected_direction < 0 or selected_direction >= len(analyze_recommendations):
        selected_direction = 0
    if analyze_recommendations and isinstance(
        analyze_recommendations[selected_direction], dict
    ):
        brief = analyze_recommendations[selected_direction].get("execution_brief") or {}
        if isinstance(brief, dict):
            visual_suggestion = str(brief.get("visual_suggestion", "")).strip()
            analyze_content_type = str(brief.get("content_type", "")).strip()

    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")
    platform = state.get("platform", "xiaohongshu")
    format_name = state.get("format_name") or None
    brand_config: dict | None = None
    try:
        from app.services.esther_factory import factory

        brand_config = await factory.get_brand_config(state.get("user_id", ""))
    except Exception as exc:
        logger.warning(f"[{workflow_id}] {node_id} brand config unavailable: {exc}")

    if asset_mode and image_assets:
        platform_data = get_template_registry().resolve_platform_format(
            platform,
            format_name,
        )
        format_plan = {
            **platform_data,
            "page_count": len(image_assets),
            "pages": [
                {
                    "index": index,
                    "source": "asset",
                    "asset_id": asset.get("asset_id", ""),
                }
                for index, asset in enumerate(image_assets)
            ],
        }
        output = {
            "image_plan": {"plan": [], "skipped": True, "reason": "asset_mode"},
            "content_plan": {"pages": []},
            "format_plan": format_plan,
            "is_asset_mode": True,
            "brand": brand_config,
            "copywrite_passthrough": {
                "title": title,
                "content": content,
                "tags": tags if isinstance(tags, list) else [],
                "key_points": key_points,
            },
            "_model_used": "asset_mode (no LLM)",
            "_duration_ms": int((time.time() - start_time) * 1000),
            "_token_usage": 0,
            "_source": "asset_mode",
        }
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 100,
            "step": "asset_mode",
            "message": f"已使用 {len(image_assets)} 张本地图片",
        })
        await emit_node_event(workflow_id, node_id, "node_completed", output)
        return {
            "current_node": node_id,
            "node_statuses": {node_id: NodeStatus.COMPLETED.value},
            "node_outputs": {node_id: output},
        }

    from app.engine.factory import get_deepseek_llm

    await emit_node_event(
        workflow_id,
        node_id,
        "progress_update",
        {
            "progress": 30,
            "step": "card_draft_planning",
            "message": "LLM 正在规划卡片文案...",
        },
    )

    llm = get_deepseek_llm(temperature=user_temperature, model=user_text_model)
    planner = ContentPlanner()
    card_draft, model_used = await planner.plan(
        topic=topic,
        title=title,
        content=content,
        tags=tags,
        key_points=key_points,
        structured_items=structured_items,
        content_type=analyze_content_type,
        visual_suggestion=visual_suggestion,
        brand=brand_config,
        llm=llm,
    )

    suggested_template_id = card_draft.get(
        "suggested_template",
        get_template_registry().default_template_id(),
    )
    page_count = len(card_draft.get("pages", []))
    format_plan = planner.build_format_plan(
        page_count,
        suggested_template_id,
        platform=platform,
        format_name=format_name,
    )

    content_plan = {"pages": card_draft.get("pages", [])}
    for key in ("suggested_template", "custom_accent", "suggested_decoration", "copywrite_context", "brand"):
        if key in card_draft:
            content_plan[key] = card_draft[key]
    output = {
        "image_plan": {"plan": [], "skipped": True, "reason": "card_editor_mode"},
        "content_plan": content_plan,
        "format_plan": format_plan,
        "copywrite_passthrough": {
            "title": title,
            "content": content,
            "tags": tags if isinstance(tags, list) else [],
            "key_points": key_points,
        },
        "_model_used": model_used,
        "_duration_ms": int((time.time() - start_time) * 1000),
        "_token_usage": 0,
        "_source": "card_editor_mode",
    }

    await emit_node_event(workflow_id, node_id, "node_completed", output)
    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }