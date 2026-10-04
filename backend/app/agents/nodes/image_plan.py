from app.agents.nodes._base import (
    NodeStatus, WorkflowState, emit_node_event, logger,
    build_belief_dict, build_loop_counter_update, read_upstream_belief,
    safe_get_selected_direction,
)
from app.agents.nodes.image_plan_planner import ContentPlanner
try:
    from app.templates.registry import get_template_registry
except ImportError:
    def get_template_registry():
        return None


def _build_creative_artifact(
    *,
    card_draft: dict,
    title: str,
    topic: str,
    content_type: str,
    visual_suggestion: str,
    workflow_id: str,
    state: WorkflowState,
) -> dict | None:
    """生成统一创作对象，供后续节点/前端共用同一份上下文。"""
    try:
        from app.services.creative_artifact import build_artifact, save_artifact

        analysis_payload: dict = {}
        analyze_output = state.get("node_outputs", {}).get("analyze", {}) or {}
        insights = analyze_output.get("insights", {}) or {}
        if insights:
            analysis_payload = {
                "confidence": float(insights.get("confidence") or 0),
                "keep_patterns": [
                    str(p)[:80]
                    for p in (insights.get("recommendations") or [])
                    if isinstance(p, dict) and p.get("topic_direction")
                ][:3],
                "evidence": insights.get("key_findings", [])[:3]
                if isinstance(insights.get("key_findings"), list)
                else [],
            }
        if visual_suggestion:
            analysis_payload.setdefault("keep_patterns", []).append(visual_suggestion[:80])

        brief_payload = {
            "topic": topic,
            "title": title,
            "visual_direction": content_type,
            "template_id": card_draft.get("suggested_template", ""),
        }

        artifact = build_artifact(
            card_draft=card_draft,
            brief=brief_payload,
            analysis=analysis_payload,
            source={"workflow_id": workflow_id},
        )
        save_artifact(artifact)  # noqa: F841 - persisted by service
        return {
            "artifact_id": artifact.artifact_id,
            "page_roles": [p.role for p in artifact.storyboard],
            "storyboard": [p.model_dump() for p in artifact.storyboard],
        }
    except Exception as exc:
        logger.warning(f"[image_plan] creative artifact build failed: {exc}")
        return None


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

    # 读取上游 agent 信念（回溯带上下文）
    # copywrite 的信念影响图片风格选择
    copywrite_belief = read_upstream_belief(state, "copywrite")
    style_hint = None
    if copywrite_belief:
        cw_confidence = copywrite_belief.get("confidence", 1.0)
        cw_verdict = copywrite_belief.get("verdict", "sufficient")
        # copywrite 信心低时，图片走保守风格
        if cw_confidence < 0.6:
            style_hint = "conservative"
            logger.info(
                f"[{workflow_id}] {node_id} copywrite 信心低({cw_confidence})，"
                f"图片走保守风格"
            )
        # copywrite 有折中方案时，图片风格对齐折中方向
        compromise = copywrite_belief.get("compromise")
        if compromise and isinstance(compromise, dict):
            style_hint = compromise.get("style_hint", style_hint)
            logger.info(
                f"[{workflow_id}] {node_id} copywrite 折中方案影响图片风格: "
                f"style_hint={style_hint}"
            )
    topic = state.get("topic", "")
    image_assets = state.get("image_assets") or []
    asset_mode = bool(state.get("asset_mode"))

    analyze_output = state.get("node_outputs", {}).get("analyze", {}) or {}
    analyze_insights = analyze_output.get("insights", {}) or {}
    analyze_recommendations = analyze_insights.get("recommendations") or []
    visual_suggestion = ""
    analyze_content_type = ""
    selected_direction = safe_get_selected_direction(analyze_output, analyze_recommendations)
    if analyze_recommendations and isinstance(
        analyze_recommendations[selected_direction], dict
    ):
        brief = analyze_recommendations[selected_direction].get("execution_brief") or {}
        if isinstance(brief, dict):
            visual_suggestion = str(brief.get("visual_suggestion", "")).strip()
            analyze_content_type = str(brief.get("content_type", "")).strip()

    # D18: 画像视觉风格 + 领域注入图片规划（按需注入：只取视觉相关字段）
    user_profile = state.get("user_profile") or {}
    if isinstance(user_profile, dict):
        profile_visual = str(user_profile.get("visual_style") or "").strip()
        profile_domain = str(user_profile.get("primary_domain") or "").strip()
        if profile_visual or profile_domain:
            hints = [f"创作者视觉风格: {profile_visual}"] if profile_visual else []
            if profile_domain:
                hints.append(f"创作者领域: {profile_domain}")
            visual_suggestion = (
                (visual_suggestion + " " if visual_suggestion else "") + "；".join(hints)
            ).strip()

    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")
    platform = state.get("platform", "xiaohongshu")
    format_name = state.get("format_name") or None
    brand_config: dict | None = None

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
            "agent_beliefs": build_belief_dict(node_id, output),
            "loop_counters": build_loop_counter_update(state, node_id),
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
    try:
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
            style_hint=style_hint,
            llm=llm,
        )
    except Exception as plan_err:
        err_str = str(plan_err)
        logger.exception(f"[{workflow_id}] {node_id} ContentPlanner.plan failed: {plan_err}")
        # 检测 DeepSeek 余额不足（402）→ 推送前端通知
        if "402" in err_str or "Insufficient Balance" in err_str or "余额" in err_str:
            from app.services.sse_bus import sse_bus
            await sse_bus.publish(workflow_id, "model_arrearage", {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "provider": "deepseek",
                "message": "DeepSeek 余额不足，图片规划降级为默认模板",
                "action_url": "https://platform.deepseek.com/usage",
                "action_text": "前往 DeepSeek 控制台充值",
            })
        # 降级：用默认模板规划
        card_draft = {
            "pages": [{"index": 0, "content": {"title": title, "body": content[:200]}}],
            "suggested_template": get_template_registry().default_template_id(),
        }
        model_used = "fallback (plan error)"

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

    creative_artifact = _build_creative_artifact(
        card_draft=card_draft,
        title=title,
        topic=topic,
        content_type=analyze_content_type,
        visual_suggestion=visual_suggestion,
        workflow_id=workflow_id,
        state=state,
    )
    if creative_artifact:
        content_plan["creative_artifact"] = creative_artifact

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
        "agent_beliefs": build_belief_dict(node_id, output),
        "loop_counters": build_loop_counter_update(state, node_id),
    }


def _build_belief(node_id: str, output: dict) -> dict:
    """从节点输出提取信念，写入 state.agent_beliefs。"""
    return build_belief_dict(node_id, output)