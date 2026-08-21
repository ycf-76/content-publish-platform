import json
from pathlib import Path

from app.agents.nodes._base import NodeStatus, WorkflowState, emit_node_event, logger
from app.services.sse_bus import sse_bus

# prompts 目录在 app/agents/prompts/（quality_checks.py 在 app/agents/nodes/，需往上两级）
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    """加载 prompts 目录下的 md 模板。文件不存在时返回空串。"""
    p = _PROMPTS_DIR / name
    if not p.exists():
        logger.warning(f"prompt file not found: {p}")
        return ""
    return p.read_text(encoding="utf-8")


# 预加载 3 个软语义 prompt（模块级缓存，避免每次节点调用都读盘）
_QUALITY_CHECK_ANALYZE_PROMPT = _load_prompt("quality_check_analyze.md")
_QUALITY_CHECK_COPYWRITE_PROMPT = _load_prompt("quality_check_copywrite.md")
_QUALITY_CHECK_AUDIT_PROMPT = _load_prompt("quality_check_audit.md")


async def _run_soft_semantic_check(
    workflow_id: str,
    check_type: str,
    upstream_node: str,
    upstream_output: dict,
    topic: str,
    prompt_template: str,
) -> dict:
    """软语义判断统一入口（Layer2）。

    红线：
    - 只判质量，不做路由决策（路由由 conditional_edges 硬编码）
    - 不命令 Agent 重跑（建议权，用户拍板）
    - LLM 不可用或调用异常时默认放行（不阻塞工作流）

    Returns:
        {"quality_pass": bool, "reason": str, "suggestions": list[str], "severity": str}
    """
    from app.engine.factory import get_deepseek_llm

    node_id = f"quality_check_{check_type}"
    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                          {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} soft semantic check started")

    llm = get_deepseek_llm()
    if llm is None:
        logger.warning(
            f"[{workflow_id}] {node_id} LLM unavailable, auto-pass"
        )
        result: dict = {
            "quality_pass": True,
            "reason": "LLM 未配置，自动放行",
            "suggestions": [],
            "severity": "low",
        }
    elif not prompt_template:
        logger.warning(
            f"[{workflow_id}] {node_id} prompt template empty, auto-pass"
        )
        result = {
            "quality_pass": True,
            "reason": "软语义 prompt 未加载，自动放行",
            "suggestions": [],
            "severity": "low",
        }
    else:
        # 渲染 prompt：upstream_output 截断防止 token 超限
        upstream_str = json.dumps(
            upstream_output, ensure_ascii=False, default=str
        )[:3000]
        try:
            prompt = prompt_template.format(
                topic=topic,
                upstream_output=upstream_str,
            )
        except (KeyError, IndexError):
            prompt = prompt_template

        try:
            resp = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            content = (resp.get("content") or "").strip()
            # 容忍 markdown fence
            if content.startswith("```"):
                lines = content.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            parsed = json.loads(content)
            result = {
                "quality_pass": bool(parsed.get("quality_pass", True)),
                "reason": str(parsed.get("reason", "")),
                "suggestions": list(parsed.get("suggestions", [])),
                "severity": str(parsed.get("severity", "low")),
            }
        except Exception as e:
            logger.warning(
                f"[{workflow_id}] {node_id} LLM call failed: {e}, auto-pass"
            )
            result = {
                "quality_pass": True,
                "reason": f"软语义判断异常: {e}",
                "suggestions": [],
                "severity": "low",
            }

    # 推送 quality_check_result 事件（前端执行详情面板展示）
    await sse_bus.publish(
        workflow_id,
        "quality_check_result",
        {
            "node_id": node_id,
            "upstream_node": upstream_node,
            **result,
        },
    )
    await emit_node_event(workflow_id, node_id, "node_completed", result)

    return result


def _build_pending_suggestion(
    check_type: str,
    target_node: str,
    result: dict,
) -> dict:
    """根据软语义失败结果构造 pending_suggestion 数据（待 WorkflowService 写 DB）。"""
    return {
        "suggestion_type": "structural",
        "target_node": target_node,
        "severity": result.get("severity", "medium"),
        "message": result.get("reason", "软语义判断未通过"),
        "suggestions": result.get("suggestions", []),
        "source_node": f"quality_check_{check_type}",
    }


