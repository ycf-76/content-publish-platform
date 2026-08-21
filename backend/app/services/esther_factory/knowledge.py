"""知识库管理：按需组装 esther-design-system 的知识文件喂给 LLM。

分层策略：
  第一层（固定）：brand-dna.md + checklist.md
  第二层（按场景）：scene-*.md
  第三层（按场景自动摘组件）：从 components.md 摘出场景文件提到的组件
  第四层（参考模板）：template-*.html
"""

from __future__ import annotations

import re
from pathlib import Path

_KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

SCENES = ("cards", "wechat", "tutorial", "landing", "app")

_COMPONENT_HEADING_RE = re.compile(r"^#{1,3}\s+(\d+[A-Z]?)[.\s]", re.MULTILINE)


def _read(name: str) -> str:
    p = _KNOWLEDGE_DIR / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def _extract_components(components_text: str, indices: list[str]) -> str:
    """从 components.md 摘出指定编号的组件片段。

    indices 如 ["1A", "5", "8", "11", "43"]
    """
    sections: list[str] = []
    lines = components_text.split("\n")
    current_idx = ""
    current_lines: list[str] = []
    capturing = False

    for line in lines:
        m = re.match(r"^#{1,3}\s+(\d+[A-Z]?)[.\s]", line)
        if m:
            if capturing and current_lines:
                sections.append("\n".join(current_lines))
            current_idx = m.group(1)
            current_lines = [line] if current_idx in indices else []
            capturing = current_idx in indices
        elif capturing:
            current_lines.append(line)

    if capturing and current_lines:
        sections.append("\n".join(current_lines))

    return "\n\n---\n\n".join(sections)


def _scene_component_indices(scene: str) -> list[str]:
    """根据场景文件内容，提取引用的组件编号。

    场景文件里会写 "components.md #8" 或 "#1B" 这样的引用。
    """
    scene_text = _read(f"scene-{scene}.md")
    refs = re.findall(r"#(\d+[A-Z]?)", scene_text)
    return list(dict.fromkeys(refs))


def build_context(
    scene: str,
    brand_overrides: dict | None = None,
    extra_instructions: str = "",
) -> str:
    """组装 LLM 生产所需的完整上下文。

    Parameters
    ----------
    scene : str
        场景名：cards / wechat / tutorial / landing / app
    brand_overrides : dict | None
        用户自定义品牌色，如 {"primary": "#FF6B35", "accent": "#1A1A2E"}
    extra_instructions : str
        额外指令（如"用更紧凑的间距"）

    Returns
    -------
    str
        组装好的上下文文本
    """
    if scene not in SCENES:
        raise ValueError(f"Unknown scene: {scene}. Supported: {SCENES}")

    parts: list[str] = []

    # 第一层：品牌 DNA + 质检标准（固定）
    brand_dna = _read("brand-dna.md")
    if brand_overrides:
        brand_dna += f"\n\n## 用户自定义品牌色\n\n"
        brand_dna += "用户要求替换以下品牌色，你必须在输出中使用这些颜色：\n"
        for key, value in brand_overrides.items():
            brand_dna += f"- {key}: {value}\n"
    parts.append(f"## 品牌DNA（必须遵守）\n\n{brand_dna}")

    checklist = _read("checklist.md")
    parts.append(f"## 质检标准（P0 必须全过）\n\n{checklist}")

    # 第二层：场景规范
    scene_text = _read(f"scene-{scene}.md")
    parts.append(f"## 场景规范：{scene}\n\n{scene_text}")

    # 第三层：摘取相关组件
    indices = _scene_component_indices(scene)
    if indices:
        components_full = _read("components.md")
        components_selected = _extract_components(components_full, indices)
        if components_selected:
            parts.append(f"## 可用组件（从组件库中摘取）\n\n{components_selected}")

    # 第四层：参考模板
    template_name = f"template-{scene}.html"
    template_text = _read(template_name)
    if template_text:
        parts.append(f"## 参考模板 HTML 结构\n\n```html\n{template_text}\n```")

    # 额外指令
    if extra_instructions:
        parts.append(f"## 额外指令\n\n{extra_instructions}")

    return "\n\n---\n\n".join(parts)


def list_scenes() -> list[dict]:
    """列出所有可用场景及其简要描述。"""
    scene_info = {
        "cards": "图文卡片（1080×1440 小红书竖图）",
        "wechat": "公众号排版（全内联 HTML，直接粘贴到微信编辑器）",
        "tutorial": "教程页（独立网页，教程/介绍/科普）",
        "landing": "Landing页（活动页/分享会邀请/产品发布）",
        "app": "App型页面（看板/书架/Canvas白板）",
    }
    return [{"id": k, "name": v} for k, v in scene_info.items()]