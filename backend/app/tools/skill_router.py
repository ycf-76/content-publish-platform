"""Skill 智能路由架构。

三层路由策略解决 Skills 数量增长后的 LLM 选择问题：
  A. 两级路由 — system prompt 展示分类摘要，LLM 先选大类再选具体 Skill
  B. trigger_words 预筛 — 关键词匹配缩小候选集，减少 LLM 选择空间
  C. 分组加载 — hot/warm/cold 三档优先级，按需注入 tools schema

新增 Skill 时只需在 .md frontmatter 中设置 category 和 priority：
  ---
  node_type: plan
  name: my_new_skill
  category: create        # 可选，不设则从 node_type 推断
  priority: hot           # 可选，不设则从 category 推断
  ---

不设 category/priority 时自动推断，零配置也能工作。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SkillCategory(str, Enum):
    CREATE = "create"
    ANALYZE = "analyze"
    OPERATE = "operate"
    AUDIT = "audit"
    DEV = "dev"
    PLATFORM = "platform"


class SkillPriority(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass(frozen=True)
class CategoryMeta:
    label: str
    icon: str
    description: str


CATEGORY_META: dict[SkillCategory, CategoryMeta] = {
    SkillCategory.CREATE: CategoryMeta("创作", "🎨", "文案/卡片/图文/视频脚本"),
    SkillCategory.ANALYZE: CategoryMeta("分析", "🔍", "诊断/复盘/数据/竞品分析"),
    SkillCategory.OPERATE: CategoryMeta("运营", "📊", "画像/排期/热点/策略"),
    SkillCategory.AUDIT: CategoryMeta("审核", "🛡", "风险/合规/质量门禁"),
    SkillCategory.DEV: CategoryMeta("开发", "🛠", "文件/浏览器/工作流"),
    SkillCategory.PLATFORM: CategoryMeta("平台", "🔌", "微信/飞书等外部平台"),
}

NODE_TYPE_TO_CATEGORY: dict[str, SkillCategory] = {
    "plan": SkillCategory.OPERATE,
    "copywrite": SkillCategory.CREATE,
    "produce": SkillCategory.CREATE,
    "image_gen": SkillCategory.CREATE,
    "audit": SkillCategory.AUDIT,
    "analyze": SkillCategory.ANALYZE,
    "attribute": SkillCategory.ANALYZE,
    "discover": SkillCategory.ANALYZE,
    "search": SkillCategory.OPERATE,
    "publish": SkillCategory.OPERATE,
    "format": SkillCategory.CREATE,
    "caption_hashtag": SkillCategory.CREATE,
    "card_design": SkillCategory.CREATE,
    "social_content": SkillCategory.CREATE,
    "condense": SkillCategory.CREATE,
    "polish": SkillCategory.CREATE,
    "topic_evaluator": SkillCategory.ANALYZE,
    "quality_gate": SkillCategory.AUDIT,
    "dev": SkillCategory.DEV,
    "file": SkillCategory.DEV,
    "workflow": SkillCategory.DEV,
    "browser": SkillCategory.DEV,
    "web": SkillCategory.OPERATE,
    "wechat": SkillCategory.PLATFORM,
    "feishu": SkillCategory.PLATFORM,
    "wechat_send_file": SkillCategory.PLATFORM,
    "wechat_send_text": SkillCategory.PLATFORM,
    "feishu_file_ops": SkillCategory.PLATFORM,
    "feishu_wiki_doc": SkillCategory.PLATFORM,
}

CATEGORY_DEFAULT_PRIORITY: dict[SkillCategory, SkillPriority] = {
    SkillCategory.CREATE: SkillPriority.HOT,
    SkillCategory.OPERATE: SkillPriority.HOT,
    SkillCategory.ANALYZE: SkillPriority.WARM,
    SkillCategory.AUDIT: SkillPriority.WARM,
    SkillCategory.DEV: SkillPriority.COLD,
    SkillCategory.PLATFORM: SkillPriority.COLD,
}


def infer_category(skill: Any) -> SkillCategory:
    explicit = getattr(skill, "skill_category", "") or ""
    if explicit:
        try:
            return SkillCategory(explicit)
        except ValueError:
            pass
    nt = getattr(skill, "node_type", "") or ""
    return NODE_TYPE_TO_CATEGORY.get(nt, SkillCategory.OPERATE)


def infer_priority(skill: Any, category: SkillCategory | None = None) -> SkillPriority:
    explicit = getattr(skill, "skill_priority", "") or ""
    if explicit:
        try:
            return SkillPriority(explicit)
        except ValueError:
            pass
    cat = category or infer_category(skill)
    return CATEGORY_DEFAULT_PRIORITY.get(cat, SkillPriority.WARM)


@dataclass
class RoutingResult:
    selected_skills: list[Any]
    category_hint: str
    trigger_matched_skills: list[str]
    trigger_matched_categories: list[str]
    total_available: int
    total_selected: int


class SkillRouter:
    """Skill 智能路由器。

    组合三层策略：
    1. C 分组加载 — hot 始终注入，warm 按类别命中注入，cold 仅触发词命中注入
    2. B trigger_words 预筛 — 匹配用户消息的触发词，提升对应类别
    3. A 两级路由 — system prompt 中展示分类摘要，LLM 按类决策
    """

    def __init__(self, max_tools: int = 50) -> None:
        self.max_tools = max_tools

    def select_skills(
        self,
        all_skills: list[Any],
        user_message: str,
    ) -> RoutingResult:
        """Trigger 匹配 + 分类提示。

        不再做 priority/category 过滤（_build_tools_schema 全量注入），
        只负责：
        1. 匹配 trigger_words → 标记 triggered Skills
        2. 生成 category_hint（system prompt 里的分类摘要）
        """
        msg_lower = user_message.lower()

        skill_info: list[dict[str, Any]] = []
        for s in all_skills:
            cat = infer_category(s)
            pri = infer_priority(s, cat)
            skill_info.append({"skill": s, "category": cat, "priority": pri})

        trigger_matched_names: set[str] = set()
        trigger_matched_cats: set[SkillCategory] = set()
        for info in skill_info:
            triggers = getattr(info["skill"], "trigger_words", []) or []
            matched = False
            for tw in triggers:
                if not tw or not isinstance(tw, str):
                    continue
                tw_lower = tw.lower()
                if tw_lower in msg_lower:
                    matched = True
                    break
                if len(tw_lower) >= 2 and tw_lower in msg_lower:
                    matched = True
                    break
            if not matched:
                for tw in triggers:
                    if not tw or not isinstance(tw, str):
                        continue
                    tw_lower = tw.lower()
                    core_chars = [c for c in tw_lower if c.strip() and '\u4e00' <= c <= '\u9fff']
                    if len(core_chars) >= 2:
                        overlap = sum(1 for c in core_chars if c in msg_lower)
                        if overlap / len(core_chars) >= 0.6:
                            matched = True
                            break
            if matched:
                trigger_matched_names.add(getattr(info["skill"], "name", ""))
                trigger_matched_cats.add(info["category"])

        category_hint = self._build_category_hint(skill_info, trigger_matched_cats)

        return RoutingResult(
            selected_skills=all_skills,
            category_hint=category_hint,
            trigger_matched_skills=sorted(trigger_matched_names),
            trigger_matched_categories=[c.value for c in sorted(trigger_matched_cats, key=lambda c: c.value)],
            total_available=len(all_skills),
            total_selected=len(all_skills),
        )

    def _build_category_hint(
        self,
        skill_info: list[dict[str, Any]],
        active_categories: set[SkillCategory],
    ) -> str:
        cat_counts: dict[SkillCategory, int] = {}
        for info in skill_info:
            cat = info["category"]
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        lines: list[str] = []
        for cat in SkillCategory:
            meta = CATEGORY_META[cat]
            count = cat_counts.get(cat, 0)
            if count == 0:
                continue
            marker = "●" if cat in active_categories else "○"
            lines.append(f"{marker} **{meta.icon} {meta.label}**（{count}个）：{meta.description}")

        if active_categories:
            active_labels = [CATEGORY_META[c].label for c in active_categories]
            lines.append(f"\n> 当前请求可能涉及：{'、'.join(active_labels)}类，已自动加载对应工具")

        return "\n".join(lines)

    MAX_SKILL_COUNT = 150
    MAX_CHARS = 18000
    DESC_COMPACT_MAX = 220

    def build_routing_table(self, selected_skills: list[Any]) -> str:
        if not selected_skills:
            return "- (当前无可用工具，直接回答用户问题)"

        skills = selected_skills[: self.MAX_SKILL_COUNT]
        truncated_count = len(selected_skills) - len(skills)

        grouped: dict[SkillCategory, list[Any]] = {}
        for s in skills:
            cat = infer_category(s)
            grouped.setdefault(cat, []).append(s)

        lines: list[str] = []
        for cat in SkillCategory:
            group = grouped.get(cat, [])
            if not group:
                continue
            meta = CATEGORY_META[cat]
            lines.append(f"\n### {meta.icon} {meta.label}")
            for s in group:
                name = getattr(s, "name", "?")
                display = getattr(s, "display_name", "") or name
                desc = getattr(s, "description", "") or ""
                triggers = getattr(s, "trigger_words", []) or []
                short_desc = desc[:80] + "…" if len(desc) > 80 else desc
                line = f"- **{display}** (`{name}`): {short_desc}"
                if triggers:
                    trigger_str = "、".join(f"「{t}」" for t in triggers[:5])
                    line += f"  — 触发词：{trigger_str}"
                lines.append(line)

        result = "\n".join(lines)

        if len(result) <= self.MAX_CHARS:
            if truncated_count > 0:
                result += f"\n\n⚠️ Skills truncated: included {len(skills)} of {len(selected_skills)}"
            return result

        result = self._compact_routing_table(skills, grouped)
        if truncated_count > 0:
            total = len(selected_skills)
            included = len(skills)
            result += f"\n\n⚠️ Skills truncated: included {included} of {total}"
        return result

    def _compact_routing_table(
        self,
        skills: list[Any],
        grouped: dict[SkillCategory, list[Any]],
    ) -> str:
        """二叉搜索缩短描述，使路由表字符数 ≤ MAX_CHARS。"""
        lo, hi = 20, 80
        best_lines: list[str] | None = None
        for _ in range(6):
            mid = (lo + hi) // 2
            lines = self._build_routing_lines(grouped, desc_limit=mid, trigger_limit=3)
            text = "\n".join(lines)
            if len(text) <= self.MAX_CHARS:
                best_lines = lines
                hi = mid
            else:
                lo = mid + 1

        if best_lines is not None:
            return "\n".join(best_lines)

        lines = self._build_routing_lines(grouped, desc_limit=self.DESC_COMPACT_MAX, trigger_limit=0)
        text = "\n".join(lines)
        if len(text) <= self.MAX_CHARS:
            return text

        kept: list[str] = []
        total = 0
        for line in lines:
            if total + len(line) + 1 > self.MAX_CHARS:
                break
            kept.append(line)
            total += len(line) + 1
        return "\n".join(kept)

    def _build_routing_lines(
        self,
        grouped: dict[SkillCategory, list[Any]],
        desc_limit: int = 80,
        trigger_limit: int = 5,
    ) -> list[str]:
        lines: list[str] = []
        for cat in SkillCategory:
            group = grouped.get(cat, [])
            if not group:
                continue
            meta = CATEGORY_META[cat]
            lines.append(f"\n### {meta.icon} {meta.label}")
            for s in group:
                name = getattr(s, "name", "?")
                display = getattr(s, "display_name", "") or name
                desc = getattr(s, "description", "") or ""
                triggers = getattr(s, "trigger_words", []) or []
                short_desc = desc[:desc_limit] + "…" if len(desc) > desc_limit else desc
                line = f"- **{display}** (`{name}`): {short_desc}"
                if triggers and trigger_limit > 0:
                    trigger_str = "、".join(f"「{t}」" for t in triggers[:trigger_limit])
                    line += f"  — 触发词：{trigger_str}"
                lines.append(line)
        return lines

    def build_category_summary_for_system_prompt(
        self,
        all_skills: list[Any],
        active_categories: set[SkillCategory] | None = None,
    ) -> str:
        cat_counts: dict[SkillCategory, int] = {}
        for s in all_skills:
            cat = infer_category(s)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        parts: list[str] = []
        for cat in SkillCategory:
            meta = CATEGORY_META[cat]
            count = cat_counts.get(cat, 0)
            if count == 0:
                continue
            active = (active_categories or set()) and cat in (active_categories or set())
            marker = "●" if active else "○"
            parts.append(f"{marker} {meta.icon}{meta.label}({count})")

        return " | ".join(parts)

    COMPACT_DESC_MAX = 50
    COMPACT_CATALOG_MAX_CHARS = 5000

    def build_compact_catalog(self, all_skills: list[Any], callable_names: frozenset[str] | None = None) -> str:
        """全量紧凑目录：每个 Skill 一行摘要，按 category 分组。

        用途：注入 system prompt 的 {skill_routing} 占位符，
        让 LLM 看到全部可用工具的一行概览。

        callable_names: tools_schema 中实际可调用的 skill 名集。
            若提供，只列出这些 Skill，保证 catalog 与 tools_schema 一致，
            避免 LLM 看到目录里有但调不了的情况。
        """
        if not all_skills:
            return "- (当前无可用工具)"

        skills_to_list = all_skills
        if callable_names is not None:
            skills_to_list = [s for s in all_skills if getattr(s, "name", "") in callable_names]

        grouped: dict[SkillCategory, list[Any]] = {}
        for s in skills_to_list:
            cat = infer_category(s)
            grouped.setdefault(cat, []).append(s)

        lines: list[str] = []
        for cat in SkillCategory:
            group = grouped.get(cat, [])
            if not group:
                continue
            meta = CATEGORY_META[cat]
            lines.append(f"### {meta.icon} {meta.label}（{len(group)}个）")
            for s in group:
                name = getattr(s, "name", "?")
                display = getattr(s, "display_name", "") or name
                desc = getattr(s, "description", "") or ""
                short = desc[:self.COMPACT_DESC_MAX] + "…" if len(desc) > self.COMPACT_DESC_MAX else desc
                lines.append(f"- {display}(`{name}`): {short}")
            lines.append("")

        result = "\n".join(lines)
        if len(result) > self.COMPACT_CATALOG_MAX_CHARS:
            result = result[:self.COMPACT_CATALOG_MAX_CHARS] + "\n\n⚠️ 工具目录已截断"
        return result