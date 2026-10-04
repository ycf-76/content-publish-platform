"""card_gen 节点：从文案产出生成卡片设计 spec。

输入：copywrite / final_review 的文案产出
输出：card_spec（结构化卡片设计规范，供前端渲染）+ card_count

借鉴 Easel card-design 的五步流程（选风格→锁spec→定字体→套骨架→自检），
但适配我们的架构：
- 不直接渲染 PNG（前端负责渲染）
- 输出结构化的 card_spec（风格+配色+骨架+内容分配）
- 前端消费 spec 渲染 HTML/CSS → 截图
"""
from __future__ import annotations

from app.agents.nodes._base import (
    NodeStatus, WorkflowState, _dlog, emit_node_event, logger,
    build_belief_dict, build_loop_counter_update,
)


_CONTENT_TYPE_TO_STYLE = {
    "knowledge": "indigo_porcelain",
    "tech": "minimal_white_ikb",
    "tool": "minimal_white_ikb",
    "product": "minimal_white_orange",
    "lifestyle": "kraft_paper",
    "reading": "forest_ink",
    "emotional": "dune",
    "food": "kraft_paper",
    "travel": "forest_ink",
    "data": "ink_classic",
}

_CONTENT_TYPE_TO_RECIPE = {
    "knowledge": "ledger_flow_data_coda",
    "tech": "ledger_compare_data",
    "tool": "ledger_compare_data",
    "product": "ledger_compare_data",
    "lifestyle": "quote_ledger",
    "reading": "quote_ledger",
    "emotional": "quote_ledger",
    "food": "quote_ledger",
    "travel": "quote_ledger",
    "data": "data_coda_compare",
}

_PALETTES = {
    "ink_classic": {
        "name": "Ink Classic",
        "primary": "#0a0a0b",
        "secondary": "#f3f0e8",
        "accent": "#111111",
        "text": "#0a0a0b",
        "text_light": "#68625a",
        "bg": "#f3f0e8",
        "border": "#0a0a0b",
    },
    "indigo_porcelain": {
        "name": "靛蓝瓷墨",
        "primary": "#1a2744",
        "secondary": "#f0ece2",
        "accent": "#3a5a8c",
        "text": "#1a2744",
        "text_light": "#6b7c94",
        "bg": "#f0ece2",
        "border": "#1a2744",
    },
    "forest_ink": {
        "name": "森林墨绿",
        "primary": "#1a3a2a",
        "secondary": "#f0ece2",
        "accent": "#2d5a3f",
        "text": "#1a3a2a",
        "text_light": "#5a7a6a",
        "bg": "#f0ece2",
        "border": "#1a3a2a",
    },
    "kraft_paper": {
        "name": "牛皮纸暖",
        "primary": "#3d2b1f",
        "secondary": "#f5e6c8",
        "accent": "#8b6914",
        "text": "#3d2b1f",
        "text_light": "#8a7a6a",
        "bg": "#f5e6c8",
        "border": "#3d2b1f",
    },
    "dune": {
        "name": "沙丘雅金",
        "primary": "#4a3f2f",
        "secondary": "#f2e8d5",
        "accent": "#c4a35a",
        "text": "#4a3f2f",
        "text_light": "#8a7a6a",
        "bg": "#f2e8d5",
        "border": "#4a3f2f",
    },
    "midnight_ink": {
        "name": "午夜黑金",
        "primary": "#f0ece2",
        "secondary": "#0a0a0b",
        "accent": "#c9a84c",
        "text": "#f0ece2",
        "text_light": "#8a8a8a",
        "bg": "#0a0a0b",
        "border": "#c9a84c",
    },
    "minimal_white_ikb": {
        "name": "极简白底+克莱因蓝",
        "primary": "#002FA7",
        "secondary": "#FFFFFF",
        "accent": "#002FA7",
        "text": "#0a1f3d",
        "text_light": "#6B6560",
        "bg": "#FFFFFF",
        "border": "#002FA7",
    },
    "minimal_white_lemon": {
        "name": "极简白底+柠檬黄",
        "primary": "#1a1a1a",
        "secondary": "#FFFFFF",
        "accent": "#FFD700",
        "text": "#1a1a1a",
        "text_light": "#6B6560",
        "bg": "#FFFFFF",
        "border": "#FFD700",
    },
    "minimal_white_orange": {
        "name": "极简白底+安全橙",
        "primary": "#1a1a1a",
        "secondary": "#FFFFFF",
        "accent": "#FF6B00",
        "text": "#1a1a1a",
        "text_light": "#6B6560",
        "bg": "#FFFFFF",
        "border": "#FF6B00",
    },
    "swiss": {
        "name": "瑞士极简",
        "primary": "#002FA7",
        "secondary": "#FFFFFF",
        "accent": "#FF3D00",
        "text": "#0a1f3d",
        "text_light": "#6B6560",
        "bg": "#FFFFFF",
        "border": "#002FA7",
    },
    "magazine": {
        "name": "杂志编辑",
        "primary": "#3F51B5",
        "secondary": "#F5F0EB",
        "accent": "#E91E63",
        "text": "#2D2D2D",
        "text_light": "#6B6560",
        "bg": "#F5F0EB",
        "border": "#3F51B5",
    },
}


