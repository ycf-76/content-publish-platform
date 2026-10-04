from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agents.nodes._base import (
    NodeStatus, WorkflowState, emit_node_event, logger,
    build_belief_dict, build_loop_counter_update, read_upstream_belief,
    safe_get_selected_direction,
)
from app.services.sse_bus import sse_bus


@dataclass
class CopywriteContext:
    """从 WorkflowState 提取的文案生成上下文。

    把 60% 的配置提取逻辑从 copywrite_node 抽出来，
    节点函数只做「取上下文 → 调 Skill → 组装输出」三步。
    """
    topic: str = ""
    search_keyword: str = ""
    copywrite_topic: str = ""
    creative_brief: str = ""
    model_settings: dict = field(default_factory=dict)
    user_temperature: float | None = None
    user_text_model: str | None = None
    user_writing_style: str = ""
    copywrite_skill_name: str | None = None
    content_length: int | None = None
    auto_emoji: bool = True
    auto_tags: bool = True
    reference: dict = field(default_factory=dict)
    user_memory: dict = field(default_factory=dict)
    patterns: dict = field(default_factory=dict)
    insights: dict = field(default_factory=dict)
    execution_brief: dict = field(default_factory=dict)
    selected_direction: int = 0
    selected_recommendation: dict = field(default_factory=dict)
    direction_note: str = ""
    image_details: list = field(default_factory=list)
    image_style: str = ""
    review_feedback: str = ""
    my_patterns: dict = field(default_factory=dict)
    my_avoid: list = field(default_factory=list)
    audit_belief: dict = field(default_factory=dict)
    # D18 创作者画像（启动工作流时注入 state，全量注入文案 prompt）
    user_profile: dict = field(default_factory=dict)

    @classmethod
    def from_state(cls, state: WorkflowState) -> CopywriteContext:
        """从 WorkflowState 提取所有文案生成需要的配置和数据。"""
        topic = state.get("topic", "")
        search_keyword = (state.get("search_keyword") or topic).strip()
        creative_brief = (state.get("creative_brief") or "").strip()
        copywrite_topic = creative_brief or topic

        model_settings = state.get("model_settings", {}) or {}
        user_temperature = model_settings.get("temperature")
        user_text_model = model_settings.get("text_model")
        user_writing_style = model_settings.get("writing_style", "")
        copywrite_skill_name = model_settings.get("copywrite_skill")
        content_length = model_settings.get("content_length")
        auto_emoji = model_settings.get("auto_emoji", True)
        auto_tags = model_settings.get("auto_tags", True)

        reference = state.get("reference", {}) or {}
        user_memory = state.get("user_memory", {}) or {}

        node_outputs = state.get("node_outputs", {})
        analyze_output = node_outputs.get("analyze", {})
        patterns = analyze_output.get("patterns", {}) or {}
        insights = analyze_output.get("insights", {}) or {}

        recommendations = insights.get("recommendations") or []
        selected_direction = safe_get_selected_direction(analyze_output, recommendations)
        selected_recommendation = {}
        if recommendations and isinstance(recommendations[selected_direction], dict):
            selected_recommendation = recommendations[selected_direction]

        execution_brief = {}
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

        my_patterns = analyze_output.get("my_patterns", {}) or {}
        my_avoid = analyze_output.get("my_avoid", []) or []

        agent_beliefs = state.get("agent_beliefs", {}) or {}
        audit_belief = agent_beliefs.get("audit", {})

        # D18: 画像从 state 读取（启动时一次性注入，节点内不查 DB）
        user_profile = state.get("user_profile") or {}

        return cls(
            topic=topic,
            search_keyword=search_keyword,
            copywrite_topic=copywrite_topic,
            creative_brief=creative_brief,
            model_settings=model_settings,
            user_temperature=user_temperature,
            user_text_model=user_text_model,
            user_writing_style=user_writing_style,
            copywrite_skill_name=copywrite_skill_name,
            content_length=content_length,
            auto_emoji=auto_emoji,
            auto_tags=auto_tags,
            reference=reference,
            user_memory=user_memory,
            patterns=patterns,
            insights=insights,
            execution_brief=execution_brief,
            selected_direction=selected_direction,
            selected_recommendation=selected_recommendation,
            direction_note=direction_note,
            image_details=image_details,
            image_style=image_style,
            review_feedback=review_feedback,
            my_patterns=my_patterns,
            my_avoid=my_avoid,
            audit_belief=audit_belief,
            user_profile=dict(user_profile),
        )


