"""质量验证器：对照 esther checklist 做程序化检查。

检查项：
- Jinja2 语法合法
- 品牌三色比例大致 6:3:1
- 无禁忌元素（glassmorphism / neon / bounce 等）
- schema 和模板字段对齐
"""

from __future__ import annotations

import json
import re

from jinja2 import Environment, TemplateSyntaxError

FORBIDDEN_PATTERNS = [
    (r"glassmorphism|backdrop-filter:\s*blur", "禁止 glassmorphism"),
    (r"neon|text-shadow.*0\s*0\s*\d+px", "禁止 neon 光效"),
    (r"animation.*bounce|animation.*elastic", "禁止 bounce/elastic 动画"),
    (r"border-left:\s*\d+px\s+solid(?!\s*var)", "禁止默认 border-left 竖线引用块（必须用组件库的引用组件）"),
    (r"<blockquote(?![^>]*class)", "禁止无样式的 blockquote（必须用组件库的引用组件）"),
    (r"<ul(?![^>]*class)|<ol(?![^>]*class)", "禁止无样式的 ul/ol（必须用组件库的列表组件）"),
    (r"<table(?![^>]*class)", "禁止无样式的 table（必须用组件库的表格组件）"),
    (r"font-family:\s*(Inter|Roboto|Arial)", "禁止 Inter/Roboto/Arial 字体"),
]

BRAND_COLORS = {
    "primary": "#2B7FD8",
    "accent": "#F4D758",
    "spot": "#E84A5F",
}


def validate_template_package(
    schema_json: dict,
    template_html: str,
    meta_json: dict | None = None,
) -> list[dict]:
    """验证模板包质量，返回问题列表。空列表 = 通过。

    Returns
    -------
    list[dict]
        [{"level": "error"|"warning", "rule": "...", "message": "..."}]
    """
    issues: list[dict] = []

    # 1. Jinja2 语法检查
    try:
        Environment().parse(template_html)
    except TemplateSyntaxError as e:
        issues.append({
            "level": "error",
            "rule": "jinja2_syntax",
            "message": f"Jinja2 语法错误: {e}",
        })

    # 2. schema 字段在模板中有对应的数据槽
    fields = schema_json.get("fields", [])
    for field in fields:
        key = field.get("key", "")
        if not key:
            continue
        if not _field_has_slot(key, template_html):
            issues.append({
                "level": "warning",
                "rule": "schema_field_missing",
                "message": f"schema 中定义了字段 '{key}'，但模板中未找到对应的数据槽",
            })

    # 3. 禁忌元素检查
    for pattern, reason in FORBIDDEN_PATTERNS:
        if re.search(pattern, template_html, re.IGNORECASE):
            issues.append({
                "level": "error",
                "rule": "forbidden_element",
                "message": reason,
            })

    # 4. 品牌色存在性检查（宽松：只要模板里用了品牌三色中的至少一种）
    brand_colors_used = 0
    for color_name, color_value in BRAND_COLORS.items():
        if color_value.lower() in template_html.lower():
            brand_colors_used += 1
    if brand_colors_used == 0 and meta_json and meta_json.get("brand", {}).get("use_default", True):
        issues.append({
            "level": "warning",
            "rule": "brand_colors_missing",
            "message": "模板中未使用任何 esther 品牌三色（#2B7FD8 / #F4D758 / #E84A5F）",
        })

    # 5. 全内联样式检查（公众号场景必须）
    if meta_json and meta_json.get("scene") == "wechat":
        if "<style" in template_html.lower():
            issues.append({
                "level": "error",
                "rule": "wechat_no_style_tag",
                "message": "公众号模板禁止使用 <style> 标签，必须全内联样式",
            })

    return issues


def _field_has_slot(key: str, template: str) -> bool:
    """检查模板中是否有对应 key 的 Jinja2 数据槽。"""
    patterns = [
        "{{ " + key + " }}",
        "{{ " + key + "|",
        "{{ " + key + ".",
        "{% for " + key,
        "{% if " + key,
    ]
    if any(p in template for p in patterns):
        return True
    for_loops = re.findall(r"\{%\s*for\s+\w+\s+in\s+(\w+)", template)
    if key in for_loops:
        return True
    return False