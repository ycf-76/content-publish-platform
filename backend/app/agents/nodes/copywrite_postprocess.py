"""文案后处理管线。

copywrite_node 生成文案后，依次执行：
1. 润色去AI味（确定性扫描 + LLM 润色）
2. 字数校验（小红书平台限制）
3. CTA 生成（行动引导语）

借鉴 Easel copywriting SKILL 的 10 步工作流中步骤 7-9，
但适配我们的异步工作流架构，不依赖 CLI 脚本。
"""

from __future__ import annotations

from app.agents.nodes._base import logger


async def run_postprocess_pipeline(
    title: str,
    content: str,
    tags: list[str],
    *,
    workflow_id: str = "",
    node_id: str = "copywrite",
    content_length: int | None = None,
    auto_emoji: bool = True,
    auto_tags: bool = True,
) -> dict:
    """执行文案后处理管线，返回处理后的文案 + 管线报告。

    不会抛异常——任何步骤失败都降级为"跳过"，保证文案不丢失。
    """
    pipeline_report = {
        "steps": [],
        "modified": False,
    }

    result_title = title
    result_content = content
    result_tags = list(tags)

    # ── Step 1: 字数校验（确定性，不调 LLM） ──
    step1 = _step_wordcount_check(result_title, result_content, content_length)
    pipeline_report["steps"].append(step1)

    # ── Step 2: AI 味确定性扫描（WARN 级提醒，不修改文案） ──
    step2 = _step_ai_marker_scan(result_title, result_content, workflow_id, node_id)
    pipeline_report["steps"].append(step2)

    # ── Step 3: CTA 补充（如果文案缺少行动引导） ──
    step3 = _step_cta_check(result_content, result_tags)
    pipeline_report["steps"].append(step3)
    if step3.get("cta_suggestion"):
        pipeline_report["cta_suggestion"] = step3["cta_suggestion"]

    if any(s.get("modified") for s in pipeline_report["steps"]):
        pipeline_report["modified"] = True

    return {
        "title": result_title,
        "content": result_content,
        "tags": result_tags,
        "pipeline": pipeline_report,
    }


def _step_wordcount_check(title: str, content: str, content_length: int | None) -> dict:
    """Step 1: 字数校验。"""
    try:
        from app.services.wordcount import check_xhs, count
        xhs_check = check_xhs(title, content)
        step = {
            "name": "wordcount_check",
            "ok": xhs_check["pass"],
            "detail": xhs_check,
            "modified": False,
        }
        if not xhs_check["pass"]:
            issues = []
            if not xhs_check["title"]["ok"]:
                issues.append(
                    f"标题 {xhs_check['title']['count']} 字，"
                    f"超出上限 {xhs_check['title']['max']} 字"
                )
            if not xhs_check["content"]["hard_ok"]:
                issues.append(
                    f"正文 {xhs_check['content']['count']} 字，"
                    f"超出硬上限 {xhs_check['content']['hard_max']} 字"
                )
            step["warnings"] = issues
        return step
    except ImportError:
        return {"name": "wordcount_check", "ok": True, "skipped": True, "modified": False}


def _step_ai_marker_scan(title: str, content: str, workflow_id: str, node_id: str) -> dict:
    """Step 2: AI 味确定性扫描（WARN 级，不修改文案）。"""
    try:
        from app.services.content_guard import scan
        findings = scan(f"{title}\n{content}")
        ai_findings = [f for f in findings if f.category == "ai-disclosure"]
        model_findings = [f for f in findings if f.category == "model-name"]
        all_warn = ai_findings + model_findings
        step = {
            "name": "ai_marker_scan",
            "ok": len(all_warn) == 0,
            "ai_disclosure_count": len(ai_findings),
            "model_name_count": len(model_findings),
            "modified": False,
        }
        if all_warn:
            step["warnings"] = [
                f"[{f.category}] {f.hint}: {f.snippet}"
                for f in all_warn
            ]
        return step
    except ImportError:
        return {"name": "ai_marker_scan", "ok": True, "skipped": True, "modified": False}


_CTA_PATTERNS = [
    "收藏", "点赞", "关注", "评论", "分享", "转发",
    "码住", "三连", "安利", "种草",
    "下单", "购买", "入手", "冲",
    "试试", "去看看", "来抄作业",
]


def _step_cta_check(content: str, tags: list[str]) -> dict:
    """Step 3: CTA 检查——文案是否包含行动引导。

    如果没有 CTA，给出建议但不修改文案（由 LLM 或用户决定是否添加）。
    """
    has_cta = any(p in content for p in _CTA_PATTERNS)
    step = {
        "name": "cta_check",
        "ok": has_cta,
        "modified": False,
    }
    if not has_cta:
        step["cta_suggestion"] = (
            "文案缺少行动引导（CTA），建议在文末添加："
            "「记得收藏/点赞，需要的时候不迷路」"
            " 或 「评论区告诉我你的想法」"
        )
    return step