"""Content planning and template matching for image_plan_node.

Phase 2:
- Prompt page types and fields are generated from TemplateRegistry.
- LLM outputs only semantic pages, not template selection.
- TemplateMatcher chooses template, decoration, and format plan.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

try:
    from app.templates.registry import TemplateRegistry, get_template_registry
except ImportError:
    TemplateRegistry = None
    def get_template_registry():
        return None

logger = logging.getLogger(__name__)


_EXAMPLE_VALUES: dict[str, Any] = {
    "title": "示例标题",
    "subtitle": "示例副标题",
    "footer": "@灵犀工坊",
    "highlight": "高亮词",
    "tag": "干货分享",
    "content": "示例正文段落",
    "listItems": ["要点一", "要点二", "要点三"],
    "emoji": "🚀",
    "decoNumber": "01",
    "ctaText": "关注我，获取更多",
    "compareLeftTitle": "传统做法",
    "compareRightTitle": "更好方式",
    "compareLeftItems": ["痛点一", "痛点二"],
    "compareRightItems": ["优势一", "优势二"],
    "iconTextPairs": [{"icon": "🎯", "text": "描述"}],
    "steps": [{"title": "步骤名", "desc": "步骤描述"}],
    "codeContent": "print('hello')",
    "codeLang": "python",
    "numberedItems": [{"title": "要点", "desc": "描述"}],
    "masthead": "THE DAILY BRIEF",
    "newspaperCols": [{"headline": "栏目标题", "body": "栏目正文"}],
}


def _schema_section() -> str:
    registry = get_template_registry()
    lines: list[str] = []
    for page_type in registry.list_page_types():
        fields = registry.page_type_fields(page_type)
        example: dict[str, Any] = {"type": page_type}
        for field in fields:
            example[field.key] = _EXAMPLE_VALUES.get(field.key, _example_for_type(field.type))
        lines.append("    " + json.dumps(example, ensure_ascii=False) + ",")
    return "\n".join(lines)


def _example_for_type(field_type: str) -> Any:
    if field_type == "array":
        return []
    if field_type == "text":
        return "示例文本"
    return "示例"


def build_content_plan_prompt(
    *,
    topic: str,
    title: str,
    content: str,
    tags: list[str],
    key_points: list[str],
    visual_suggestion: str,
    available_page_types: list[str] | None = None,
) -> str:
    visual_hint = (
        f"\n**配图风格建议**（来自分析节点，卡片文案风格应与此一致）:\n{visual_suggestion}\n"
        if visual_suggestion
        else ""
    )
    tag_text = ", ".join(tags) if isinstance(tags, list) else str(tags)
    key_point_text = ", ".join(key_points) if isinstance(key_points, list) and key_points else "无"

    available_types = available_page_types or get_template_registry().all_page_types()

    try:
        from app.templates.component_catalog import catalog_prompt_section

        component_section = catalog_prompt_section(available_types)
    except Exception:
        component_section = ""

    return (
        "你是小红书卡片文案编排师。你的核心任务是把下面的文案全文拆分编排到 4-6 张卡片中，\n"
        "每张卡都要有实质内容，不能留空。读者看完所有卡片等于读完原文。\n\n"
        "编排原则：\n"
        "1. 第 1 张封面（cover）：原文标题 + 吸引眼球的副标题 + 署名\n"
        "2. 中间页把原文正文按逻辑段落拆分，每页放 2-3 句或 1 个完整段落，选择最合适的页面类型\n"
        "3. 最后 1 张尾页（end_page）：一句让人记住你的话 + CTA\n"
        "【视觉多样性硬性要求】\n"
        "- 不要把所有中间页都排成 content；相邻两张不能使用相同页面类型\n"
        "- 要点罗列优先 list / dark_panel / numbered_cards\n"
        "- 有先后顺序优先 steps；有并列知识点优先 icon_text\n"
        "- 有前后差异或新旧做法优先 compare；有数据或栏目感优先 newspaper\n"
        "- 收尾可用 quote / big_quote / end_page，但不要与前一页同类型\n"
        f"{visual_hint}\n"
        "【关键要求】\n"
        "- 你必须把原文内容编排进每张卡的 content/listItems/steps 等字段中，不能只写标题不写正文\n"
        "- 每张 content 页的 content 字段必须有 2-3 段实际文案，总字数 50-120 字\n"
        "- 每张 list/dark_panel 页的 listItems 必须有 3-5 条实际要点，每条 10-30 字\n"
        "- 内容要精炼，不要把整段原文照搬，要提炼要点、保留核心信息\n"
        "- 读者看完所有卡 = 读完原文核心内容，不能遗漏重要内容\n\n"
        "可用的页面类型和字段由模板注册表提供，如下所示：\n"
        f"{_schema_section()}\n\n"
        f"{component_section}"
        "严格输出以下 JSON 格式（不要输出其他内容，不要 markdown 代码块）：\n"
        '{\n'
        '  "pages": [\n'
        '    {"type": "cover", "title": "封面标题", "subtitle": "副标题", "footer": "@灵犀工坊"}\n'
        '  ]\n'
        '}\n\n'
        "注意：pages 数组中只需包含实际需要的页面类型，不必每种都用。"
        "每页字段必须来自上面的模板注册表定义，不得自行发明新字段。\n\n"
        f"主题：{topic}\n"
        f"标题：{title}\n"
        f"正文（必须全部编排进卡片，不能遗漏）：\n{content}\n"
        f"标签：{tag_text}\n"
        f"要点：{key_point_text}\n"
    )


class TemplateMatcher:
    """Select template, decoration, and format plan deterministically."""

    def __init__(self, registry: TemplateRegistry | None = None) -> None:
        self._registry = registry or get_template_registry()

    def match_template(self, topic: str, content_type: str = "") -> str:
        category_map = {
            "清单型": "知识",
            "教程型": "知识",
            "观点型": "科技",
            "对比型": "生活方式",
            "叙事型": "生活方式",
        }
        if content_type in category_map:
            matches = self._registry.list(category=category_map[content_type])
            if matches:
                return matches[0].id

        text = (topic or "").lower()
        best_id = self._registry.default_template_id()
        best_score = 0
        for template in self._registry.list():
            score = sum(
                1 for keyword in template.category_keywords if keyword.lower() in text
            )
            if score > best_score:
                best_id = template.id
                best_score = score

        return best_id

    def match_decoration(self, template_id: str, content_type: str = "") -> dict[str, Any]:
        manifest = self._registry.get(template_id)
        base = (
            manifest.default_decoration
            if manifest and manifest.default_decoration
            else {
                "type": "none",
                "color1": "#2B7FD8",
                "color2": "#F4D758",
                "opacity": 0.2,
            }
        )
        overrides = {
            ("清单型", "教程型"): {
                "type": "noise",
                "color1": "#92400E",
                "color2": "#78716C",
                "opacity": 0.06,
                "param1": 0.5,
                "param2": 1,
            },
            "观点型": {
                "type": "geometric",
                "color1": "#818CF8",
                "color2": "#F472B6",
                "opacity": 0.15,
                "param1": 0.6,
                "param2": -15,
            },
            ("对比型", "叙事型"): {
                "type": "gradient_orbs",
                "color1": "#FDE68A",
                "color2": "#FCA5A5",
                "opacity": 0.35,
                "param1": 0.25,
                "param2": 0.65,
            },
        }
        for key, decoration in overrides.items():
            keys = key if isinstance(key, tuple) else (key,)
            if content_type in keys:
                return decoration
        return base

    def build_format_plan(
        self,
        *,
        page_count: int,
        template_id: str,
        platform: str = "xiaohongshu",
        format_name: str | None = None,
    ) -> dict[str, Any]:
        platform_data = self._registry.resolve_platform_format(platform, format_name)
        return {
            **platform_data,
            "page_count": page_count,
            "pages": [
                {
                    "index": index,
                    "source": "template",
                    "template_id": template_id,
                }
                for index in range(page_count)
            ],
        }


# 允许的页面位置：避免封面/尾页出现在中间，也避免普通正文页连续堆叠
_ROLE_ALLOWED_AT: dict[str, tuple[str, ...]] = {
    "cover": ("first",),
    "end_page": ("last",),
    "quote": ("last", "middle"),
    "big_quote": ("last", "middle"),
    # 清单/面板结构不适合做收尾页，收尾需要情绪或行动号召
    "list": ("middle",),
    "dark_panel": ("middle",),
    "numbered_cards": ("middle",),
    "steps": ("middle",),
    "compare": ("middle",),
    "icon_text": ("middle",),
    "newspaper": ("middle",),
}

# 当页面重复或类型不适合当前内容时，优先转换为这些结构性页面
_STRUCTURED_FALLBACKS: tuple[str, ...] = (
    "dark_panel",
    "list",
    "steps",
    "numbered_cards",
    "quote",
    "big_quote",
    "compare",
    "content",
)

_STRUCTURED_PAGE_TYPES: tuple[str, ...] = _STRUCTURED_FALLBACKS


def _split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？；\n":
            if buf.strip():
                parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _convert_page(
    registry: TemplateRegistry,
    template_id: str,
    page: dict[str, Any],
    target_type: str,
) -> dict[str, Any] | None:
    """把一个页面转换为目标页面类型，尽量保留原有文案。

    转换失败（模板不支持该类型，或转换后没有实质内容）时返回 None。
    """
    if not registry.supports_page_type(template_id, target_type):
        return None

    title = page.get("title") or ""
    content = page.get("content") or ""
    items = page.get("listItems")
    if isinstance(items, list) and items:
        list_items = [str(i) for i in items]
    else:
        list_items = _split_sentences(content)

    values: dict[str, Any] = {"type": target_type, "title": title}

    if target_type in ("list", "dark_panel"):
        values["listItems"] = list_items or [content or title or "要点"]
        if target_type == "dark_panel":
            values["emoji"] = values.get("emoji") or "💡"
            values["decoNumber"] = values.get("decoNumber") or "01"
    elif target_type == "steps":
        values["steps"] = [
            {"title": f"步骤 {i + 1}", "desc": item}
            for i, item in enumerate((list_items or [content])[:5])
        ]
    elif target_type == "numbered_cards":
        values["numberedItems"] = [
            {"title": f"要点 {i + 1}", "desc": item}
            for i, item in enumerate((list_items or [content])[:5])
        ]
    elif target_type in ("quote", "big_quote"):
        quote_text = list_items[0] if list_items else content
        # 金句要短，超过 40 字就截取第一句/前半段
        if len(quote_text) > 40:
            quote_text = _split_sentences(quote_text)[0][:40] or quote_text[:40]
        values["content"] = quote_text
        values["footer"] = page.get("footer") or "@灵犀工坊"
        values["decoNumber"] = values.get("decoNumber") or '"'
    elif target_type == "compare":
        half = max(1, (len(list_items or []) + 1) // 2)
        values["compareLeftTitle"] = "常见问题"
        values["compareRightTitle"] = "更好做法"
        values["compareLeftItems"] = (list_items or [content])[:half]
        values["compareRightItems"] = (list_items or [content])[half:] or ["持续优化"]
    else:
        values["content"] = content or " ".join(list_items)

    converted = _page_from_fields(registry, template_id, target_type, values)
    converted["type"] = target_type
    if target_type in ("list", "dark_panel"):
        if not converted.get("listItems"):
            return None
    elif target_type in ("steps", "numbered_cards"):
        if not converted.get("steps") and not converted.get("numberedItems"):
            return None
    elif target_type == "compare":
        if not converted.get("compareLeftItems") and not converted.get("compareRightItems"):
            return None
    elif not converted.get("content"):
        return None
    return converted


def _fallback_order(
    registry: TemplateRegistry,
    template_id: str,
    current_type: str,
    neighbour_type: str | None,
    position: str,
) -> list[str]:
    """候选转换目标：模板支持、不与相邻页重复、符合页面位置。"""
    candidates: list[str] = []
    for target in _STRUCTURED_FALLBACKS:
        if target == current_type or target == neighbour_type:
            continue
        if position not in _ROLE_ALLOWED_AT.get(target, ("first", "middle", "last")):
            continue
        if not registry.supports_page_type(template_id, target):
            continue
        candidates.append(target)
    return candidates


def enforce_page_diversity(
    card_draft: dict[str, Any],
    registry: TemplateRegistry,
    template_id: str,
) -> dict[str, Any]:
    """保证一组图文有足够的视觉节奏，不退化成单一骨架。

    规则：
    1. 首页必须是封面；
    2. 尾页优先是收尾页或金句页；
    3. 相邻页面不能使用相同 page type；
    4. 普通 content 页连续出现时，转换为结构性页面；
    5. 整体去重后仍不足 3 种页面类型时，继续转换中间页。
    """
    pages = card_draft.get("pages")
    if not isinstance(pages, list) or len(pages) < 2:
        return card_draft

    total = len(pages)
    seen: set[str] = set()

    for idx in range(1, total):
        page = pages[idx]
        if not isinstance(page, dict):
            continue
        ptype = page.get("type") or "content"
        prev = pages[idx - 1] if idx > 0 else None
        prev_type = (prev or {}).get("type") if isinstance(prev, dict) else None
        position = "first" if idx == 0 else ("last" if idx == total - 1 else "middle")

        allowed = _ROLE_ALLOWED_AT.get(ptype, ("first", "middle", "last"))
        needs_convert = (
            position not in allowed
            or ptype == prev_type
            or (ptype == "content" and prev_type == "content")
        )
        if not needs_convert:
            continue

        for target in _fallback_order(registry, template_id, ptype, prev_type, position):
            converted = _convert_page(registry, template_id, page, target)
            if converted:
                pages[idx] = converted
                break

    # 多样性预算：尽量保证至少 3 种页面结构
    for _ in range(3):
        types = {
            (p.get("type") or "content")
            for p in pages
            if isinstance(p, dict)
        }
        if len(types) >= min(3, total):
            break
        changed = False
        for idx in range(1, total - 1):
            page = pages[idx]
            if not isinstance(page, dict):
                continue
            ptype = page.get("type") or "content"
            prev_type = (pages[idx - 1] or {}).get("type") if isinstance(pages[idx - 1], dict) else None
            next_type = (pages[idx + 1] or {}).get("type") if isinstance(pages[idx + 1], dict) else None
            for target in _STRUCTURED_FALLBACKS:
                if target == ptype or target == prev_type or target == next_type:
                    continue
                if target in types:
                    continue
                converted = _convert_page(registry, template_id, page, target)
                if converted:
                    pages[idx] = converted
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break

    card_draft["pages"] = pages
    card_draft["page_types"] = [
        (p.get("type") or "content") for p in pages if isinstance(p, dict)
    ]
    seen.clear()
    return card_draft


def _page_from_fields(
    registry: TemplateRegistry,
    template_id: str,
    page_type: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Build a page using only fields supported by the selected template."""
    field_names = registry.field_names_for_page(template_id, page_type)
    return {
        key: values[key]
        for key in field_names
        if key in values
    }