async def analyze_quality_check_node(state: WorkflowState) -> dict:
    """软语义: analyze 后置判断（爆款因子是否符合主题调性）。"""
    workflow_id = state["workflow_id"]
    analyze_output = state.get("node_outputs", {}).get("analyze", {})

    result = await _run_soft_semantic_check(
        workflow_id=workflow_id,
        check_type="analyze",
        upstream_node="analyze",
        upstream_output=analyze_output,
        topic=state.get("topic", ""),
        prompt_template=_QUALITY_CHECK_ANALYZE_PROMPT,
    )

    node_outputs = {"quality_check_analyze": result}
    existing_suggestions = list(state.get("pending_suggestions", []))
    new_suggestions: list[dict] = []

    if not result.get("quality_pass", True):
        suggestion = _build_pending_suggestion("analyze", "analyze", result)
        # 推送 supervisor_suggestion 事件（前端弹确认框）
        await sse_bus.publish(
            workflow_id,
            "supervisor_suggestion",
            {
                "workflow_id": workflow_id,
                "node_id": "quality_check_analyze",
                **suggestion,
                "require_user_confirm": True,
            },
        )
        new_suggestions = [suggestion]

    return {
        "node_outputs": node_outputs,
        "pending_suggestions": existing_suggestions + new_suggestions,
    }


async def copywrite_quality_check_node(state: WorkflowState) -> dict:
    """软语义: copywrite 后置判断（文案是否空洞/调性不符/字数不达标）。"""
    workflow_id = state["workflow_id"]
    copywrite_output = state.get("node_outputs", {}).get("copywrite", {})

    result = await _run_soft_semantic_check(
        workflow_id=workflow_id,
        check_type="copywrite",
        upstream_node="copywrite",
        upstream_output=copywrite_output,
        topic=state.get("topic", ""),
        prompt_template=_QUALITY_CHECK_COPYWRITE_PROMPT,
    )

    node_outputs = {"quality_check_copywrite": result}
    existing_suggestions = list(state.get("pending_suggestions", []))
    new_suggestions: list[dict] = []

    if not result.get("quality_pass", True):
        suggestion = _build_pending_suggestion("copywrite", "copywrite", result)
        await sse_bus.publish(
            workflow_id,
            "supervisor_suggestion",
            {
                "workflow_id": workflow_id,
                "node_id": "quality_check_copywrite",
                **suggestion,
                "require_user_confirm": True,
            },
        )
        new_suggestions = [suggestion]

    return {
        "node_outputs": node_outputs,
        "pending_suggestions": existing_suggestions + new_suggestions,
    }


async def audit_quality_check_node(state: WorkflowState) -> dict:
    """软语义: audit 后置判断（审核是否到位，双重保险）。"""
    workflow_id = state["workflow_id"]
    audit_output = state.get("node_outputs", {}).get("audit", {})

    result = await _run_soft_semantic_check(
        workflow_id=workflow_id,
        check_type="audit",
        upstream_node="audit",
        upstream_output=audit_output,
        topic=state.get("topic", ""),
        prompt_template=_QUALITY_CHECK_AUDIT_PROMPT,
    )

    node_outputs = {"quality_check_audit": result}
    existing_suggestions = list(state.get("pending_suggestions", []))
    new_suggestions: list[dict] = []

    if not result.get("quality_pass", True):
        suggestion = _build_pending_suggestion("audit", "copywrite", result)
        await sse_bus.publish(
            workflow_id,
            "supervisor_suggestion",
            {
                "workflow_id": workflow_id,
                "node_id": "quality_check_audit",
                **suggestion,
                "require_user_confirm": True,
            },
        )
        new_suggestions = [suggestion]

    return {
        "node_outputs": node_outputs,
        "pending_suggestions": existing_suggestions + new_suggestions,
    }
