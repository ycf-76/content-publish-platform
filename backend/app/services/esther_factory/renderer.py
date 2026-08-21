"""模板渲染器：用 Jinja2 填数据，输出最终 HTML。

核心逻辑：
- 从模板库读取 Jinja2 模板
- 用用户数据渲染
- 品牌色通过 brand 变量注入，不需要重新调 LLM
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, BaseLoader, TemplateNotFound

_TEMPLATES_DIR = Path(__file__).parent / "templates"

DEFAULT_BRAND = {
    "primary": "#2B7FD8",
    "accent": "#F4D758",
    "spot": "#E84A5F",
    "cream": "#fefcf6",
    "creamDark": "#faf6eb",
    "ink": "#1A1A2E",
    "inkLight": "#4A4A5A",
    "inkFaint": "#8A8A9A",
}


class _TemplateLoader(BaseLoader):
    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir

    def get_source(self, environment, template_id):
        template_dir = self.templates_dir / template_id
        template_file = template_dir / "template.html"
        if not template_file.exists():
            raise TemplateNotFound(template_id)
        source = template_file.read_text(encoding="utf-8")
        mtime = str(template_file.stat().st_mtime)
        return source, str(template_file), lambda: template_file.stat().st_mtime == float(mtime)


_env = Environment(loader=_TemplateLoader(_TEMPLATES_DIR), autoescape=False)


def render(template_id: str, data: dict, brand: dict | None = None) -> str:
    """用数据渲染模板，输出最终 HTML。

    Parameters
    ----------
    template_id : str
        模板 ID，对应 templates/<id>/ 目录
    data : dict
        用户数据，键对应 schema.json 中的 fields
    brand : dict | None
        品牌色覆盖，如 {"primary": "#FF6B35"}
        None 则使用 esther 默认品牌色

    Returns
    -------
    str
        渲染后的完整 HTML
    """
    final_brand = {**DEFAULT_BRAND}
    if brand:
        final_brand.update(brand)

    template = _env.get_template(template_id)
    return template.render(**data, brand=final_brand)


def get_schema(template_id: str) -> dict | None:
    """读取模板的 schema.json。"""
    schema_file = _TEMPLATES_DIR / template_id / "schema.json"
    if not schema_file.exists():
        return None
    return json.loads(schema_file.read_text(encoding="utf-8"))


def get_meta(template_id: str) -> dict | None:
    """读取模板的 meta.json。"""
    meta_file = _TEMPLATES_DIR / template_id / "meta.json"
    if not meta_file.exists():
        return None
    return json.loads(meta_file.read_text(encoding="utf-8"))


def list_templates() -> list[dict]:
    """列出模板库中所有可用模板。"""
    results = []
    if not _TEMPLATES_DIR.exists():
        return results
    for d in sorted(_TEMPLATES_DIR.iterdir()):
        if d.is_dir():
            schema = get_schema(d.name)
            meta = get_meta(d.name)
            results.append({
                "id": d.name,
                "name": schema.get("name", d.name) if schema else d.name,
                "scene": meta.get("scene", "unknown") if meta else "unknown",
                "fields_count": len(schema.get("fields", [])) if schema else 0,
            })
    return results