def _build_structured_draft(
    *,
    registry: TemplateRegistry,
    topic: str,
    title: str,
    structured_items: list[dict[str, Any]],
    suggested_template: str,
) -> dict[str, Any]:
    items_per_page = 4
    cover_values: dict[str, Any] = {
        "type": "cover",
        "title": title[:40] if title else topic,
        "subtitle": f"共 {len(structured_items)} 个知识点",
        "footer": "@灵犀工坊",
        "highlight": "",
        "tag": "知识清单",
    }
    cover = _page_from_fields(
        registry,
        suggested_template,
        "cover",
        cover_values,
    )
    cover["type"] = "cover"

    pages: list[dict[str, Any]] = [cover]
    for i in range(0, len(structured_items), items_per_page):
        chunk = structured_items[i : i + items_per_page]
        list_items = [
            f"{item.get('term', '')}：{item.get('definition', '')}"
            for item in chunk
            if item.get("term")
        ]
        if list_items:
            list_page = _page_from_fields(
                registry,
                suggested_template,
                "list",
                {
                    "title": f"{topic}（{i + 1}-{i + len(list_items)}）",
                    "listItems": list_items,
                    "footer": (
                        f"第 {len(pages)}/"
                        f"{((len(structured_items) - 1) // items_per_page) + 2} 页"
                    ),
                },
            )
            list_page["type"] = "list"
            pages.append(list_page)

    if registry.supports_page_type(suggested_template, "end_page"):
        end_page = _page_from_fields(
            registry,
            suggested_template,
            "end_page",
            {
                "title": "",
                "content": f"掌握 {len(structured_items)} 个知识点，让{topic}不再难。",
                "footer": "@灵犀工坊",
                "ctaText": "关注我，获取更多知识",
                "decoNumber": '"',
            },
        )
        end_page["type"] = "end_page"
        pages.append(end_page)

    return {"pages": pages, "suggested_template": suggested_template}


