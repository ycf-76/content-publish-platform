"""Agent Belief System — 每个节点维护自己的判断，而非共享一个平铺 dict。

核心思想：
- 每个节点执行完后，自动从输出中提取信心分 + 判断（0 LLM 成本）
- 信心不足时，节点可以"请求"上游补充数据（request_to + request_payload）
- 路由层读取信念，决定是继续往下走还是回溯补数据
- 协商记录（Negotiation）用于 audit vs copywrite 冲突仲裁

三层路由：
  Layer 1: 确定性规则（保留原 routing.py 的逻辑）
  Layer 2: 信心路由（基于 AgentBelief，0 LLM）
  Layer 3: 协商路由（仅在 agent 间冲突时，1次 LLM）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Confidence(Enum):
    HIGH = 0.9
    MEDIUM = 0.6
    LOW = 0.3
    FAILED = 0.0


@dataclass
class AgentBelief:
    """单个智能体的信念快照。"""
    agent_id: str
    confidence: float
    verdict: str  # "sufficient" | "insufficient" | "rejected" | "needs_revision"
    reasoning: str
    request_to: str | None = None
    request_payload: dict | None = None
    compromise: dict | None = None

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "reasoning": self.reasoning,
            "request_to": self.request_to,
            "request_payload": self.request_payload,
            "compromise": self.compromise,
        }


@dataclass
class Negotiation:
    """两个 agent 之间的协商记录。"""
    round: int
    initiator: str
    responder: str
    issue: str
    proposals: list[dict] = field(default_factory=list)
    resolution: str | None = None
    resolved_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "initiator": self.initiator,
            "responder": self.responder,
            "issue": self.issue,
            "proposals": self.proposals,
            "resolution": self.resolution,
            "resolved_by": self.resolved_by,
        }


def belief_from_output(agent_id: str, output: dict) -> AgentBelief:
    """从节点输出自动提取信念（纯规则，0 LLM 成本）。

    每个节点根据自己的输出结构判断信心：
    - analyze: 看结果数量 + 趋势信号强度
    - copywrite: 看标题/正文/标签是否完整
    - audit: 看是否通过 + 问题严重度
    - search: 看结果数量
    - 其他节点: 默认 sufficient
    """
    if not output:
        return AgentBelief(
            agent_id=agent_id,
            confidence=Confidence.FAILED.value,
            verdict="insufficient",
            reasoning="节点输出为空",
            request_to=_default_upstream(agent_id),
            request_payload={"reason": "output_empty"},
        )

    extractor = _BELIEF_EXTRACTORS.get(agent_id)
    if extractor:
        return extractor(output)

    return AgentBelief(
        agent_id=agent_id,
        confidence=Confidence.MEDIUM.value,
        verdict="sufficient",
        reasoning="默认信念（无专用提取器）",
    )


def _default_upstream(agent_id: str) -> str | None:
    """节点失败时的默认回溯目标。"""
    upstream_map = {
        "analyze": "search",
        "copywrite": "analyze",
        "image_plan": "copywrite",
        "image_gen": "image_plan",
        "image_review": "image_gen",
        "audit": "copywrite",
        "final_review": "audit",
        "publish": "final_review",
    }
    return upstream_map.get(agent_id)


def _extract_search_belief(output: dict) -> AgentBelief:
    """search 节点信念：看结果数量。"""
    results = output.get("results", [])
    count = len(results) if isinstance(results, list) else 0

    if count >= 8:
        return AgentBelief(
            "search", Confidence.HIGH.value, "sufficient",
            f"搜索返回{count}条结果，数据充足",
        )
    if count >= 3:
        return AgentBelief(
            "search", Confidence.MEDIUM.value, "sufficient",
            f"搜索返回{count}条结果，基本够用",
        )
    return AgentBelief(
        "search", Confidence.LOW.value, "insufficient",
        f"搜索仅返回{count}条结果，数据不足",
    )


def _extract_analyze_belief(output: dict) -> AgentBelief:
    """analyze 节点信念：看结果数量 + 趋势信号 + recommendations。"""
    results = output.get("results", [])
    count = len(results) if isinstance(results, list) else 0
    patterns = output.get("patterns", {}) or {}
    insights = output.get("insights", {}) or {}
    has_trend = bool(patterns.get("title_patterns") or patterns.get("content_patterns"))
    recommendations = insights.get("recommendations") or []
    has_recommendations = len(recommendations) > 0

    if count >= 5 and has_trend and has_recommendations:
        return AgentBelief(
            "analyze", Confidence.HIGH.value, "sufficient",
            f"拿到{count}条结果+趋势信号+{len(recommendations)}个选题建议，信心充足",
        )
    if count >= 3 and (has_trend or has_recommendations):
        return AgentBelief(
            "analyze", Confidence.MEDIUM.value, "sufficient",
            f"有{count}条结果，趋势={has_trend}，建议={has_recommendations}，勉强够用",
        )
    return AgentBelief(
        "analyze", Confidence.LOW.value, "insufficient",
        f"仅{count}条结果，趋势={has_trend}，建议={has_recommendations}，需要更多数据",
        request_to="search",
        request_payload={
            "reason": "analyze 数据不足，需要更多搜索结果",
            "current_count": count,
            "min_results": 5,
            "has_trend": has_trend,
            "has_recommendations": has_recommendations,
        },
    )


def _extract_copywrite_belief(output: dict) -> AgentBelief:
    """copywrite 节点信念：看标题/正文/标签是否完整。"""
    title = output.get("title", "") or ""
    content = output.get("content", "") or ""
    tags = output.get("tags", []) or []
    has_title = bool(title.strip())
    has_content = len(content.strip()) > 50
    has_tags = bool(tags)

    if has_title and has_content and has_tags:
        return AgentBelief(
            "copywrite", Confidence.HIGH.value, "sufficient",
            f"标题+正文({len(content)}字)+{len(tags)}标签齐全",
        )
    if has_title and has_content:
        return AgentBelief(
            "copywrite", Confidence.MEDIUM.value, "needs_revision",
            "内容基本完整但缺标签或正文过短",
            compromise={"missing": _copywrite_missing(has_title, has_content, has_tags)},
        )
    return AgentBelief(
        "copywrite", Confidence.LOW.value, "insufficient",
        "文案生成不完整（缺标题或正文）",
        request_to="analyze",
        request_payload={"reason": "文案生成不完整，需要更明确的选题方向"},
    )


def _copywrite_missing(has_title: bool, has_content: bool, has_tags: bool) -> list[str]:
    missing = []
    if not has_title:
        missing.append("title")
    if not has_content:
        missing.append("content")
    if not has_tags:
        missing.append("tags")
    return missing


def _extract_audit_belief(output: dict) -> AgentBelief:
    """audit 节点信念：看是否通过 + 问题严重度。"""
    passed = output.get("passed", False)
    issues = output.get("issues", []) or []

    if passed:
        return AgentBelief(
            "audit", Confidence.HIGH.value, "sufficient",
            "审核通过",
        )

    severe = [i for i in issues if i.get("severity") == "high"]
    if severe:
        return AgentBelief(
            "audit", Confidence.HIGH.value, "rejected",
            f"存在{len(severe)}个严重问题，必须修改",
            request_to="copywrite",
            request_payload={"issues": severe, "action": "fix_required"},
        )

    return AgentBelief(
        "audit", Confidence.MEDIUM.value, "needs_revision",
        f"存在{len(issues)}个建议修改项",
        compromise={"action": "suggest_fix", "issues": issues},
    )


def _extract_image_gen_belief(output: dict) -> AgentBelief:
    """image_gen 节点信念：看图片数量。"""
    images = output.get("images_base64", []) or []
    image_urls = output.get("image_urls", []) or []
    count = max(len(images), len(image_urls))

    if count >= 3:
        return AgentBelief(
            "image_gen", Confidence.HIGH.value, "sufficient",
            f"生成了{count}张图片",
        )
    if count >= 1:
        return AgentBelief(
            "image_gen", Confidence.MEDIUM.value, "sufficient",
            f"仅生成{count}张图片，可能不够",
        )
    return AgentBelief(
        "image_gen", Confidence.LOW.value, "insufficient",
        "未生成任何图片",
    )


def _extract_image_plan_belief(output: dict) -> AgentBelief:
    """image_plan 节点信念：看规划是否完整（pages 数量、每页是否有内容）。"""
    card_draft = output.get("card_draft") or output.get("plan") or {}
    pages = card_draft.get("pages", []) or []
    page_count = len(pages)
    pages_with_content = sum(1 for p in pages if p.get("content") or p.get("elements"))

    if page_count >= 3 and pages_with_content >= 3:
        return AgentBelief(
            "image_plan", Confidence.HIGH.value, "sufficient",
            f"规划了{page_count}页，{pages_with_content}页有内容",
        )
    if page_count >= 1 and pages_with_content >= 1:
        return AgentBelief(
            "image_plan", Confidence.MEDIUM.value, "sufficient",
            f"规划了{page_count}页，{pages_with_content}页有内容，可能不够",
        )
    return AgentBelief(
        "image_plan", Confidence.LOW.value, "insufficient",
        f"规划不完整：{page_count}页，{pages_with_content}页有内容",
        request_to="copywrite",
        request_payload={"reason": "图片规划不完整，需要更明确的文案方向"},
    )


def _extract_image_review_belief(output: dict) -> AgentBelief:
    """image_review 节点信念：通过/拒绝 + 拒绝原因。"""
    review_status = output.get("review_status", "")
    passed = review_status in ("passed", "approved") or output.get("passed", False)
    feedback = output.get("feedback", "") or ""

    if passed:
        return AgentBelief(
            "image_review", Confidence.HIGH.value, "sufficient",
            "图片审核通过",
        )
    return AgentBelief(
        "image_review", Confidence.HIGH.value, "rejected",
        f"图片被拒绝: {feedback[:80] if feedback else '无具体原因'}",
        request_to="image_gen",
        request_payload={"reason": feedback or "图片不符合要求"},
    )


def _extract_final_review_belief(output: dict) -> AgentBelief:
    """final_review 节点信念：仲裁结果（冲突/一致/审核跳过）。"""
    arbitration = output.get("arbitration")
    review_status = output.get("review_status", "")

    if review_status in ("passed", "approved"):
        if arbitration and arbitration.get("audit_skipped"):
            return AgentBelief(
                "final_review", Confidence.MEDIUM.value, "sufficient",
                "终审通过（但 audit 被跳过，需人工确认）",
            )
        if arbitration and arbitration.get("conflict"):
            return AgentBelief(
                "final_review", Confidence.MEDIUM.value, "sufficient",
                f"终审通过（仲裁解决冲突: {arbitration.get('resolution', '?')})",
            )
        return AgentBelief(
            "final_review", Confidence.HIGH.value, "sufficient",
            "终审通过，无冲突",
        )

    return AgentBelief(
        "final_review", Confidence.HIGH.value, "rejected",
        "终审未通过",
        request_to="copywrite",
        request_payload={"reason": "终审拒绝，需修改文案"},
    )


def _extract_publish_belief(output: dict) -> AgentBelief:
    """publish 节点信念：发布是否成功 + post_id。"""
    success = output.get("success", False) or bool(output.get("post_id"))
    post_id = output.get("post_id", "")
    error = output.get("error", "")

    if success:
        return AgentBelief(
            "publish", Confidence.HIGH.value, "sufficient",
            f"发布成功 post_id={post_id}",
        )
    return AgentBelief(
        "publish", Confidence.LOW.value, "insufficient",
        f"发布失败: {error[:80] if error else '未知原因'}",
    )


_BELIEF_EXTRACTORS: dict[str, callable] = {
    "search": _extract_search_belief,
    "analyze": _extract_analyze_belief,
    "copywrite": _extract_copywrite_belief,
    "audit": _extract_audit_belief,
    "image_gen": _extract_image_gen_belief,
    "image_plan": _extract_image_plan_belief,
    "image_review": _extract_image_review_belief,
    "final_review": _extract_final_review_belief,
    "publish": _extract_publish_belief,
}