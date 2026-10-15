"""Agent 自我进化复盘服务。

核心机制：在工作流终态（完成/失败）或用户反馈（点踩）后，
用 LLM 分析执行轨迹（trace_summary）+ 反馈信号（feedback_summary），
产出结构化分析（analysis_json）与建议草稿（suggestion_md），
经人审（approve/reject）后形成 Agent 的进化闭环。

流程：
1. 收集轨迹：节点状态/耗时/token/错误信息
2. 收集反馈：赞/踩/重试统计（含踩的维度分布）
3. 构建复盘 prompt → LLM 结构化分析
4. 渲染为 markdown 人审草稿 → EvolutionProposal(status=pending_review)
5. SSE 推送 agent_reflection 事件给前端
6. 人审 → approve → 注入 Agent prompt（skill 转正）

关键设计：
1. 成本控制：只对失败/被点踩的工作流复盘，不盲目烧 token
2. 人审优先：LLM 产出的建议默认 pending_review 状态，需人工批准才能注入 prompt
3. 幂等性：每个 workflow 只自动触发一次复盘（手动触发不受限制）
4. 降级容错：LLM 不可用时降级为模板化分析，保证基础功能可用
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    EvolutionProposal,
    EvolutionProposalStatus,
    FeedbackEvent,
    FeedbackEventType,
    Workflow,
    WorkflowNode,
)
from app.db.session import AsyncSessionLocal
from app.services.sse_bus import sse_bus

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 轨迹与反馈收集
# ══════════════════════════════════════════════════════════════════

async def _collect_workflow_trace(
    db: AsyncSession, workflow_id: str
) -> dict[str, Any]:
    """收集工作流执行轨迹摘要（节点状态/耗时/token/错误）。"""
    workflow = await db.get(Workflow, workflow_id)
    if not workflow:
        return {}

    nodes_result = await db.execute(
        select(WorkflowNode)
        .where(WorkflowNode.workflow_id == workflow_id)
        .order_by(WorkflowNode.created_at)
    )
    nodes = nodes_result.scalars().all()

    node_records = []
    total_tokens = 0
    error_count = 0
    for node in nodes:
        status = node.node_status.value if hasattr(node.node_status, "value") else str(node.node_status)
        tokens = node.token_usage or 0
        total_tokens += tokens
        if status == "error":
            error_count += 1
        node_records.append({
            "type": node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
            "status": status,
            "duration_ms": node.duration_ms,
            "tokens_used": tokens,
            "error": node.error_message,
        })

    return {
        "topic": workflow.topic,
        "final_status": workflow.status.value if hasattr(workflow.status, "value") else str(workflow.status),
        "duration_ms": workflow.duration_ms,
        "total_tokens": total_tokens,
        "error_count": error_count,
        "nodes": node_records,
    }


async def _collect_feedback_summary(
    db: AsyncSession, workflow_id: str
) -> dict[str, Any]:
    """收集该工作流收到的反馈信号（赞/踩/重试 + 踩的维度分布）。"""
    result = await db.execute(
        select(
            FeedbackEvent.event_type,
            FeedbackEvent.dimension,
            func.count(FeedbackEvent.id),
        )
        .where(FeedbackEvent.workflow_id == workflow_id)
        .group_by(FeedbackEvent.event_type, FeedbackEvent.dimension)
    )
    rows = result.all()

    likes, dislikes, retries = 0, 0, 0
    dislike_dimensions: dict[str, int] = {}
    for event_type, dimension, count in rows:
        type_str = event_type.value if hasattr(event_type, "value") else str(event_type)
        if type_str == FeedbackEventType.LIKE.value:
            likes += count
        elif type_str == FeedbackEventType.DISLIKE.value:
            dislikes += count
            if dimension:
                dislike_dimensions[dimension] = dislike_dimensions.get(dimension, 0) + count
        elif type_str == FeedbackEventType.RETRY.value:
            retries += count

    return {
        "likes": likes,
        "dislikes": dislikes,
        "retries": retries,
        "dislike_dimensions": dislike_dimensions,
    }


# ══════════════════════════════════════════════════════════════════
# LLM 复盘分析
# ══════════════════════════════════════════════════════════════════

def _build_reflection_prompt(
    trace_summary: dict[str, Any],
    feedback_summary: dict[str, Any],
) -> list[dict[str, str]]:
    """构建 LLM 复盘分析 prompt（消息列表格式）。"""
    status_icons = {
        "completed": "✅", "running": "🔄", "pending": "⏸️",
        "error": "❌", "suspended": "📌", "terminated": "🛑",
    }

    node_lines = []
    for node in trace_summary.get("nodes", []):
        icon = status_icons.get(node.get("status", ""), "❓")
        error_info = f" | 错误: {node['error']}" if node.get("error") else ""
        node_lines.append(
            f"- {icon} **{node.get('type', '未知节点')}**："
            f"状态={node.get('status', '?')}，耗时={node.get('duration_ms') or '?'}ms{error_info}"
        )
    node_section = "\n".join(node_lines) if node_lines else "（无节点记录）"

    feedback_lines = []
    if feedback_summary.get("likes"):
        feedback_lines.append(f"- 👍 点赞 {feedback_summary['likes']} 次")
    if feedback_summary.get("dislikes"):
        feedback_lines.append(f"- 👎 点踩 {feedback_summary['dislikes']} 次")
        for dim, count in feedback_summary.get("dislike_dimensions", {}).items():
            feedback_lines.append(f"  - 维度「{dim}」：{count} 次")
    if feedback_summary.get("retries"):
        feedback_lines.append(f"- 🔄 用户触发重试 {feedback_summary['retries']} 次")
    feedback_section = "\n".join(feedback_lines) if feedback_lines else "- 暂无用户反馈"

    system_prompt = (
        "你是小红书多智能体内容创作系统的复盘分析专家。\n"
        "你的任务是分析工作流的执行轨迹和用户反馈，找出问题根因并提出可执行的改进建议。\n\n"
        "分析要求：\n"
        "1. 亮点识别：找出本次执行中做得好的方面（没有则返回空数组）\n"
        "2. 问题定位：按严重程度（high/medium/low）列出发现的问题，标注影响的节点/环节\n"
        "3. 根因分析：深入分析最核心的问题根因（技术/流程/prompt设计等维度）\n"
        "4. 改进建议：给出具体可执行的改进步骤（不要泛泛而谈，每条都要可落地）\n"
        "5. 预期效果：描述改进后预期达到的效果\n\n"
        "输出要求：必须以纯 JSON 格式输出（不要 markdown 代码块包裹），schema 如下：\n"
        '{\n'
        '  "highlights": ["亮点描述"],\n'
        '  "issues": [{"aspect": "影响的节点/环节", "description": "问题描述", "severity": "high|medium|low"}],\n'
        '  "root_cause": "根因分析",\n'
        '  "proposal_type": "建议分类（文案写法改进/图片规划优化/工作流设计/搜索策略/审核规则/性能优化/其他）",\n'
        '  "actionable_steps": ["具体可执行的改进步骤"],\n'
        '  "expected_outcome": "预期改进效果"\n'
        '}'
    )

    user_prompt = (
        f"## 任务背景\n"
        f"- 工作流主题：{trace_summary.get('topic', '未知')}\n"
        f"- 最终状态：{trace_summary.get('final_status', '未知')}\n"
        f"- 总执行耗时：{trace_summary.get('duration_ms') or '?'}ms\n"
        f"- 总 Token 消耗：{trace_summary.get('total_tokens') or '?'}\n"
        f"- 错误节点数：{trace_summary.get('error_count', 0)}\n\n"
        f"## 节点执行轨迹\n"
        f"{node_section}\n\n"
        f"## 用户反馈信号\n"
        f"{feedback_section}\n\n"
        f"请基于以上信息进行深度复盘分析，以纯 JSON 格式输出。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _fallback_analysis(
    trace_summary: dict[str, Any],
    feedback_summary: dict[str, Any],
) -> dict[str, Any]:
    """LLM 不可用时的降级分析（模板化，不烧 token）。"""
    issues = []
    for node in trace_summary.get("nodes", []):
        if node.get("status") == "error":
            issues.append({
                "aspect": node.get("type", "未知节点"),
                "description": node.get("error") or "节点执行失败",
                "severity": "high",
            })

    if feedback_summary.get("dislikes"):
        for dim, count in feedback_summary.get("dislike_dimensions", {}).items():
            issues.append({
                "aspect": "用户反馈",
                "description": f"用户点踩「{dim}」维度 {count} 次",
                "severity": "medium",
            })

    steps = ["检查失败节点的日志输出，定位具体错误原因"]
    if any(n.get("status") == "error" for n in trace_summary.get("nodes", [])):
        steps.append("针对报错节点检查外部依赖（API Key/网络/配额）是否正常")
    if feedback_summary.get("dislikes"):
        steps.append("针对用户点踩的维度调整对应的生成策略")

    return {
        "highlights": [],
        "issues": issues,
        "root_cause": "（降级模式）LLM 复盘服务不可用，以下为基于规则的模板化分析。",
        "proposal_type": "其他",
        "actionable_steps": steps,
        "expected_outcome": "定位并修复执行失败的基础设施问题。",
    }


async def _call_llm_analysis(
    messages: list[dict[str, str]],
) -> Optional[dict[str, Any]]:
    """调用 LLM 进行结构化复盘分析。失败返回 None（由调用方降级）。"""
    try:
        from app.adapters.llm_base import BaseLLM
        from app.engine.factory import get_deepseek_llm

        llm: Optional[BaseLLM] = get_deepseek_llm()
        if llm is None:
            return None

        response = await llm.chat(
            messages,
            response_format={"type": "json_object"},
            max_tokens=2500,
        )
        content = (response or {}).get("content", "")
        if not content:
            logger.warning("[agent_evolution] LLM 返回空内容")
            return None

        # 清理可能的 markdown 代码块包裹
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content
            if content.endswith("```"):
                content = content[:-3].strip()

        analysis = json.loads(content)

        # 字段校验与补全
        defaults = {
            "highlights": [], "issues": [], "root_cause": "",
            "proposal_type": "其他", "actionable_steps": [], "expected_outcome": "",
        }
        for key, default in defaults.items():
            if key not in analysis or analysis[key] is None:
                analysis[key] = default
        return analysis

    except json.JSONDecodeError as e:
        logger.warning(f"[agent_evolution] LLM 输出 JSON 解析失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"[agent_evolution] LLM 复盘调用失败: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# Markdown 渲染
# ══════════════════════════════════════════════════════════════════

def _severity_icon(severity: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")


def _render_suggestion_md(
    trigger_reason: str,
    trace_summary: dict[str, Any],
    feedback_summary: dict[str, Any],
    analysis: dict[str, Any],
) -> str:
    """将结构化分析渲染为人审友好的 markdown 草稿。"""
    lines: list[str] = []
    lines.append("## 📋 Agent 复盘分析报告")
    lines.append("")
    lines.append(f"**触发原因**：{trigger_reason}")
    lines.append("")

    # 任务背景
    lines.append("### 🎯 任务背景")
    lines.append(f"- 工作流主题：{trace_summary.get('topic', '未知')}")
    lines.append(f"- 最终状态：{trace_summary.get('final_status', '未知')}")
    duration = trace_summary.get("duration_ms")
    if duration:
        lines.append(f"- 执行耗时：{duration / 1000:.1f}s")
    tokens = trace_summary.get("total_tokens")
    if tokens:
        lines.append(f"- Token 消耗：{tokens:,}")
    lines.append("")

    # 亮点
    highlights = analysis.get("highlights", [])
    if highlights:
        lines.append("### ✨ 亮点")
        for h in highlights:
            lines.append(f"- {h}")
        lines.append("")

    # 问题定位
    issues = analysis.get("issues", [])
    if issues:
        lines.append("### ⚠️ 问题定位")
        for issue in issues:
            icon = _severity_icon(issue.get("severity", ""))
            aspect = issue.get("aspect", "未知环节")
            description = issue.get("description", "")
            lines.append(f"- {icon} **{aspect}**：{description}")
        lines.append("")

    # 根因分析
    root_cause = analysis.get("root_cause", "")
    if root_cause:
        lines.append("### 🔍 根因分析")
        lines.append(root_cause)
        lines.append("")

    # 改进建议
    steps = analysis.get("actionable_steps", [])
    if steps:
        lines.append("### 💡 改进建议")
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    # 预期效果
    outcome = analysis.get("expected_outcome", "")
    if outcome:
        lines.append("### 🌟 预期效果")
        lines.append(outcome)
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 核心入口：触发复盘
# ══════════════════════════════════════════════════════════════════

async def _has_existing_proposal(
    db: AsyncSession, workflow_id: str, user_id: str
) -> bool:
    """检查该工作流是否已有未拒绝的复盘建议（幂等去重）。"""
    result = await db.execute(
        select(func.count(EvolutionProposal.id)).where(
            EvolutionProposal.workflow_id == workflow_id,
            EvolutionProposal.user_id == user_id,
            EvolutionProposal.status != EvolutionProposalStatus.REJECTED,
        )
    )
    return (result.scalar() or 0) > 0


async def _do_reflect(
    workflow_id: str,
    user_id: str,
    trigger_source: str,
    trigger_reason: str,
) -> Optional[dict[str, Any]]:
    """执行一次完整复盘（在独立 DB session 中运行，可异步触发）。

    Returns: 创建的 proposal 摘要 dict（用于事件推送），失败返回 None。
    """
    try:
        async with AsyncSessionLocal() as db:
            # 幂等检查：同一 workflow 不重复生成（手动触发除外，由调用方控制）
            if trigger_source != "manual" and await _has_existing_proposal(db, workflow_id, user_id):
                logger.info(f"[agent_evolution] workflow={workflow_id} 已有复盘建议，跳过自动触发")
                return None

            trace_summary = await _collect_workflow_trace(db, workflow_id)
            if not trace_summary:
                logger.warning(f"[agent_evolution] workflow={workflow_id} 不存在或无轨迹数据")
                return None

            feedback_summary = await _collect_feedback_summary(db, workflow_id)

            # LLM 分析（失败自动降级为模板分析）
            analysis = await _call_llm_analysis(
                _build_reflection_prompt(trace_summary, feedback_summary)
            )
            if analysis is None:
                logger.info(f"[agent_evolution] workflow={workflow_id} LLM 复盘降级为模板分析")
                analysis = _fallback_analysis(trace_summary, feedback_summary)

            suggestion_md = _render_suggestion_md(
                trigger_reason, trace_summary, feedback_summary, analysis
            )

            proposal = EvolutionProposal(
                user_id=user_id,
                workflow_id=workflow_id,
                trigger_source=trigger_source,
                trigger_reason=trigger_reason,
                trace_summary=trace_summary,
                feedback_summary=feedback_summary,
                analysis_json=analysis,
                suggestion_md=suggestion_md,
                status=EvolutionProposalStatus.PENDING_REVIEW,
            )
            db.add(proposal)
            await db.commit()

            result = {
                "proposal_id": proposal.id,
                "workflow_id": workflow_id,
                "trigger_source": trigger_source,
                "proposal_type": analysis.get("proposal_type", "其他"),
                "summary": (analysis.get("root_cause") or "复盘分析已生成")[:120],
            }

            # SSE 推送（用户可能正看着页面）
            try:
                await sse_bus.publish(
                    workflow_id, "agent_reflection",
                    {"message": "Agent 已完成自我复盘，生成了改进建议草稿，请在设置页查看。", **result},
                )
            except Exception as e:
                logger.warning(f"[agent_evolution] SSE 推送失败（不影响落库）: {e}")

            logger.info(f"[agent_evolution] ✅ 复盘完成 workflow={workflow_id} proposal={proposal.id}")
            return result

    except Exception as e:
        logger.exception(f"[agent_evolution] 复盘失败 workflow={workflow_id}: {e}")
        return None


def trigger_reflection_async(
    workflow_id: str,
    user_id: str,
    trigger_source: str = "auto_error",
    trigger_reason: str = "",
) -> None:
    """异步触发复盘（fire-and-forget，不阻塞主流程）。

    Args:
        workflow_id: 目标工作流
        user_id: 归属用户
        trigger_source: auto_error（工作流失败）/ auto_dislike（用户点踩）/ manual（手动）
        trigger_reason: 人类可读的触发原因
    """
    asyncio.create_task(
        _do_reflect(workflow_id, user_id, trigger_source, trigger_reason)
    )


async def trigger_reflection(
    workflow_id: str,
    user_id: str,
    trigger_source: str = "manual",
    trigger_reason: str = "用户手动触发复盘",
) -> Optional[dict[str, Any]]:
    """同步触发复盘（手动场景，等待结果返回）。"""
    return await _do_reflect(workflow_id, user_id, trigger_source, trigger_reason)


# ══════════════════════════════════════════════════════════════════
# 人审操作
# ══════════════════════════════════════════════════════════════════

async def review_proposal(
    db: AsyncSession,
    proposal_id: str,
    user_id: str,
    decision: str,
    review_comment: Optional[str] = None,
) -> Optional[EvolutionProposal]:
    """人审复盘建议。

    Args:
        decision: "approve" | "reject"
        approve 后 applied_at 记录应用时间（后续版本接入 prompt 注入机制）
    """
    proposal = await db.get(EvolutionProposal, proposal_id)
    if not proposal or proposal.user_id != user_id:
        return None

    if proposal.status != EvolutionProposalStatus.PENDING_REVIEW:
        return proposal  # 已审过，幂等返回

    if decision == "approve":
        proposal.status = EvolutionProposalStatus.APPROVED
        proposal.applied_at = datetime.now(UTC)
        # TODO（后续迭代）：将 analysis_json.actionable_steps 注入对应 Agent 的
        # prompt 模板或追加到 skill.md，实现真正的「进化转正」。
    elif decision == "reject":
        proposal.status = EvolutionProposalStatus.REJECTED
    else:
        raise ValueError(f"无效的审核决定: {decision}")

    proposal.review_comment = review_comment
    proposal.reviewed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(proposal)
    return proposal