def build_cover_only_prompt(
    *,
    topic: str,
    style: str = "",
    title: str | None = None,
) -> str:
    """封面专用 prompt：只生成 1 张 cover 页，不需要全文编排。

    对话式创作场景：用户说"帮我做个美食封面"，没有完整文案，
    只需要生成封面卡片的内容 + 选择模板 + 选择装饰。
    """
    style_hint = f"\n风格要求：{style}" if style else ""
    title_instruction = (
        f"标题已确定：{title}"
        if title
        else "请生成一个吸引眼球的标题（15-20字，可用1-2个emoji）"
    )

    registry = get_template_registry()
    template_list = ", ".join(
        f"{t.id}({t.name})"
        for t in registry.list()
    )

    return (
        "你是小红书封面设计师。根据主题和风格生成 1 张封面卡片的内容。\n\n"
        f"主题：{topic}\n"
        f"{title_instruction}\n"
        f"{style_hint}\n\n"
        "【关键要求】\n"
        "- title: 15-20字，有吸引力，可用1-2个emoji\n"
        "- subtitle: 补充说明或吸引语，10-15字\n"
        "- tag: 分类标签，2-4字\n"
        "- emoji: 与主题相关的装饰emoji\n\n"
        "严格输出以下 JSON 格式（不要输出其他内容，不要 markdown 代码块）：\n"
        '{\n'
        '  "pages": [\n'
        '    {\n'
        '      "type": "cover",\n'
        '      "title": "主标题",\n'
        '      "subtitle": "副标题",\n'
        '      "footer": "@灵犀工坊",\n'
        '      "tag": "分类标签",\n'
        '      "emoji": "🎨",\n'
        '      "highlight": "高亮关键词"\n'
        '    }\n'
        '  ],\n'
        '  "suggested_template": "模板id",\n'
        '  "custom_accent": "#FF5A5F",\n'
        '  "suggested_decoration": {\n'
        '    "type": "decoration_type",\n'
        '    "color1": "#hex",\n'
        '    "color2": "#hex",\n'
        '    "opacity": 0.2\n'
        '  }\n'
        '}\n\n'
        f"可用模板：{template_list}\n"
        "选择原则：简约/干货 → minimal_white, 暖色/美食/旅行 → warm_card, "
        "深色/高级 → dark_ink, 品牌/专业 → dark_ink\n\n"
        "可用装饰类型：gradient_orbs, grid_lines, dots, wave, noise, geometric\n"
        "选择原则：简约 → noise(低透明度), 暖色 → gradient_orbs, "
        "深色 → geometric, 品牌 → grid_lines\n"
    )


