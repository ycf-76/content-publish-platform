"""蓝图生成 Skill：调 LLM 根据 topic + insights + copywrite 输出 blueprint JSON。

蓝图结构：
{
  "intent": "励志教程",  # 用户意图分类
  "style": {
    "primary_color": "#FF5A5F",
    "bg_color": "#FDFBF7",
    "font_style": "sans-serif"
  },
  "pages": [
    {"type": "cover", "title": "...", "subtitle": "...", "tags": [...], "intent": "..."},
    {"type": "pain_quote", "quote": "...", "subtext": "..."},
    {"type": "steps", "title": "...", "steps": [{"title": "...", "desc": "..."}]},
    {"type": "comparison", "title": "...", "left": {...}, "right": {...}},
    {"type": "single_quote", "quote": "...", "subtext": "..."},
    {"type": "list_tips", "title": "...", "tips": [...]}
  ]
}

意图映射（page type 选择）：
- 励志教程：[cover, pain_quote, steps, single_quote]
- 对比测评：[cover, comparison, list_tips, single_quote]
- 干货清单：[cover, list_tips, steps, single_quote]
- 吐槽避坑：[cover, pain_quote, list_tips, single_quote]
- 经验分享：[cover, steps, list_tips, single_quote]
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.skills.base import Skill
from app.agents.skills.registry import register

logger = logging.getLogger(__name__)


@register
class XHSBlueprintSkill(Skill):
    """动态布局生成 Skill。

    仅作为前端可选项注册到 SkillRegistry（让 /api/skills 能返回 xhs_blueprint）。
    实际执行逻辑由 graph.py 的 image_plan_node / image_gen_node 中的 blueprint 分支处理：
    - image_plan_node: 调 generate_blueprint 生成蓝图
    - image_gen_node: 调 render_blueprint_to_images 渲染 4 张卡

    当用户在前端选了 "xhs_blueprint" 时，graph.py 通过
    `user_image_skill == "xhs_blueprint"` 进入 blueprint 模式，
    不会调用本类的 execute()。
    """

    node_type = "image_gen"
    name = "xhs_blueprint"
    display_name = "动态布局生成"
    description = (
        "LLM 根据用户意图输出结构化蓝图，动态渲染4张卡片"
        "（封面/痛点/步骤/对比/金句）"
    )
    default_config: dict[str, Any] = {}

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """占位实现：实际逻辑在 graph.py 的 blueprint 分支处理。

        如果被意外调用（例如 SkillRegistry 直接调度），返回错误信息，
        让上层降级到候选模式，而不是抛 NotImplementedError 中断流程。
        """
        logger.warning(
            "[xhs_blueprint] execute() 不应被直接调用，"
            "实际逻辑由 graph.py 的 image_plan_node/image_gen_node 处理"
        )
        return {
            "images_base64": [],
            "image_details": [],
            "style": "动态布局生成（占位）",
            "image_prompts": [],
            "_source": "blueprint_placeholder",
            "_skill": self.name,
            "_error": "blueprint mode should be handled in graph.py",
        }


# 意图 → 推荐 pages 模板（LLM 可参考，但最终由 LLM 根据内容决定）
INTENT_PAGE_TEMPLATES: dict[str, list[str]] = {
    "励志教程": ["cover", "pain_quote", "steps", "single_quote"],
    "对比测评": ["cover", "comparison", "list_tips", "single_quote"],
    "干货清单": ["cover", "list_tips", "steps", "single_quote"],
    "吐槽避坑": ["cover", "pain_quote", "list_tips", "single_quote"],
    "经验分享": ["cover", "steps", "list_tips", "single_quote"],
    "教程": ["cover", "steps", "list_tips", "single_quote"],
    "吐槽": ["cover", "pain_quote", "list_tips", "single_quote"],
    "对比": ["cover", "comparison", "list_tips", "single_quote"],
    "励志": ["cover", "pain_quote", "single_quote", "list_tips"],
}

# 风格预设（LLM 可从中选，也可自定义）
STYLE_PRESETS: dict[str, dict[str, str]] = {
    "warm": {"primary_color": "#FF7A45", "bg_color": "#FFF8F0", "font_style": "sans-serif"},
    "fresh": {"primary_color": "#00B894", "bg_color": "#F0FBF6", "font_style": "sans-serif"},
    "calm": {"primary_color": "#4A90E2", "bg_color": "#F5F8FC", "font_style": "sans-serif"},
    "passion": {"primary_color": "#E74C3C", "bg_color": "#FDF2F0", "font_style": "sans-serif"},
    "elegant": {"primary_color": "#8E44AD", "bg_color": "#F8F4FB", "font_style": "serif"},
    "classic": {"primary_color": "#2C3E50", "bg_color": "#FDFBF7", "font_style": "serif"},
    "cute": {"primary_color": "#FF9FF3", "bg_color": "#FFF5FC", "font_style": "sans-serif"},
    "pro": {"primary_color": "#1ABC9C", "bg_color": "#F4FAF9", "font_style": "sans-serif"},
}


def build_blueprint_prompt(
    topic: str,
    copywrite: dict[str, Any],
    insights: dict[str, Any] | None = None,
) -> str:
    """构造 LLM prompt，让模型输出 blueprint JSON。

    Args:
        topic: 用户原始选题
        copywrite: copywrite 节点输出（含 title/content/tags/key_points）
        insights: analyze 节点的 insights（可选，提供爆款因子参考）
    """
    title = copywrite.get("title", "")
    content = (copywrite.get("content") or "")[:600]  # 截断省 token
    tags = copywrite.get("tags") or []
    key_points = copywrite.get("key_points") or []
    tags_str = "、".join(tags[:6]) if tags else "无"
    kp_str = "\n".join(f"  - {p}" for p in key_points[:5]) if key_points else "  无"

    # insights 的 recommendations 作为意图判断参考
    recs_str = "无"
    if insights and isinstance(insights.get("recommendations"), list):
        recs = insights["recommendations"][:3]
        rec_lines = []
        for r in recs:
            if isinstance(r, dict):
                rec_lines.append(
                    f"  - 方向: {r.get('topic_direction', '')}, "
                    f"标题模板: {r.get('title_template', '')}"
                )
        if rec_lines:
            recs_str = "\n".join(rec_lines)

    return f"""你是小红书内容设计专家。根据用户选题和文案，输出结构化图片蓝图（blueprint），用于动态生成 4 张小红书卡片图。

## 用户选题（必须围绕）
{topic}

## 文案信息
标题：{title}
正文（截断）：
{content}
标签：{tags_str}

## 文案核心要点（已由文案 LLM 提取，直接复用）
{kp_str}

## 趋势分析参考（仅作意图判断参考，内容必须围绕用户选题）
{recs_str}

## 任务
1. 判断用户意图（intent），从以下选一个：
   励志教程 / 对比测评 / 干货清单 / 吐槽避坑 / 经验分享

2. 选择 4 个 page type 组成 pages 数组（第一张必须是 cover）：
   - cover: 封面（大标题 + 副标题 + 标签 + 意图徽章）
   - pain_quote: 痛点金句（引发共鸣的大字引言）
   - steps: 步骤教程（编号卡片，3-5 步）
   - comparison: 对比测评（左右两栏，每栏 3-4 个要点）
   - single_quote: 单图金句（居中励志/总结大字）
   - list_tips: 清单提示（3-5 条要点带序号徽章）

3. 选择配色风格（style），从以下预设选一个：
   warm(暖橙) / fresh(清新绿) / calm(冷静蓝) / passion(热情红) / elegant(优雅紫) / classic(经典深灰) / cute(可爱粉) / pro(专业青)

## 意图映射示例（参考，不强制）
- 焦虑AI裁员 → 励志教程 → [cover, pain_quote, steps, single_quote]
- 工具测评对比 → 对比测评 → [cover, comparison, list_tips, single_quote]
- 学习方法总结 → 干货清单 → [cover, list_tips, steps, single_quote]
- 踩坑吐槽 → 吐槽避坑 → [cover, pain_quote, list_tips, single_quote]

## 各 page type 的数据字段要求
- cover: {{type, title(必填), subtitle, tags(数组), intent}}
- pain_quote: {{type, quote(必填，痛点金句), subtext, author}}
- steps: {{type, title, steps:[{{title, desc}}]（3-5个）}}
- comparison: {{type, title, left:{{title, points:[str]}}, right:{{title, points:[str]}}}}
- single_quote: {{type, quote(必填), subtext, author}}
- list_tips: {{type, title, tips:[str]（3-5个）}}

## 红线
- 所有文字必须围绕用户选题「{topic}」，不要偏离
- 复用文案核心要点，不要凭空编造
- pages 数量固定 4 张
- 第 1 张必须是 cover

## 输出严格 JSON（不要 markdown 代码块，不要解释）
{{
  "intent": "意图分类",
  "style": {{"preset": "warm"}},
  "pages": [
    {{"type": "cover", "title": "...", "subtitle": "...", "tags": [...], "intent": "..."}},
    {{"type": "...", ...}},
    {{"type": "...", ...}},
    {{"type": "...", ...}}
  ]
}}
"""


def _apply_style_preset(blueprint: dict[str, Any]) -> dict[str, Any]:
    """如果 style 只有 preset 字段，展开为完整颜色配置。"""
    style = blueprint.get("style")
    if not isinstance(style, dict):
        # 兜底：warm 预设
        blueprint["style"] = STYLE_PRESETS["warm"].copy()
        return blueprint

    # 已经是完整配置（有 primary_color），直接返回
    if style.get("primary_color"):
        # 补全缺失字段
        style.setdefault("bg_color", "#FDFBF7")
        style.setdefault("font_style", "sans-serif")
        return blueprint

    # 用 preset 展开
    preset_name = style.get("preset", "warm")
    preset = STYLE_PRESETS.get(preset_name)
    if preset:
        blueprint["style"] = preset.copy()
    else:
        blueprint["style"] = STYLE_PRESETS["warm"].copy()
    return blueprint


def validate_blueprint(blueprint: dict[str, Any]) -> dict[str, Any] | None:
    """校验并修复 LLM 输出的 blueprint。

    Returns:
        修复后的 blueprint dict，校验失败返回 None
    """
    if not isinstance(blueprint, dict):
        return None

    pages = blueprint.get("pages")
    if not isinstance(pages, list) or not pages:
        logger.warning(f"[blueprint] pages 无效: {type(pages)}")
        return None

    supported = {"cover", "pain_quote", "steps", "comparison", "single_quote", "list_tips"}

    # 校验每张 page
    valid_pages: list[dict[str, Any]] = []
    for i, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        page_type = page.get("type", "")
        if page_type not in supported:
            logger.warning(f"[blueprint] page[{i}] 未知 type {page_type!r}，跳过")
            continue
        # 第 0 张必须是 cover
        if i == 0 and page_type != "cover":
            logger.warning(f"[blueprint] page[0] 必须 cover，实际 {page_type!r}")
            return None
        # 必填字段校验
        if page_type == "cover" and not (page.get("title") or "").strip():
            logger.warning("[blueprint] cover 缺 title")
            return None
        if page_type in ("pain_quote", "single_quote") and not (page.get("quote") or "").strip():
            logger.warning(f"[blueprint] {page_type} 缺 quote")
            return None
        if page_type == "steps" and not page.get("steps"):
            logger.warning("[blueprint] steps 缺 steps 数据")
            return None
        if page_type == "comparison" and not page.get("left") and not page.get("right"):
            logger.warning("[blueprint] comparison 缺 left/right 数据")
            return None
        if page_type == "list_tips" and not page.get("tips") and not page.get("items"):
            logger.warning("[blueprint] list_tips 缺 tips 数据")
            return None
        valid_pages.append(page)

    if len(valid_pages) < 1:
        logger.warning("[blueprint] 没有有效 page")
        return None

    blueprint["pages"] = valid_pages
    # 补全 intent
    if not blueprint.get("intent"):
        blueprint["intent"] = "经验分享"

    # 展开 style preset
    blueprint = _apply_style_preset(blueprint)

    return blueprint


def build_fallback_blueprint(
    topic: str,
    copywrite: dict[str, Any],
) -> dict[str, Any]:
    """LLM 不可用时，用模板生成基础 blueprint。

    规则：固定 [cover, list_tips, single_quote, list_tips] 4 张
    """
    title = copywrite.get("title", topic)[:20]
    tags = copywrite.get("tags") or [topic]
    key_points = copywrite.get("key_points") or [
        f"{topic}核心概念",
        "实操建议与注意事项",
        "常见问题与避坑指南",
    ][:5]

    return {
        "intent": "经验分享",
        "style": STYLE_PRESETS["warm"].copy(),
        "pages": [
            {
                "type": "cover",
                "title": title,
                "subtitle": topic,
                "tags": tags[:5],
                "intent": "经验分享",
            },
            {
                "type": "list_tips",
                "title": f"{topic}核心要点",
                "tips": key_points[:5],
            },
            {
                "type": "single_quote",
                "quote": f"掌握 {topic}，少走弯路",
                "subtext": "实践出真知",
            },
            {
                "type": "list_tips",
                "title": "注意事项",
                "tips": ["结合自身情况", "持续复盘优化", "保持学习心态"][:3],
            },
        ],
    }


async def generate_blueprint(
    topic: str,
    copywrite: dict[str, Any],
    insights: dict[str, Any] | None = None,
    llm: Any = None,
) -> dict[str, Any]:
    """调 LLM 生成 blueprint，失败时用 fallback。

    Args:
        topic: 用户选题
        copywrite: copywrite 节点输出
        insights: analyze 节点 insights（可选）
        llm: LLM 实例（需有 chat 方法），None 时直接走 fallback

    Returns:
        有效的 blueprint dict
    """
    if llm is None:
        logger.info("[blueprint] LLM 不可用，用 fallback blueprint")
        return build_fallback_blueprint(topic, copywrite)

    prompt = build_blueprint_prompt(topic, copywrite, insights)

    try:
        resp = await llm.chat(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content_str = (resp.get("content") or "").strip()
        # 去除可能的 markdown 代码块包裹
        if content_str.startswith("```"):
            content_str = content_str.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        parsed = json.loads(content_str)
        blueprint = validate_blueprint(parsed)
        if blueprint is None:
            logger.warning("[blueprint] LLM 输出校验失败，用 fallback")
            return build_fallback_blueprint(topic, copywrite)

        logger.info(
            f"[blueprint] LLM 生成成功: intent={blueprint.get('intent')!r}, "
            f"pages={[p.get('type') for p in blueprint.get('pages', [])]}"
        )
        return blueprint
    except json.JSONDecodeError as e:
        logger.warning(f"[blueprint] LLM 输出 JSON 解析失败: {e}，用 fallback")
        return build_fallback_blueprint(topic, copywrite)
    except Exception as e:
        logger.warning(f"[blueprint] LLM 调用失败: {e}，用 fallback")
        return build_fallback_blueprint(topic, copywrite)