def _infer_content_type(topic: str, content: str) -> str:
    text = f"{topic} {content}".lower()
    tech_kw = ["ai", "工具", "技术", "代码", "开发", "模型", "api", "效率", "自动化", "科技"]
    life_kw = ["生活", "阅读", "情感", "美食", "旅行", "穿搭", "护肤", "家居", "咖啡", "周末"]
    data_kw = ["数据", "报告", "统计", "对比", "排名", "榜单", "测评"]
    knowledge_kw = ["知识", "科普", "原理", "解析", "入门", "指南", "教程", "方法"]
    for kw in data_kw:
        if kw in text:
            return "data"
    for kw in tech_kw:
        if kw in text:
            return "tech"
    for kw in knowledge_kw:
        if kw in text:
            return "knowledge"
    for kw in life_kw:
        if kw in text:
            return "lifestyle"
    return "knowledge"


def _split_content_to_cards(title: str, content: str, tags: list[str]) -> list[dict]:
    """将文案内容拆分为卡片序列。"""
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    if not paragraphs:
        paragraphs = [content] if content else [title]

    cards = []

    # 封面卡
    cards.append({
        "type": "cover",
        "kicker": tags[0] if tags else "",
        "headline": title,
        "footer": "",
    })

    # 正文卡：每张一个核心段落
    for i, para in enumerate(paragraphs):
        if len(para) > 80:
            sub_paras = []
            while len(para) > 80:
                cut = para.rfind("。", 0, 80)
                if cut == -1:
                    cut = para.rfind("，", 0, 80)
                if cut == -1:
                    cut = 80
                sub_paras.append(para[:cut + 1])
                para = para[cut + 1:]
            if para:
                sub_paras.append(para)
            for sp in sub_paras:
                cards.append({"type": "body", "index": len(cards), "content": sp})
        else:
            cards.append({"type": "body", "index": len(cards), "content": para})

    # 收尾卡
    key_points = [p[:20] + "…" if len(p) > 20 else p for p in paragraphs[:5]]
    cards.append({
        "type": "coda",
        "key_points": key_points,
        "cta": "记得收藏，需要的时候不迷路",
    })

    return cards


async def card_gen_node(state: WorkflowState) -> dict:
    workflow_id = state["workflow_id"]
    node_id = "card_gen"

    _dlog(f"[{workflow_id}] ===== card_gen_node ENTERED =====")
    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed", {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    # 从上游取文案
    node_outputs = state.get("node_outputs", {})
    final_review = node_outputs.get("final_review", {})
    copywrite = node_outputs.get("copywrite", {})

    title = (
        final_review.get("title")
        or copywrite.get("title")
        or state.get("topic", "")
    )
    content = (
        final_review.get("content")
        or copywrite.get("content")
        or ""
    )
    tags = copywrite.get("tags", [])

    if not title and not content:
        logger.warning(f"[{workflow_id}] {node_id} no content for card generation")
        output = {
            "card_spec": None,
            "card_count": 0,
            "message": "无文案内容，跳过卡片生成",
        }
        await emit_node_event(workflow_id, node_id, "node_completed", output)
        return {
            "current_node": node_id,
            "node_statuses": {node_id: NodeStatus.COMPLETED.value},
            "node_outputs": {node_id: output},
        }

    # ── Step 1: 推断内容类型 → 选风格 ──
    content_type = _infer_content_type(title, content)
    model_settings = state.get("model_settings", {}) or {}
    style_override = model_settings.get("card_style", "")
    style = style_override if style_override and style_override in _PALETTES else _CONTENT_TYPE_TO_STYLE.get(content_type, "indigo_porcelain")
    recipe = _CONTENT_TYPE_TO_RECIPE.get(content_type, "ledger_flow_data_coda")
    palette = _PALETTES.get(style, _PALETTES["indigo_porcelain"])

    logger.info(
        f"[{workflow_id}] {node_id} content_type={content_type}, "
        f"style={style}, recipe={recipe}"
    )

    # ── Step 2: 拆分内容为卡片序列 ──
    cards = _split_content_to_cards(title, content, tags)

    # ── Step 3: 组装 card_spec ──
    card_spec = {
        "style": style,
        "palette": palette,
        "recipe": recipe,
        "content_type": content_type,
        "cards": cards,
        "card_count": len(cards),
        "layout": {
            "aspect_ratio": "3:4",
            "min_fill_ratio": 0.75,
            "max_dead_band": 0.15,
        },
        "typography": {
            "headline_weight": 300,
            "body_weight": 400,
            "body_min_px": 28,
            "text_color": palette["text"],
            "text_light_color": palette["text_light"],
        },
    }

    output = {
        "card_spec": card_spec,
        "card_count": len(cards),
        "style": style,
        "palette_name": palette["name"],
    }

    logger.info(
        f"[{workflow_id}] {node_id} completed: "
        f"style={style}, cards={len(cards)}, recipe={recipe}"
    )

    await emit_node_event(workflow_id, node_id, "node_completed", output)

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
        "agent_beliefs": build_belief_dict(node_id, output),
        "loop_counters": build_loop_counter_update(state, node_id),
    }