def build_fallback_card_draft(
    topic: str,
    title: str,
    content: str,
    tags: list[str],
    key_points: list[str],
    matcher: TemplateMatcher,
    registry: TemplateRegistry,
) -> dict[str, Any]:
    paragraphs = [p.strip() for p in (content or "").split("\n") if p.strip()]
    if not paragraphs:
        sentences = re.split(r"(?<=[。！？；])", content or "")
        sentences = [s.strip() for s in sentences if s.strip()]
        paragraphs = []
        chunk: list[str] = []
        for sentence in sentences:
            chunk.append(sentence)
            if len(chunk) >= 2:
                paragraphs.append("".join(chunk))
                chunk = []
        if chunk:
            paragraphs.append("".join(chunk))
    if not paragraphs:
        paragraphs = [content] if content else ["正文内容待补充"]

    if isinstance(key_points, list) and key_points:
        list_items = [str(point)[:100] for point in key_points[:5]]
    else:
        list_items = ["要点一", "要点二", "要点三"]

    template_id = matcher.match_template(topic)
    cover_values: dict[str, Any] = {
        "title": title or topic or "点击编辑标题",
        "subtitle": " · ".join(tags[:3]) if isinstance(tags, list) and tags else "",
        "footer": "@灵犀工坊",
        "highlight": "",
        "tag": "干货分享",
    }
    cover = _page_from_fields(registry, template_id, "cover", cover_values)
    cover["type"] = "cover"

    pages: list[dict[str, Any]] = [cover]
    if registry.supports_page_type(template_id, "dark_panel"):
        key_page = _page_from_fields(
            registry,
            template_id,
            "dark_panel",
            {
                "title": "核心要点",
                "emoji": "💡",
                "decoNumber": "01",
                "listItems": list_items,
                "content": "",
            },
        )
        key_page["type"] = "dark_panel"
    else:
        key_page = _page_from_fields(
            registry,
            template_id,
            "list",
            {
                "title": "要点清单",
                "listItems": list_items,
            },
        )
        key_page["type"] = "list"
    pages.append(key_page)

    per_page = 2 if len(paragraphs) <= 4 else 3
    for i in range(0, len(paragraphs), per_page):
        content_page = _page_from_fields(
            registry,
            template_id,
            "content",
            {
                "title": "",
                "content": "\n".join(paragraphs[i : i + per_page]),
            },
        )
        content_page["type"] = "content"
        pages.append(content_page)

    if registry.supports_page_type(template_id, "end_page"):
        end_page = _page_from_fields(
            registry,
            template_id,
            "end_page",
            {
                "title": "",
                "content": "一句让人记住你的话。",
                "footer": "@灵犀工坊",
                "ctaText": "关注我，获取更多",
                "decoNumber": '"',
            },
        )
        end_page["type"] = "end_page"
        pages.append(end_page)

    return {"pages": pages, "suggested_template": template_id}


