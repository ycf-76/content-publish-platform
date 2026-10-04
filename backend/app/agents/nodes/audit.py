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
    creative_brief = (state.get("creative_brief") or "").strip()
    copywrite_output = state.get("node_outputs", {}).get("copywrite", {})

    # ── 出站内容安全闸门（确定性扫描，在 LLM 审核之前） ──
    # 扫描标题+正文，检出 API key/内部地址/代理IP 等敏感信息
    # BLOCK 级命中 → 直接拒绝，不进 LLM 审核
    # WARN 级命中 → 记录告警，继续 LLM 审核
    content_guard_block_findings = []
    content_guard_warn_findings = []
    try:
        from app.services.content_guard import guard_or_die, ContentGuardError
        audit_text_parts = [
            copywrite_output.get("title", ""),
            copywrite_output.get("content", ""),
        ]
        try:
            warn_findings = guard_or_die(
                audit_text_parts,
                allow_unsafe=False,
                label="审核内容",
            )
            content_guard_warn_findings = warn_findings
            if warn_findings:
                logger.warning(
                    f"[{workflow_id}] {node_id} content_guard WARN: "
                    f"{len(warn_findings)} 处 AI 措辞/模型名提醒"
                )
        except ContentGuardError as e:
            content_guard_block_findings = e.findings
            logger.error(
                f"[{workflow_id}] {node_id} content_guard BLOCK: "
                f"{len(e.findings)} 处敏感信息泄露，直接拒绝"
            )
    except ImportError:
        logger.debug(f"[{workflow_id}] {node_id} content_guard not available, skip")

    # ── content_guard BLOCK 级命中 → 直接拒绝，不进 LLM 审核 ──
    if content_guard_block_findings:
        block_issues = [
            f"[{f.category}/{f.severity}] {f.hint}: {f.snippet}"
            for f in content_guard_block_findings
        ]
        output = {
            "passed": False,
            "issues": block_issues,
            "suggestions": ["请从内容中删除上述敏感信息后重新提交"],
            "audit_method": "content_guard_block",
            "content_guard": {
                "blocked": True,
                "block_count": len(content_guard_block_findings),
                "warn_count": len(content_guard_warn_findings),
            },
        }
        await emit_node_event(workflow_id, node_id, "node_completed", output)
        logger.info(
            f"[{workflow_id}] {node_id} BLOCKED by content_guard: "
            f"{len(content_guard_block_findings)} 处敏感信息"
        )
        return {
            "current_node": node_id,
            "node_statuses": {node_id: NodeStatus.COMPLETED.value},
            "node_outputs": {node_id: output},
        }

    # 用户在右侧工作区选择的 audit skill 配置
    model_settings = state.get("model_settings", {}) or {}
    audit_skill_name = model_settings.get("audit_skill") or "standard"

    # 通过 registry 加载 audit Skill（支持第三方插件）
    from app.tools.registry import get_skill_class
    # 触发内置 Skill 注册（import 即注册）
    import app.tools.audit_skill  # noqa: F401
    from app.tools.audit_skill import StandardAuditSkill

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
    from app.engine.factory import get_deepseek_llm
    llm = get_deepseek_llm()

    await emit_node_event(workflow_id, node_id, "tool_call_start", {
        "tool": "audit_skill",
        "skill": audit_skill.name,
    })

    try:
        audit_result = await audit_skill.execute({
            "llm": llm,
            "topic": creative_brief or topic,
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
        # 注入 content_guard WARN 信息到输出
        if content_guard_warn_findings:
            output["content_guard"] = {
                "blocked": False,
                "block_count": 0,
                "warn_count": len(content_guard_warn_findings),
                "warnings": [
                    f"[{f.category}] {f.hint}: {f.snippet}"
                    for f in content_guard_warn_findings
                ],
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