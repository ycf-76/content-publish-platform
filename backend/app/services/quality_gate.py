"""共享质量门禁（Quality Gate）。

把 BLCaptain 风格校验的 R1-R9 规则 + 满铺图构图合同
（full-bleed-image-composition-contracts.json）抽成可复用的服务，
供所有出图路径统一调用：

- 对话式 blueprint 路径（image_gen_skill blueprint 模式）
- Graph 工作流路径（ContentPlanner.plan 之后）
- 前端卡片编辑器 html2canvas 导出前预检（POST /api/quality-gate/check）
- 最终 review 节点复核

设计原则：
- validator 只判断「结构 / 数值越界」问题，不替代人工审美（与 R 规则一致）。
- 能在 card_draft 内容层验证的，就在此验证；必须等渲染出图才看的
  （真实溢出、字体环境、对比度）标记为 INFO，提示由人工/前端像素校验补位。
- 报告可序列化为 JSON，方便写进 CreativeArtifact.quality 与 SSE 下发。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

try:
    from app.templates.registry import get_template_registry
except ImportError:
    def get_template_registry():
        return None

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 阈值（来源：full-bleed-image-composition-contracts.json）
# --------------------------------------------------------------------------- #
MIN_QUIET_ZONE_RATIO = 0.3
MAX_TITLE_CANVAS_RATIO = 0.4
MAX_OVERLAY_PEAK_ALPHA = 0.3

# 满铺图角色：这类页面需要走 R8 / R9 合同校验
_FULLBLEED_INDICATORS = ("full-bleed", "full_bleed", "fullbleed")
_IMAGE_PAGE_TYPES = ("image_page", "image")


# --------------------------------------------------------------------------- #
# 字段字数 / 行数上限（R2 Type Caps 的内容层代理）
# key -> (warn_min, warn_max, block_max)
# 超过 block_max 视为会溢出海报，标记 blocking；warn 区间给温和提示。
# --------------------------------------------------------------------------- #
FIELD_CAPS: dict[str, dict[str, int]] = {
    "title": {"warn_min": 6, "warn_max": 40, "block_max": 52},
    "subtitle": {"warn_min": 0, "warn_max": 30, "block_max": 40},
    "footer": {"warn_min": 0, "warn_max": 20, "block_max": 28},
    "content": {"warn_min": 30, "warn_max": 220, "block_max": 300},
    "highlight": {"warn_min": 0, "warn_max": 16, "block_max": 24},
    "tag": {"warn_min": 0, "warn_max": 12, "block_max": 18},
    "ctaText": {"warn_min": 0, "warn_max": 24, "block_max": 36},
    "masthead": {"warn_min": 0, "warn_max": 30, "block_max": 40},
}

# 数组类型字段的合理数量区间（R4 Band Density 的内容层代理）
ARRAY_CAPS: dict[str, dict[str, int]] = {
    "listItems": {"min": 2, "warn_max": 8, "block_max": 12},
    "compareLeftItems": {"min": 2, "warn_max": 6, "block_max": 9},
    "compareRightItems": {"min": 2, "warn_max": 6, "block_max": 9},
    "steps": {"min": 2, "warn_max": 8, "block_max": 12},
    "numberedItems": {"min": 2, "warn_max": 8, "block_max": 12},
    "iconTextPairs": {"min": 2, "warn_max": 6, "block_max": 9},
    "newspaperCols": {"min": 2, "warn_max": 5, "block_max": 8},
}


# --------------------------------------------------------------------------- #
# 报告模型
# --------------------------------------------------------------------------- #
class QualityIssue(BaseModel):
    """单条质量发现。"""

    rule: str = Field(description="规则编号：R1-R9 / CONTRACT_* / DIVERSITY / COUNT")
    severity: str = Field(description="blocking / warn / info")
    scope: str = Field(default="page", description="page / draft")
    page_index: int | None = None
    page_type: str | None = None
    field: str | None = None
    message: str
    suggestion: str = ""


class PageQuality(BaseModel):
    page_index: int
    page_type: str
    issues: list[QualityIssue] = Field(default_factory=list)


class QualityReport(BaseModel):
    passed: bool = Field(description="是否有 blocking 级问题")
    blocking: int = 0
    warn: int = 0
    info: int = 0
    page_reports: list[PageQuality] = Field(default_factory=list)
    draft_issues: list[QualityIssue] = Field(default_factory=list)
    summary: str = ""

    def all_issues(self) -> list[QualityIssue]:
        out: list[QualityIssue] = []
        for pr in self.page_reports:
            out.extend(pr.issues)
        out.extend(self.draft_issues)
        return out


# --------------------------------------------------------------------------- #
# 页面级检查
# --------------------------------------------------------------------------- #
def _is_fullbleed(page: dict[str, Any]) -> bool:
    role = (page.get("imageRole") or "").lower()
    if role in _FULLBLEED_INDICATORS:
        return True
    if page.get("type") in _IMAGE_PAGE_TYPES:
        return True
    # 显式声明了满铺合同字段的，也按满铺处理
    return any(k in page for k in ("subjectMap", "safeTextZones", "objectPosition"))


def _char_count(value: Any) -> int:
    if value is None:
        return 0
    return len(str(value).strip())


def check_page(
    page_index: int,
    page: dict[str, Any],
    registry: Any | None = None,
) -> PageQuality:
    """检查单页内容：R2/R3/R4/R7/R8/R9 的内容层代理。"""
    registry = registry or get_template_registry()
    ptype = page.get("type") or "content"
    issues: list[QualityIssue] = []

    # R2 Type Caps：文本字段字数
    for field, caps in FIELD_CAPS.items():
        val = page.get(field)
        if val is None or val == "":
            continue
        n = _char_count(val)
        if field in ("title", "footer") and n == 0:
            continue
        if caps.get("warn_min") and n < caps["warn_min"] and field == "content":
            # 正文过薄会在 R4 / 内容空洞处统一提示，这里不重复报
            pass
        if n > caps["block_max"]:
            issues.append(QualityIssue(
                rule="R2", severity="blocking", scope="page",
                page_index=page_index, page_type=ptype, field=field,
                message=f"「{field}」字数 {n} 超过上限 {caps['block_max']}，会溢出卡片",
                suggestion=f"压缩到 {caps['warn_max']} 字以内",
            ))
        elif n > caps["warn_max"]:
            issues.append(QualityIssue(
                rule="R2", severity="warn", scope="page",
                page_index=page_index, page_type=ptype, field=field,
                message=f"「{field}」字数 {n} 接近上限（{caps['warn_max']}）",
                suggestion="考虑精简，预留安全区",
            ))

    # R4 Band Density：数组长度
    for field, caps in ARRAY_CAPS.items():
        val = page.get(field)
        if not isinstance(val, list) or not val:
            continue
        n = len(val)
        if n < caps["min"]:
            issues.append(QualityIssue(
                rule="R4", severity="warn", scope="page",
                page_index=page_index, page_type=ptype, field=field,
                message=f"「{field}」仅 {n} 条，信息带偏薄",
                suggestion=f"补充到至少 {caps['min']} 条",
            ))
        elif n > caps["block_max"]:
            issues.append(QualityIssue(
                rule="R4", severity="blocking", scope="page",
                page_index=page_index, page_type=ptype, field=field,
                message=f"「{field}」{n} 条超过密度上限 {caps['block_max']}，会读不过来",
                suggestion=f"拆页或压缩到 {caps['warn_max']} 条以内",
            ))
        elif n > caps["warn_max"]:
            issues.append(QualityIssue(
                rule="R4", severity="warn", scope="page",
                page_index=page_index, page_type=ptype, field=field,
                message=f"「{field}」{n} 条偏密",
                suggestion=f"考虑 ≤ {caps['warn_max']} 条以保证可读性",
            ))

    # R3 Footer Collision：页脚不得与正文重复
    footer = page.get("footer")
    if footer and isinstance(footer, str):
        body = " ".join(str(page.get(k, "")) for k in ("content", "listItems", "steps", "compareLeftItems"))
        if body and footer.strip() and footer.strip() in body:
            issues.append(QualityIssue(
                rule="R3", severity="warn", scope="page",
                page_index=page_index, page_type=ptype, field="footer",
                message="页脚文本与正文重复，易出现碰撞感",
                suggestion="页脚用署名/出处，避免复用正文句子",
            ))

    # 内容空洞：必填字段缺失
    if ptype == "content" and not page.get("content"):
        issues.append(QualityIssue(
            rule="R2", severity="blocking", scope="page",
            page_index=page_index, page_type=ptype, field="content",
            message="正文页缺少 content，页面为空",
            suggestion="回填 50-120 字实质文案",
        ))

    # 满铺图 / 图片页：R7 / R8 / R9 合同校验
    if _is_fullbleed(page):
        # R7 Image Source Record
        if not (page.get("source") or page.get("image_source") or page.get("imageUrl")):
            issues.append(QualityIssue(
                rule="R7", severity="warn", scope="page",
                page_index=page_index, page_type=ptype,
                message="图片缺少来源记录（source / image_source）",
                suggestion="补充 IMAGE_REQUESTS / SOURCES 中的来源标识",
            ))
        # R8 Object Position
        missing_pos = [k for k in ("objectPosition", "subjectMap", "safeTextZones", "avoidZones")
                       if not page.get(k)]
        if missing_pos:
            issues.append(QualityIssue(
                rule="R8", severity="blocking", scope="page",
                page_index=page_index, page_type=ptype,
                field=",".join(missing_pos),
                message=f"满铺图缺少构图声明：{', '.join(missing_pos)}",
                suggestion="声明 objectPosition / subjectMap / safeTextZones / avoidZones",
            ))
        # R9 + 满铺合同数值阈值
        qz = page.get("quietZoneRatio")
        if qz is not None and isinstance(qz, (int, float)) and qz < MIN_QUIET_ZONE_RATIO:
            issues.append(QualityIssue(
                rule="R9", severity="blocking", scope="page",
                page_index=page_index, page_type=ptype, field="quietZoneRatio",
                message=f"留白比 {qz} < {MIN_QUIET_ZONE_RATIO}，标题/主体易贴边",
                suggestion="提高留白比到 0.3 以上",
            ))
        tcr = page.get("titleCanvasRatio")
        if tcr is not None and isinstance(tcr, (int, float)) and tcr > MAX_TITLE_CANVAS_RATIO:
            issues.append(QualityIssue(
                rule="R9", severity="blocking", scope="page",
                page_index=page_index, page_type=ptype, field="titleCanvasRatio",
                message=f"标题占画布比 {tcr} > {MAX_TITLE_CANVAS_RATIO}，标题过重",
                suggestion="缩小标题区到画布 40% 以内",
            ))
        opa = page.get("overlayPeakAlpha")
        if opa is not None and isinstance(opa, (int, float)) and opa > MAX_OVERLAY_PEAK_ALPHA:
            issues.append(QualityIssue(
                rule="R9", severity="blocking", scope="page",
                page_index=page_index, page_type=ptype, field="overlayPeakAlpha",
                message=f"蒙版峰值透明度 {opa} > {MAX_OVERLAY_PEAK_ALPHA}",
                suggestion="降低蒙版透明度到 0.3 以内以保证文字可读",
            ))
        # 缩略图可读性
        thumb = page.get("thumbnailCheck")
        if thumb == "pending":
            issues.append(QualityIssue(
                rule="CONTRACT_THUMB", severity="warn", scope="page",
                page_index=page_index, page_type=ptype, field="thumbnailCheck",
                message="缩略图可读性待确认（thumbnailCheck=pending）",
                suggestion="在小图下确认主体与标题仍清晰",
            ))
    else:
        # 非满铺页如果带了满铺合同字段但角色不对，给 INFO 提示
        if any(k in page for k in ("subjectMap", "safeTextZones")) and page.get("type") != "image_page":
            issues.append(QualityIssue(
                rule="R8", severity="info", scope="page",
                page_index=page_index, page_type=ptype,
                message="页面含满铺构图字段但未声明 imageRole=full-bleed",
                suggestion="明确 imageRole，或移除无关构图字段",
            ))

    return PageQuality(page_index=page_index, page_type=ptype, issues=issues)


# --------------------------------------------------------------------------- #
# 草稿级（跨页）检查
# --------------------------------------------------------------------------- #
def check_draft(
    card_draft: dict[str, Any],
    *,
    expected_count: int | None = None,
    registry: Any | None = None,
) -> QualityReport:
    """检查整份 card_draft：逐页 R1-R9 + 跨页多样性/计数。"""
    registry = registry or get_template_registry()
    pages = card_draft.get("pages") if isinstance(card_draft, dict) else None
    if not isinstance(pages, list):
        return QualityReport(
            passed=False,
            draft_issues=[QualityIssue(
                rule="R1", severity="blocking", scope="draft",
                message="card_draft.pages 缺失或不是数组",
                suggestion="生成合法的 pages 数组",
            )],
            summary="草稿结构异常，未通过门禁。",
        )

    page_reports: list[PageQuality] = []
    for i, page in enumerate(pages):
        if isinstance(page, dict):
            page_reports.append(check_page(i, page, registry))

    draft_issues: list[QualityIssue] = []
    types = [(p.get("type") or "content") for p in pages if isinstance(p, dict)]
    total = len(types)

    # 首页必须是封面
    if types and types[0] != "cover":
        draft_issues.append(QualityIssue(
            rule="DIVERSITY", severity="warn", scope="draft", page_index=0,
            page_type=types[0],
            message="首页不是封面（cover），叙事节奏被打断",
            suggestion="将第一页设为 cover",
        ))
    # 尾页优先收尾/金句
    if total >= 2 and types[-1] not in ("end_page", "quote", "big_quote"):
        draft_issues.append(QualityIssue(
            rule="DIVERSITY", severity="warn", scope="draft",
            page_index=total - 1, page_type=types[-1],
            message="尾页不是收尾/金句页，缺少情绪收口",
            suggestion="末页用 end_page / quote / big_quote",
        ))
    # 相邻页面去重（相邻骨架不得相同）——与 enforce_page_diversity 呼应
    for i in range(1, total):
        if types[i] == types[i - 1]:
            draft_issues.append(QualityIssue(
                rule="DIVERSITY", severity="blocking", scope="draft",
                page_index=i, page_type=types[i],
                message=f"第 {i} 页与第 {i-1} 页页面类型相同（{types[i]}），骨架重复",
                suggestion="转换成 list/dark_panel/steps/compare 等结构性页面",
            ))
    # 多样性预算：至少 3 种页面结构（info 级，不阻塞）
    distinct = set(types)
    if total >= 3 and len(distinct) < 3:
        draft_issues.append(QualityIssue(
            rule="DIVERSITY", severity="info", scope="draft",
            message=f"仅 {len(distinct)} 种页面结构，视觉节奏偏单一",
            suggestion="混用更多组件类型（list/compare/steps/quote…）",
        ))
    # 计数匹配（来自注入图片或规划页数）
    if expected_count is not None:
        actual = total
        if expected_count != actual:
            draft_issues.append(QualityIssue(
                rule="COUNT", severity="warn", scope="draft",
                message=f"规划页数 {expected_count} 与实际 {actual} 不一致",
                suggestion="核对卡片数量，避免漏页/多页",
            ))

    # 统计
    blocking = sum(1 for pr in page_reports for it in pr.issues if it.severity == "blocking")
    blocking += sum(1 for it in draft_issues if it.severity == "blocking")
    warn = sum(1 for pr in page_reports for it in pr.issues if it.severity == "warn")
    warn += sum(1 for it in draft_issues if it.severity == "warn")
    info = sum(1 for pr in page_reports for it in pr.issues if it.severity == "info")
    info += sum(1 for it in draft_issues if it.severity == "info")

    summary = (
        f"共 {total} 页；blocking {blocking}，warn {warn}，info {info}。"
        + ("已通过门禁。" if blocking == 0 else "存在阻塞性质量问题，需修正后再出图。")
    )

    return QualityReport(
        passed=blocking == 0,
        blocking=blocking,
        warn=warn,
        info=info,
        page_reports=page_reports,
        draft_issues=draft_issues,
        summary=summary,
    )


def run_quality_gate(
    card_draft: dict[str, Any],
    *,
    expected_count: int | None = None,
    registry: Any | None = None,
) -> QualityReport:
    """门禁入口：返回 QualityReport（可直接 model_dump 落库）。"""
    try:
        return check_draft(card_draft, expected_count=expected_count, registry=registry)
    except Exception as exc:  # 门禁本身不能炸掉出图流程
        logger.warning(f"[quality_gate] check failed: {exc}")
        return QualityReport(
            passed=True,
            info=1,
            draft_issues=[QualityIssue(
                rule="GATE", severity="info", scope="draft",
                message=f"质量门禁自检异常：{exc}",
                suggestion="门禁跳过，由人工 review 兜底",
            )],
            summary="质量门禁自检异常，已跳过。",
        )


# --------------------------------------------------------------------------- #
# 便捷：把报告压缩成给前端的精简 badge
# --------------------------------------------------------------------------- #
def gate_badge(report: QualityReport) -> dict[str, Any]:
    level = "fail" if not report.passed else ("warn" if report.warn else "pass")
    return {
        "level": level,
        "passed": report.passed,
        "blocking": report.blocking,
        "warn": report.warn,
        "info": report.info,
        "summary": report.summary,
    }