"""设计系统注入器：将设计系统知识提前到 system prompt 阶段注入。

根因修复：
  当前 palettes.md / card-recipes.md / layout-laws.md 锁在 Skill.references 里，
  只有 execute() 时才加载。LLM 在决策阶段（选工具+选配色）看不到这些知识，
  导致"幻觉"出固定蓝/紫配色。

  本模块在 LoopExecutor._system_prompt() 阶段根据创作意图注入设计系统知识，
  让 LLM 决策时就有完整的设计上下文。

去重策略：
  - system prompt 注入：每个 reference 文件的【核心规则摘要】（~45%内容）
  - Skill.execute() 注入：reference 文件的【完整原文】（100%内容）
  - 两者不冲突：system prompt 是"全局导航"，execute() 是"详细手册"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REFERENCES_DIR = Path(__file__).resolve().parent

_DESIGN_SYSTEM_FILES: dict[str, list[str]] = {
    "visual": [
        "palettes.md",
        "card-recipes.md",
        "layout-laws.md",
        "anti-ai-slop.md",
    ],
    "writing": [
        "writing-style-rules.md",
        "zh-ai-markers.md",
        "phrases-to-remove.md",
    ],
}

_INTENT_TO_KNOWLEDGE: dict[str, list[str]] = {
    "image_text": ["visual", "writing"],
    "card": ["visual", "writing"],
    "copywrite": ["writing"],
    "video": ["writing"],
    "data": ["visual"],
    "default": ["writing"],
}

_INTENT_SIGNALS: dict[str, list[str]] = {
    "image_text": [
        "图文", "做图", "卡片", "小红书", "封面", "海报",
        "信息图", "对比图", "知识卡", "金句卡", "竖版",
    ],
    "card": ["卡片", "知识卡", "金句卡", "card", "渲染卡片"],
    "copywrite": ["文案", "写", "标题", "正文", "标签", "种草"],
    "video": ["视频", "脚本", "口播", "剪辑"],
    "data": ["数据", "图表", "可视化", "报告", "信息图"],
}

_CREATION_TYPE_TO_INTENT: dict[str, str] = {
    "image_text": "image_text",
    "voiceover": "copywrite",
    "short_video": "video",
    "ai_edit": "image_text",
    "long_article": "copywrite",
    "live_clip": "video",
}


def infer_creative_intent(
    user_message: str,
    creation_type: str | None = None,
) -> str:
    """推断创作意图。

    复用项目已有的 creation_type 机制（见 registry.py CREATION_TYPE_SKILLS），
    优先用前端显式传入的 creation_type，其次用信号词匹配。
    """
    if creation_type:
        return _CREATION_TYPE_TO_INTENT.get(creation_type, "default")

    msg = user_message.lower()
    best_intent = "default"
    best_score = 0
    for intent, signals in _INTENT_SIGNALS.items():
        score = sum(1 for s in signals if s in msg)
        if score > best_score:
            best_score = score
            best_intent = intent
    return best_intent


def _summarize_reference(content: str, max_chars: int) -> str:
    """将 reference 文件内容压缩为核心规则摘要。

    策略：
    - 保留 # 标题和 ## 二级标题（结构骨架）
    - 保留 > 引用块（关键原则）
    - 保留表格（如 palettes.md 的配色表）
    - 保留 🚫/✅ 标记的规则行
    - 截断长段落，保留前两句

    关键：append 前检查长度，保证每行都是完整的 Markdown，
    不会出现表格行被腰斩的情况。
    """
    lines = content.split("\n")
    kept: list[str] = []
    current_len = 0

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("#"):
            candidate = line
        elif stripped.startswith(">"):
            candidate = line
        elif stripped.startswith("|") and not stripped.startswith("|--"):
            candidate = line
        elif any(marker in stripped for marker in ("🚫", "✅", "⚠️", "🔴", "🟡", "🟢")):
            candidate = line
        elif stripped and not stripped.startswith("-") and not stripped.startswith("*"):
            candidate = stripped[:80] + ("…" if len(stripped) > 80 else "")
        elif stripped.startswith("-") or stripped.startswith("*"):
            candidate = stripped[:100]
        else:
            continue

        if current_len + len(candidate) + 1 > max_chars:
            break

        kept.append(candidate)
        current_len += len(candidate) + 1

    result = "\n".join(kept)
    if current_len >= max_chars:
        result += "\n\n⚠️ 设计系统摘要已截断"
    return result


def build_design_system_block(
    user_message: str = "",
    creation_type: str | None = None,
    mode: str = "summary",
    max_chars: int = 0,
) -> str:
    """根据创作意图，构建设计系统知识块。

    Args:
        user_message: 用户原始消息
        creation_type: 前端传入的创作类型
        mode: "summary"=摘要版（用于 system prompt），"full"=完整版（备用）
        max_chars: 最大字符数，0 表示自动计算
    """
    intent = infer_creative_intent(user_message, creation_type)
    knowledge_types = _INTENT_TO_KNOWLEDGE.get(intent, ["writing"])

    parts: list[str] = []
    parts.append("## 设计系统")
    parts.append(
        "> 以下知识适用于所有相关工具，不限于特定 Skill。\n"
        "> 选配色时必须从此处选取，不要自定义新配色。\n"
        "> 完整详情在各 Skill 执行时自动补充。\n"
    )

    if max_chars == 0:
        file_sizes: dict[str, int] = {}
        for ktype in knowledge_types:
            for fname in _DESIGN_SYSTEM_FILES.get(ktype, []):
                fpath = _REFERENCES_DIR / fname
                if fpath.exists():
                    file_sizes[fname] = fpath.stat().st_size
        total_raw = sum(file_sizes.values())
        max_chars = max(int(total_raw * 0.45), 8000)

    for ktype in knowledge_types:
        files = _DESIGN_SYSTEM_FILES.get(ktype, [])
        for fname in files:
            fpath = _REFERENCES_DIR / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8").strip()
                if content:
                    if mode == "summary":
                        content = _summarize_reference(content, max_chars // max(len(files), 1))
                    parts.append(content)
                    parts.append("")

    result = "\n".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n⚠️ 设计系统内容已截断"
    return result