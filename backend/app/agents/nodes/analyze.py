from app.agents.nodes._base import NodeStatus, WorkflowState, emit_node_event, logger


async def analyze_node(state: WorkflowState) -> dict:
    """Analyze node: 三层分层分析架构。

    Layer 1：规则层（0 LLM 成本）—— 派生指标 + 分位数分类 + 爆点分排序
    Layer 2：LLM 粗分析（top 5，1 次调用）—— 标题钩子 / 内容结构 / 情绪触发点
    Layer 3：LLM 深度归因（top 2，1 次调用）—— 趋势信号 + 选题建议

    可插拔：通过 SkillRegistry 加载 analyze 节点的 Skill 子类，
    第三方可以在 backend/skills/ 下注册自己的 AnalyzeSkillBase 子类。

    LLM 不可用时降级为只返回 Layer 1 结果。
    """
    import time
    from app.agents.skills.viral_analyzer import analyze_viral
    from app.agents.harnesses.factory import get_deepseek_llm
    from app.agents.skills.registry import get_skill_class
    # 触发内置 Skill 注册（import 即注册）
    import app.agents.skills.analyze_skill  # noqa: F401

    workflow_id = state["workflow_id"]
    node_id = "analyze"

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started (3-layer analysis)")

    topic = state.get("topic", "")
    # 用户在右侧工作区选择的模型/温度/analyze skill 配置
    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")
    # 用户可选择 analyze 节点的 skill name（None 时用默认 "standard"）
    analyze_skill_name = model_settings.get("analyze_skill") or "standard"
    search_output = state.get("node_outputs", {}).get("search", {})
    raw_results = search_output.get("results", [])

    # 用户级长期记忆中的偏好（preferred_topics / avoided_topics）
    # 注入 Layer3 prompt，让 LLM 推荐选题时优先/避免某些方向
    user_memory = state.get("user_memory", {}) or {}
    user_preferences = {
        "preferred_topics": user_memory.get("preferred_topics") or [],
        "avoided_topics": user_memory.get("avoided_topics") or [],
    }

    # 通过 registry 加载 analyze Skill（支持第三方插件）
    analyze_skill_cls = get_skill_class("analyze", analyze_skill_name)
    if analyze_skill_cls is None:
        logger.warning(
            f"[{workflow_id}] analyze skill '{analyze_skill_name}' not found, "
            f"falling back to StandardAnalyzeSkill"
        )
        from app.agents.skills.analyze_skill import StandardAnalyzeSkill
        analyze_skill_cls = StandardAnalyzeSkill
    analyze_skill = analyze_skill_cls()
    logger.info(
        f"[{workflow_id}] analyze using skill: {analyze_skill.name} "
        f"({analyze_skill.__class__.__name__})"
    )

    start_time = time.time()
    total_tokens = 0
    model_used = "layer1_only"

    try:
        # ===== Layer 1: 规则层（0 LLM 成本） =====
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 33,
            "current_node": node_id,
            "layer": 1,
            "message": "Layer 1 规则层：计算派生指标与爆款分类",
        })
        with_metrics, layer1_stats = analyze_viral(raw_results)
        logger.info(
            f"[{workflow_id}] analyze Layer1 done: "
            f"total={layer1_stats.get('total', 0)}, "
            f"method={layer1_stats.get('classification_method')}, "
            f"distribution={layer1_stats.get('type_distribution')}"
        )

        # LLM 不可用时降级（使用用户配置的温度+模型）
        llm = get_deepseek_llm(temperature=user_temperature, model=user_text_model)
        if llm is None:
            logger.warning(f"[{workflow_id}] analyze: LLM unavailable, Layer1 only")
            output = {
                "results": with_metrics,
                "patterns": {"_skipped": "no_llm"},
                "insights": {"_skipped": "no_llm"},
                "filter_stats": search_output.get("filter_stats", {}),
                "layer1_stats": layer1_stats,
                "_model_used": "none (layer1 only)",
                "_duration_ms": int((time.time() - start_time) * 1000),
                "_token_usage": {"prompt": 0, "completion": 0, "total": 0},
            }
            await emit_node_event(workflow_id, node_id, "node_completed", output)
            return {
                "current_node": node_id,
                "node_statuses": {node_id: NodeStatus.COMPLETED.value},
                "node_outputs": {node_id: output},
            }

        # ===== Layer 2: LLM 粗分析（top 5） =====
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 60,
            "current_node": node_id,
            "layer": 2,
            "message": "Layer 2 LLM 粗分析：识别标题钩子 / 内容结构 / 情绪触发点",
        })
        await emit_node_event(workflow_id, node_id, "tool_call_start", {
            "tool": "deepseek_layer2",
            "input_size": min(5, len(with_metrics)),
        })
        top5 = with_metrics[:5]
        patterns = await analyze_skill.analyze_layer2(llm, top5, topic)
        await emit_node_event(workflow_id, node_id, "tool_call_end", {
            "tool": "deepseek_layer2",
            "success": "_error" not in patterns and "_parse_failed" not in patterns,
        })
        logger.info(
            f"[{workflow_id}] analyze Layer2 done: "
            f"patterns_keys={list(patterns.keys())}"
        )

        # ===== Layer 3: LLM 深度归因（top 2） =====
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 85,
            "current_node": node_id,
            "layer": 3,
            "message": "Layer 3 LLM 深度归因：趋势信号 + 选题建议",
        })
        await emit_node_event(workflow_id, node_id, "tool_call_start", {
            "tool": "deepseek_layer3",
            "input_size": min(2, len(with_metrics)),
        })
        top2 = with_metrics[:2]
        insights = await analyze_skill.analyze_layer3(
            llm, top2, with_metrics, patterns, topic, user_preferences
        )
        await emit_node_event(workflow_id, node_id, "tool_call_end", {
            "tool": "deepseek_layer3",
            "success": "_error" not in insights and "_parse_failed" not in insights,
        })
        logger.info(
            f"[{workflow_id}] analyze Layer3 done: "
            f"insights_keys={list(insights.keys())}"
        )

        model_used = "deepseek-v3 (3-layer)"

        # 组装最终输出
        output = {
            "results": with_metrics,
            "patterns": patterns,
            "insights": insights,
            "filter_stats": search_output.get("filter_stats", {}),
            "layer1_stats": layer1_stats,
            "_model_used": model_used,
            "_duration_ms": int((time.time() - start_time) * 1000),
            "_token_usage": {"prompt": 0, "completion": 0, "total": total_tokens},
        }

        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 100,
            "current_node": node_id,
            "layer": "done",
            "message": "三层分析完成",
        })
        await emit_node_event(workflow_id, node_id, "node_completed", output)

    except Exception as e:
        logger.exception(f"[{workflow_id}] analyze_node failed: {e}")
        await emit_node_event(workflow_id, node_id, "node_error",
                              {"error": str(e), "error_type": type(e).__name__})
        # 降级：只返回原始 results
        output = {
            "results": raw_results,
            "patterns": {"_error": str(e)},
            "insights": {"_error": str(e)},
            "filter_stats": search_output.get("filter_stats", {}),
            "layer1_stats": {},
            "_model_used": "error_fallback",
            "_duration_ms": int((time.time() - start_time) * 1000),
            "_error": str(e),
        }
        await emit_node_event(workflow_id, node_id, "node_completed", output)

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }
