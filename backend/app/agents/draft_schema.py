"""Draft Schema：草稿结构说明书生成器。

让 Agent 像看 API 文档一样知道"我能写哪些字段、每个字段什么类型、什么约束"。
"""

from __future__ import annotations

import json
from typing import Any


DRAFT_FIELD_SCHEMA: dict[str, dict[str, Any]] = {
    "title": {
        "type": "string",
        "max_length": 20,
        "description": "笔记标题，15-20字，可用1-2个emoji点缀",
        "example": "5个让PPT瞬间高级的排版技巧",
    },
    "coverUrl": {
        "type": "image_url",
        "size": "1080x1440",
        "ratio": "3:4",
        "description": "封面图URL，3:4竖图，由image_plan生成后通过卡片编辑器导出",
        "generation_method": "image_plan_node → card_editor → html2canvas → inject",
        "note": "不能直接生成URL，需要走 card_draft 流程",
    },
    "contentText": {
        "type": "markdown",
        "max_length": 1000,
        "description": "正文内容，200-400字，分段清晰，口语化",
        "example": "很多人做PPT就是套模板...",
    },
    "scriptText": {
        "type": "markdown",
        "max_length": 2000,
        "description": "视频脚本（仅视频类型使用）",
    },
    "tags": {
        "type": "string_array",
        "min_items": 3,
        "max_items": 8,
        "description": "话题标签，3-8个，不带#号",
        "example": ["PPT", "职场技能", "排版设计"],
    },
    "platform": {
        "type": "enum",
        "values": ["xiaohongshu", "douyin", "kuaishou", "bilibili", "wechat_video"],
        "description": "发布平台",
    },
}

CARD_EDITOR_SCHEMA: dict[str, Any] = {
    "canvas_size": "1080x1440",
    "templates": [
        {"id": "minimal_white", "name": "极简白底", "style": "简约/干货/知识"},
        {"id": "warm_card", "name": "暖色卡片", "style": "温馨/美食/旅行"},
        {"id": "dark_ink", "name": "深色墨韵", "style": "高级/科技/观点"},
    ],
    "page_types": [
        "cover", "content", "quote", "list",
        "dark_panel", "end_page", "compare", "icon_text",
        "steps", "code_panel", "numbered_cards", "newspaper", "big_quote",
    ],
    "decoration_types": [
        "none", "gradient_orbs", "grid_lines", "dots",
        "wave", "noise", "geometric",
    ],
    "refinable_fields": {
        "customFontSize": {"type": "number", "description": "自定义字号覆盖模板默认"},
        "customAccent": {"type": "string", "description": "自定义强调色（十六进制）"},
        "customBg": {"type": "string", "description": "自定义背景色（十六进制）"},
    },
}

STYLE_TO_TEMPLATE: dict[str, str] = {
    "简约": "minimal_white",
    "清新": "minimal_white",
    "干货": "minimal_white",
    "暖色": "warm_card",
    "奶油": "warm_card",
    "温馨": "warm_card",
    "美食": "warm_card",
    "旅行": "warm_card",
    "深色": "dark_ink",
    "墨韵": "dark_ink",
    "高级": "dark_ink",
    "品牌": "dark_ink",
    "专业": "dark_ink",
    "科技": "dark_ink",
}


def build_draft_schema_prompt(work_context: dict[str, Any]) -> str:
    """生成草稿结构说明书，注入 Agent 的 system prompt。"""
    fields_with_values = {}
    for field_name, schema in DRAFT_FIELD_SCHEMA.items():
        entry = {**schema}
        current = work_context.get(field_name)
        if current is not None:
            if isinstance(current, str) and len(current) > 100:
                entry["current_value"] = current[:100] + "..."
            else:
                entry["current_value"] = current
        else:
            entry["current_value"] = None
        fields_with_values[field_name] = entry

    return (
        "## 当前草稿结构\n\n"
        "你可以修改以下字段（修改后通过 draft_patch 事件自动写入草稿）：\n\n"
        f"{json.dumps(fields_with_values, ensure_ascii=False, indent=2)}\n\n"
        "## 卡片编辑器\n\n"
        "封面图通过卡片编辑器生成，流程：选模板 → 填页面内容 → 选装饰 → 导出图片\n\n"
        f"{json.dumps(CARD_EDITOR_SCHEMA, ensure_ascii=False, indent=2)}\n\n"
        "## 修改规则\n\n"
        "- 你输出的 JSON 中，key 必须是上面 fields 中的字段名\n"
        "- coverUrl 不能直接生成 URL，需要走 card_draft 流程（image_plan → 编辑器 → 导出）\n"
        "- tags 是数组，整体替换而非追加\n"
        "- 精炼请求（调亮/换风格/改标题等）只修改目标字段，不要重写全部\n"
    )