def postprocess_draft(
    card_draft: dict[str, Any],
    copywrite_title: str,
    copywrite_content: str,
    copywrite_tags: list[str],
) -> None:
    pages = card_draft.get("pages", [])
    if not pages:
        return

    cover = next((page for page in pages if page.get("type") == "cover"), None)
    if cover:
        if not cover.get("title") and copywrite_title:
            cover["title"] = copywrite_title[:40]
        if not cover.get("subtitle") and copywrite_tags:
            cover["subtitle"] = " · ".join(copywrite_tags[:3])

    content_types = {
        "content",
        "list",
        "dark_panel",
        "quote",
        "big_quote",
        "steps",
        "numbered_cards",
        "compare",
        "icon_text",
        "newspaper",
    }
    empty_pages: list[dict[str, Any]] = []
    for page in pages:
        if page.get("type") not in content_types:
            continue
        has_any = any(
            [
                page.get("content"),
                page.get("listItems"),
                page.get("steps"),
                page.get("numberedItems"),
                page.get("compareLeftItems"),
                page.get("compareRightItems"),
                page.get("iconTextPairs"),
                page.get("newspaperCols"),
            ]
        )
        if not has_any:
            empty_pages.append(page)

    if empty_pages and copywrite_content:
        paragraphs = [p.strip() for p in copywrite_content.split("\n") if p.strip()]
        if not paragraphs:
            sentences = re.split(r"(?<=[。！？；])", copywrite_content)
            sentences = [s.strip() for s in sentences if s.strip()]
            paragraphs = []
            chunk: list[str] = []
            for sentence in sentences:
                chunk.append(sentence)
                if len(chunk) >= 2:
                    paragraphs.append("".join(chunk))
                    chunk = []
            if chunk:
                paragraphs.append("".join(chunk))
        if not paragraphs:
            paragraphs = [copywrite_content]

        per_page = max(1, (len(paragraphs) + len(empty_pages) - 1) // len(empty_pages))
        paragraph_index = 0
        for page in empty_pages:
            if paragraph_index >= len(paragraphs):
                break
            chunk = paragraphs[paragraph_index : paragraph_index + per_page]
            paragraph_index += per_page
            if page.get("type") in ("list", "dark_panel"):
                page["listItems"] = chunk
            else:
                page["content"] = "\n".join(chunk)

    card_draft["copywrite_context"] = {
        "title": copywrite_title,
        "content": copywrite_content,
        "tags": copywrite_tags if isinstance(copywrite_tags, list) else [],
    }


class ContentPlanner:
    def __init__(
        self,
        registry: TemplateRegistry | None = None,
        matcher: TemplateMatcher | None = None,
    ) -> None:
        self._registry = registry or get_template_registry()
        self._matcher = matcher or TemplateMatcher(self._registry)

    async def plan(
        self,
        *,
        topic: str,
        title: str,
        content: str,
        tags: list[str],
        key_points: list[str],
        structured_items: list[dict[str, Any]],
        content_type: str,
        visual_suggestion: str,
        brand: dict[str, Any] | None = None,
        style_hint: str | None = None,
        llm: Any,
    ) -> tuple[dict[str, Any], str]:
        template_id = self._matcher.match_template(topic, content_type)
        if structured_items:
            draft = _build_structured_draft(
                registry=self._registry,
                topic=topic,
                title=title,
                structured_items=structured_items,
                suggested_template=template_id,
            )
            model_used = "structured_split (no LLM)"
        else:
            draft, model_used = await self._plan_with_llm(
                topic=topic,
                title=title,
                content=content,
                tags=tags,
                key_points=key_points,
                visual_suggestion=visual_suggestion,
                template_id=template_id,
                llm=llm,
            )

        postprocess_draft(draft, title, content, tags)
        if not structured_items:
            # 结构化清单页本身已有清晰节奏，避免把「知识点列表」拆散
            enforce_page_diversity(draft, self._registry, template_id)
        self._apply_template_metadata(draft, template_id, content_type, brand)
        # P1-3 共享质量门禁：在出图前对 card_draft 做结构/数值预检
        try:
            from app.services.quality_gate import run_quality_gate

            report = run_quality_gate(draft, registry=self._registry)
            draft["quality"] = report.model_dump()
        except Exception as exc:
            logger.warning(f"[image_plan_planner] quality gate attach failed: {exc}")
        return draft, model_used

    async def _plan_with_llm(
        self,
        *,
        topic: str,
        title: str,
        content: str,
        tags: list[str],
        key_points: list[str],
        visual_suggestion: str,
        template_id: str,
        llm: Any,
    ) -> tuple[dict[str, Any], str]:
        fallback = build_fallback_card_draft(
            topic,
            title,
            content,
            tags,
            key_points,
            self._matcher,
            self._registry,
        )
        fallback["suggested_template"] = template_id
        if llm is None:
            return fallback, "fallback (no LLM)"

        prompt = build_content_plan_prompt(
            topic=topic,
            title=title,
            content=content,
            tags=tags,
            key_points=key_points,
            visual_suggestion=visual_suggestion,
        )
        try:
            response = await llm.chat(messages=[{"role": "user", "content": prompt}])
            raw = (response.get("content") or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw.rsplit("```", 1)[0]
                raw = raw.strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or not isinstance(parsed.get("pages"), list):
                raise ValueError("invalid content plan structure")
            draft = {"pages": parsed["pages"], "suggested_template": template_id}
            return draft, llm.model_name or "deepseek"
        except Exception as exc:
            logger.warning(f"[image_plan_planner] LLM plan failed: {exc}, using fallback")
            return fallback, "fallback (LLM error)"

    def _apply_template_metadata(
        self,
        draft: dict[str, Any],
        template_id: str,
        content_type: str,
        brand: dict[str, Any] | None,
    ) -> None:
        manifest = self._registry.get(template_id)
        draft["suggested_template"] = template_id
        if manifest:
            draft["custom_accent"] = (
                (brand or {}).get("primary")
                or manifest.theme.get("accent", "")
            )
        if brand:
            draft["brand"] = brand
        draft["suggested_decoration"] = self._matcher.match_decoration(
            template_id,
            content_type,
        )

    def build_format_plan(
        self,
        page_count: int,
        template_id: str,
        platform: str = "xiaohongshu",
        format_name: str | None = None,
    ) -> dict[str, Any]:
        return self._matcher.build_format_plan(
            page_count=page_count,
            template_id=template_id,
            platform=platform,
            format_name=format_name,
        )