async def copywrite_node(state: WorkflowState) -> dict:
    """Copywrite node: 基于分析洞察 + 图片描述生成小红书文案。

    流程：
    1. CopywriteContext.from_state(state) 一步提取所有配置
    2. 调 LLM Skill 生成 title + content + tags
    3. 组装输出 + 信念 + 回溯计数
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

    # ===== Step 1: 一步提取所有配置 =====
    ctx = CopywriteContext.from_state(state)

    logger.info(
        f"[{workflow_id}] {node_id} upstream: "
        f"patterns={'yes' if ctx.patterns else 'no'}, "
        f"insights={'yes' if ctx.insights else 'no'}, "
        f"execution_brief={'yes' if ctx.execution_brief else 'no'}, "
        f"selected_direction={ctx.selected_direction}, "
        f"creative_brief={'yes' if ctx.creative_brief else 'no'}, "
        f"search_keyword={ctx.search_keyword or '(none)'}, "
        f"image_details={len(ctx.image_details)}, "
        f"review_feedback={'yes' if ctx.review_feedback else 'no'}, "
        f"writing_style={ctx.user_writing_style or '(default)'}, "
        f"temperature={ctx.user_temperature if ctx.user_temperature is not None else '(default)'}, "
        f"reference={'yes' if ctx.reference else 'no'}"
    )

    # ===== Step 2: 调 LLM 生成文案 =====
    await emit_node_event(workflow_id, node_id, "progress_update", {
        "progress": 30,
        "step": "copywriting",
        "message": "LLM 生成小红书文案中...",
    })

    from app.engine.factory import get_deepseek_llm
    from app.tools.registry import get_skill_class
    import app.tools.copywrite_builder  # noqa: F401
    from app.tools.copywrite_builder import (
        CopywriteSkillBase,
        LivelyGirlCopywriteSkill,
        _WRITING_STYLE_TO_SKILL_NAME,
    )

    llm = get_deepseek_llm(temperature=ctx.user_temperature, model=ctx.user_text_model)

    skill_name = ctx.copywrite_skill_name
    if not skill_name and ctx.user_writing_style:
        skill_name = _WRITING_STYLE_TO_SKILL_NAME.get(
            ctx.user_writing_style.strip(), "lively_girl"
        )
    copywrite_skill_cls = get_skill_class("copywrite", skill_name or "lively_girl")
    if copywrite_skill_cls is None:
        logger.warning(
            f"[{workflow_id}] copywrite skill '{skill_name}' not found, "
            f"falling back to LivelyGirlCopywriteSkill"
        )
        copywrite_skill_cls = LivelyGirlCopywriteSkill
    copywrite_skill = copywrite_skill_cls()
    logger.info(
        f"[{workflow_id}] copywrite using skill: {copywrite_skill.name} "
        f"({copywrite_skill.__class__.__name__})"
    )

    try:
        result = await copywrite_skill.execute_streaming({
            "llm": llm,
            "topic": ctx.copywrite_topic,
            "insights": ctx.insights,
            "patterns": ctx.patterns,
            "execution_brief": ctx.execution_brief,
            "image_details": ctx.image_details,
            "image_style": ctx.image_style,
            "reference": ctx.reference,
            "user_memory": ctx.user_memory,
            "content_length": ctx.content_length,
            "auto_emoji": ctx.auto_emoji,
            "auto_tags": ctx.auto_tags,
            "workflow_id": workflow_id,
            "node_id": node_id,
            "my_patterns": ctx.my_patterns,
            "my_avoid": ctx.my_avoid,
            "user_profile": ctx.user_profile,
        })
    except Exception as e:
        err_str = str(e)
        logger.exception(f"[{workflow_id}] {node_id} copywrite failed: {e}")

        if "402" in err_str or "Insufficient Balance" in err_str or "余额" in err_str:
            await sse_bus.publish(workflow_id, "model_arrearage", {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "provider": "deepseek",
                "message": "DeepSeek 余额不足，文案生成降级为模板模式",
                "action_url": "https://platform.deepseek.com/usage",
                "action_text": "前往 DeepSeek 控制台充值",
            })

        result = copywrite_skill.fallback(ctx.copywrite_topic, ctx.insights, ctx.image_details)

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

    # ===== Step 4: 后处理管线（字数校验→AI味扫描→CTA检查） =====
    try:
        from app.agents.nodes.copywrite_postprocess import run_postprocess_pipeline

        postprocessed = await run_postprocess_pipeline(
            title=output["title"],
            content=output["content"],
            tags=output["tags"],
            workflow_id=workflow_id,
            node_id=node_id,
            content_length=ctx.content_length,
            auto_emoji=ctx.auto_emoji,
            auto_tags=ctx.auto_tags,
        )
        output["title"] = postprocessed["title"]
        output["content"] = postprocessed["content"]
        output["tags"] = postprocessed["tags"]
        if postprocessed.get("pipeline"):
            output["postprocess_pipeline"] = postprocessed["pipeline"]
        logger.info(
            f"[{workflow_id}] {node_id} postprocess pipeline: "
            f"modified={postprocessed['pipeline'].get('modified', False)}, "
            f"steps={len(postprocessed['pipeline'].get('steps', []))}"
        )
    except Exception as pp_err:
        logger.warning(
            f"[{workflow_id}] {node_id} postprocess pipeline failed (skip): {pp_err}"
        )

    if ctx.review_feedback:
        output["review_feedback"] = ctx.review_feedback

    elapsed = int((time.time() - start_time) * 1000)
    logger.info(
        f"[{workflow_id}] {node_id} completed: "
        f"source={output['prompt_source']}, "
        f"title={output['title'][:30]}, "
        f"content_len={len(output['content'])}, "
        f"tags={len(output['tags'])}, "
        f"elapsed={elapsed}ms"
    )

    if ctx.audit_belief.get("verdict") in ("needs_revision", "rejected"):
        revision_hints = ctx.audit_belief.get("compromise") or ctx.audit_belief.get("request_payload") or {}
        if revision_hints:
            output["revision_hints"] = revision_hints
            logger.info(
                f"[{workflow_id}] {node_id} 收到 audit 修改意见: "
                f"{list(revision_hints.keys())}"
            )

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