from app.agents.nodes._base import NodeStatus, WorkflowState, emit_node_event, logger


async def audit_node(state: WorkflowState) -> dict:
    """Audit node: 用 LLM 审核文案合规性。

    审核维度：合规性、平台规则、内容质量、品牌安全。
    LLM 不可用时自动通过（不阻塞工作流）。

    可插拔：通过 SkillRegistry 加载 audit 节点的 Skill 子类，
    第三方可在 backend/skills/ 下注册自己的 AuditSkillBase 子类。

    成本控制：max_tokens 由 DeepSeekAdapter 控制（默认 1500）。
    """
    import time

    workflow_id = state["workflow_id"]
    node_id = "audit"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    topic = state.get("topic", "")
    copywrite_output = state.get("node_outputs", {}).get("copywrite", {})

    # 用户在右侧工作区选择的 audit skill 配置
    model_settings = state.get("model_settings", {}) or {}
    audit_skill_name = model_settings.get("audit_skill") or "standard"

    # 通过 registry 加载 audit Skill（支持第三方插件）
    from app.agents.skills.registry import get_skill_class
    # 触发内置 Skill 注册（import 即注册）
    import app.agents.skills.audit_skill  # noqa: F401
    from app.agents.skills.audit_skill import StandardAuditSkill

    audit_skill_cls = get_skill_class("audit", audit_skill_name)
    if audit_skill_cls is None:
        logger.warning(
            f"[{workflow_id}] audit skill '{audit_skill_name}' not found, "
            f"falling back to StandardAuditSkill"
        )
        audit_skill_cls = StandardAuditSkill
    audit_skill = audit_skill_cls()
    logger.info(
        f"[{workflow_id}] audit using skill: {audit_skill.name} "
        f"({audit_skill.__class__.__name__})"
    )

    # audit 节点使用默认温度（审核需要稳定输出，不强行使用用户配置）
    from app.agents.harnesses.factory import get_deepseek_llm
    llm = get_deepseek_llm()

    await emit_node_event(workflow_id, node_id, "tool_call_start", {
        "tool": "audit_skill",
        "skill": audit_skill.name,
    })

    try:
        audit_result = await audit_skill.execute({
            "llm": llm,
            "topic": topic,
            "copywrite": copywrite_output,
        })
        output = {
            "passed": audit_result.get("passed", True),
            "issues": audit_result.get("issues", []),
            "suggestions": audit_result.get("suggestions", []),
            "audit_method": audit_result.get("audit_method", "unknown"),
            "_skill": audit_skill.name,
            "_model_used": "deepseek-chat" if llm is not None else "none",
            "_duration_ms": int((time.time() - start_time) * 1000),
        }
        await emit_node_event(workflow_id, node_id, "tool_call_end", {
            "tool": "audit_skill",
            "success": True,
            "passed": output["passed"],
        })
        logger.info(
            f"[{workflow_id}] {node_id} completed: passed={output['passed']}, "
            f"issues={len(output['issues'])}, skill={audit_skill.name}"
        )
    except Exception as e:
        logger.exception(f"[{workflow_id}] {node_id} audit skill failed: {e}")
        await emit_node_event(workflow_id, node_id, "tool_call_end", {
            "tool": "audit_skill",
            "success": False,
            "error": str(e),
        })
        output = {
            "passed": True,
            "issues": [],
            "suggestions": [],
            "audit_method": "fallback",
            "_skill": audit_skill.name,
            "_model_used": "none (fallback)",
            "_error": str(e),
            "_duration_ms": int((time.time() - start_time) * 1000),
        }

    await emit_node_event(workflow_id, node_id, "node_completed", output)

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }
