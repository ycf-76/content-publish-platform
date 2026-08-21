from app.agents.nodes._base import NodeStatus, WorkflowState, emit_node_event, logger
from app.services.sse_bus import sse_bus


async def copywrite_node(state: WorkflowState) -> dict:
    """Copywrite node: 基于分析洞察 + 图片描述生成小红书文案。

    流程：
    1. 从 analyze 节点取 insights（patterns, recommendations）
    2. 从 image_gen 节点取 image_details（图片描述）+ style
    3. 从 image_review 节点取审核反馈（如有）
    4. 用 LLM 生成 title + content + tags
    5. LLM 不可用时降级为模板生成

    成本控制：
    - 直接调 DeepSeek（不走完整 harness，减少抽象层开销）
    - max_tokens 由 DeepSeekAdapter 控制（默认 1500）
    - 单次调用约 0.012 元
    """
    import time

    workflow_id = state["workflow_id"]
    node_id = "copywrite"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    topic = state.get("topic", "")
    search_keyword = (state.get("search_keyword") or topic).strip()
    creative_brief = (state.get("creative_brief") or "").strip()
    # 文案主题以用户创作要求为主；旧工作流无 brief 时保持原 topic。
    copywrite_topic = creative_brief or topic

    # 用户在右侧工作区选择的模型/温度/文风配置
    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")
    user_writing_style = model_settings.get("writing_style", "")
    # 用户可直接指定 copywrite skill name（优先级高于 writing_style 中文名）
    copywrite_skill_name = model_settings.get("copywrite_skill")
    # 风格开关（来自右侧配置中心）：
    # - content_length: 用户期望的文案正文字数（100-500），覆盖 prompt 硬编码长度规则
    # - auto_emoji: False 时指示 LLM 不使用 emoji，覆盖风格 skill 默认
    # - auto_tags: False 时指示 LLM 不生成标签，返回空 tags 数组
    content_length = model_settings.get("content_length")
    auto_emoji = model_settings.get("auto_emoji", True)
    auto_tags = model_settings.get("auto_tags", True)

    # 选题池参考素材（从选题池"发起新工作流"时携带，注入 LLM prompt）
    reference = state.get("reference", {}) or {}

    # 用户级长期记忆（跨工作流，工作流启动时从 AgentMemory 加载）
    # 注入 LLM prompt 供 copywrite 参考历史选题/文案/偏好文风
    user_memory = state.get("user_memory", {}) or {}

    # ===== Step 1: 收集上游数据 =====
    node_outputs = state.get("node_outputs", {})
    analyze_output = node_outputs.get("analyze", {})
    # 修 bug：patterns 是 analyze_output 的顶层字段，不在 insights 里
    # 之前只取 insights 导致 Layer2 的标题钩子/内容结构/情绪触发点完全丢失
    patterns = analyze_output.get("patterns", {}) or {}
    insights = analyze_output.get("insights", {}) or {}

    # 提取 execution_brief：优先使用用户在 analyze 后选择的推荐方向。
    execution_brief = {}
    recommendations = insights.get("recommendations") or []
    selected_direction = analyze_output.get("selected_direction", 0)
    try:
        selected_direction = int(selected_direction)
    except (TypeError, ValueError):
        selected_direction = 0
    if selected_direction < 0 or selected_direction >= len(recommendations):
        selected_direction = 0
    selected_recommendation = {}
    if recommendations and isinstance(recommendations[selected_direction], dict):
        selected_recommendation = recommendations[selected_direction]
        brief = selected_recommendation.get("execution_brief")
        if isinstance(brief, dict):
            execution_brief = dict(brief)
    direction_note = str(analyze_output.get("direction_note") or "").strip()
    if creative_brief:
        execution_brief["user_creative_brief"] = creative_brief
    if selected_recommendation.get("topic_direction"):
        execution_brief["selected_direction"] = selected_recommendation["topic_direction"]
    if direction_note:
        execution_brief["direction_note"] = direction_note

    image_gen_output = node_outputs.get("image_gen", {})
    image_details = image_gen_output.get("image_details", [])
    image_style = image_gen_output.get("style", "")

    image_review_output = node_outputs.get("image_review", {})
    review_feedback = image_review_output.get("feedback", "")

    logger.info(
        f"[{workflow_id}] {node_id} upstream: "
        f"patterns={'yes' if patterns else 'no'}, "
        f"insights={'yes' if insights else 'no'}, "
        f"execution_brief={'yes' if execution_brief else 'no'}, "
        f"selected_direction={selected_direction}, "
        f"creative_brief={'yes' if creative_brief else 'no'}, "
        f"search_keyword={search_keyword or '(none)'}, "
        f"image_details={len(image_details)}, "
        f"review_feedback={'yes' if review_feedback else 'no'}, "
        f"writing_style={user_writing_style or '(default)'}, "
        f"temperature={user_temperature if user_temperature is not None else '(default)'}, "
        f"reference={'yes' if reference else 'no'}"
    )

    # ===== Step 2: 调 LLM 生成文案 =====
    await emit_node_event(workflow_id, node_id, "progress_update", {
        "progress": 30,
        "step": "copywriting",
        "message": "LLM 生成小红书文案中...",
    })

    from app.engine.factory import get_deepseek_llm
    from app.tools.registry import get_skill_class
    # 触发内置 Skill 注册（import 即注册）
    import app.tools.copywrite_builder  # noqa: F401
    from app.tools.copywrite_builder import (
        CopywriteSkillBase,
        LivelyGirlCopywriteSkill,
        _WRITING_STYLE_TO_SKILL_NAME,
    )

    # 使用用户配置的温度+模型生成文案
    llm = get_deepseek_llm(temperature=user_temperature, model=user_text_model)

    # 通过 registry 加载 copywrite Skill（支持第三方插件）
    # 优先用 copywrite_skill，其次用 writing_style 中文名映射，最后用默认 lively_girl
    if not copywrite_skill_name and user_writing_style:
        copywrite_skill_name = _WRITING_STYLE_TO_SKILL_NAME.get(
            user_writing_style.strip(), "lively_girl"
        )
    copywrite_skill_cls = get_skill_class(
        "copywrite", copywrite_skill_name or "lively_girl"
    )
    if copywrite_skill_cls is None:
        logger.warning(
            f"[{workflow_id}] copywrite skill '{copywrite_skill_name}' not found, "
            f"falling back to LivelyGirlCopywriteSkill"
        )
        copywrite_skill_cls = LivelyGirlCopywriteSkill
    copywrite_skill = copywrite_skill_cls()
    logger.info(
        f"[{workflow_id}] copywrite using skill: {copywrite_skill.name} "
        f"({copywrite_skill.__class__.__name__})"
    )

    # 检测 DeepSeek 余额不足
    # 使用流式输出：LLM streaming → SSE stream_chunk → 前端逐字显示
    try:
        result = await copywrite_skill.execute_streaming({
            "llm": llm,
            "topic": copywrite_topic,
            "insights": insights,
            "patterns": patterns,
            "execution_brief": execution_brief,
            "image_details": image_details,
            "image_style": image_style,
            "reference": reference,
            "user_memory": user_memory,
            "content_length": content_length,
            "auto_emoji": auto_emoji,
            "auto_tags": auto_tags,
            "workflow_id": workflow_id,
            "node_id": node_id,
        })
    except Exception as e:
        err_str = str(e)
        logger.exception(f"[{workflow_id}] {node_id} copywrite failed: {e}")

        # 检测 DeepSeek 余额不足（402）→ 推送前端通知
        if "402" in err_str or "Insufficient Balance" in err_str or "余额" in err_str:
            await sse_bus.publish(workflow_id, "model_arrearage", {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "provider": "deepseek",
                "message": "DeepSeek 余额不足，文案生成降级为模板模式",
                "action_url": "https://platform.deepseek.com/usage",
                "action_text": "前往 DeepSeek 控制台充值",
            })

        # 降级为模板生成
        result = copywrite_skill.fallback(copywrite_topic, insights, image_details)

    # ===== Step 3: 组装输出 =====
    output = {
        "title": result.get("title", ""),
        "content": result.get("content", ""),
        "tags": result.get("tags", []),
        "prompt_source": result.get("_source", "unknown"),
        "_model_used": "deepseek-chat" if llm else "none (fallback)",
        "_duration_ms": int((time.time() - start_time) * 1000),
        "_token_usage": {"prompt": 0, "completion": 0, "total": 0},
    }

    # 如果有审核反馈，附加到输出供前端展示
    if review_feedback:
        output["review_feedback"] = review_feedback

    elapsed = int((time.time() - start_time) * 1000)
    logger.info(
        f"[{workflow_id}] {node_id} completed: "
        f"source={output['prompt_source']}, "
        f"title={output['title'][:30]}, "
        f"content_len={len(output['content'])}, "
        f"tags={len(output['tags'])}, "
        f"elapsed={elapsed}ms"
    )

    await emit_node_event(workflow_id, node_id, "node_completed", output)

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }
