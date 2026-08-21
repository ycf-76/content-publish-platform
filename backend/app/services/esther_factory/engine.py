"""Esther Template Factory engine.

Core flow:
  User request -> Assemble context -> LLM produces Jinja2 template -> Validate -> Save

Usage:
  from app.services.esther_factory import factory

  result = await factory.produce(
      scene="cards",
      description="step flow card with 3-5 steps",
      template_id="esther_steps_v2",
      brand_overrides={"primary": "#FF6B35"},
  )

  html = factory.render("esther_steps_v2", {
      "title": "3 Steps to Learn AI",
      "steps": [
          {"title": "Pick tools", "desc": "Find AI tools for you"},
          {"title": "Write prompts", "desc": "Learn clear prompting"},
          {"title": "Iterate", "desc": "Refine your results"},
      ],
  })
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import base64
from jinja2 import Environment, BaseLoader, TemplateNotFound

from .knowledge import build_context, list_scenes
from .renderer import render as _render_from_file, DEFAULT_BRAND
from .validator import validate_template_package

logger = logging.getLogger(__name__)

_FORBIDDEN_RE = [
    (re.compile(r"backdrop-filter\s*:\s*blur\s*\([^)]*\)\s*;?", re.IGNORECASE), ""),
    (re.compile(r"glassmorphism", re.IGNORECASE), ""),
    (re.compile(r"animation\s*:[^;]*bounce[^;]*;?", re.IGNORECASE), ""),
    (re.compile(r"animation\s*:[^;]*elastic[^;]*;?", re.IGNORECASE), ""),
]

def _auto_fix_forbidden(html: str) -> str:
    for pattern, replacement in _FORBIDDEN_RE:
        html = pattern.sub(replacement, html)
    return html

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_DEFAULT_BRAND_CONFIG = {
    "brand_name": "",
    "avatar_url": "",
    "gender": "man",
    "primary": "#2B7FD8",
    "accent": "#F4D758",
    "spot": "#E84A5F",
}

_SYSTEM_PROMPT = (
    "你是基于 Esther 设计方法论（开源设计规范）的模板生产师。\n"
    "⚠️ 重要：Esther 是设计方法论，不是身份。你不得在任何输出中使用 Esther/不二/esthersjw "
    "的姓名、头像、IP形象或品牌标识。所有身份相关内容必须使用使用者自己的品牌信息。\n\n"
    "你的任务是根据用户需求，生产一个 Jinja2 HTML 模板。\n\n"
    "## 输出格式\n\n"
    "你必须输出两个部分，用 ---SCHEMA--- 和 ---TEMPLATE--- 分隔：\n\n"
    "1. SCHEMA（JSON）：描述这个模板需要什么数据\n"
    "2. TEMPLATE（Jinja2 HTML）：模板本体\n\n"
    "### SCHEMA 格式\n\n"
    "```json\n"
    '{"id": "模板ID", "name": "模板中文名", "scene": "cards", "size": "1080x1440", '
    '"fields": [{"key": "title", "type": "string", "label": "标题", "required": true}, '
    '{"key": "steps", "type": "array", "label": "步骤", "items": ['
    '{"key": "title", "type": "string", "label": "步骤名"}, '
    '{"key": "desc", "type": "string", "label": "步骤描述"}]}]}\n'
    "```\n\n"
    "### TEMPLATE 规则\n\n"
    "1. 动态内容用 Jinja2 语法：{{ title }}, {% for step in steps %} ... {% endfor %}, "
    "{% if deco_number %} ... {% endif %}, {{ '%02d' % loop.index }}\n"
    "2. 品牌色通过 brand 变量注入：{{ brand.primary }}（默认 #2B7FD8）, "
    "{{ brand.accent }}（默认 #F4D758）, {{ brand.spot }}（默认 #E84A5F）, "
    "{{ brand.cream }}（默认 #fefcf6）, {{ brand.creamDark }}（默认 #faf6eb）, "
    "{{ brand.ink }}（默认 #1A1A2E）, {{ brand.inkLight }}（默认 #4A4A5A）, "
    "{{ brand.inkFaint }}（默认 #8A8A9A）\n"
    "3. 样式全内联（style 属性），不用 <style> 标签，不用 CSS 变量\n"
    "4. 严格遵守品牌 DNA 禁忌：禁止 glassmorphism / neon / bounce 动画，"
    "禁止 Inter/Roboto/Arial 字体，禁止无样式的 blockquote/ul/ol/table，"
    "禁止纯黑 #000 或纯白 #fff\n"
    "5. 卡片场景固定尺寸：width:1080px; height:1440px\n"
    "6. 品牌三色比例：主色 60% / 强调色 30% / 点缀色 10%\n"
    "7. SCHEMA 中每个 field 的 key 必须在 TEMPLATE 中有对应的 Jinja2 数据槽（{{ key }} 或 {% for item in key %}），"
    "不要在 schema 中声明模板里用不到的字段\n"
    "8. 必须使用品牌色变量（{{ brand.primary }} / {{ brand.accent }} / {{ brand.spot }}），"
    "不要用自定义硬编码颜色替代品牌色\n"
)

_OUTPUT_RE = re.compile(
    r"---SCHEMA---\s*\n(.*?)\n\s*---TEMPLATE---\s*\n(.*)",
    re.DOTALL,
)


class EstherFactory:

    async def get_brand_config(self, user_id: str, db=None) -> dict:
        from app.db.models import EstherBrandConfig

        if db is None:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                return await self._load_brand_config(session, user_id)
        return await self._load_brand_config(db, user_id)

    async def _load_brand_config(self, session, user_id: str) -> dict:
        from sqlalchemy import select
        from app.db.models import EstherBrandConfig

        stmt = select(EstherBrandConfig).where(EstherBrandConfig.user_id == user_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

        if not row:
            return {**_DEFAULT_BRAND_CONFIG}

        avatar_url = ""
        if row.avatar_data and row.avatar_content_type:
            avatar_url = (
                f"/api/esther-factory/brand-config/avatar/{user_id}"
            )

        return {
            "brand_name": row.brand_name or "",
            "avatar_url": avatar_url,
            "gender": row.gender or "man",
            "primary": row.primary or "#2B7FD8",
            "accent": row.accent or "#F4D758",
            "spot": row.spot or "#E84A5F",
        }

    async def save_brand_config(self, user_id: str, config: dict, db=None) -> dict:
        from app.db.models import EstherBrandConfig, generate_ulid
        from sqlalchemy import select

        session_ctx = db
        if session_ctx is None:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                result = await self._upsert_brand_config(session, user_id, config)
                await session.commit()
                return result
        return await self._upsert_brand_config(session_ctx, user_id, config)

    async def _upsert_brand_config(self, session, user_id: str, config: dict) -> dict:
        from sqlalchemy import select
        from app.db.models import EstherBrandConfig, generate_ulid

        stmt = select(EstherBrandConfig).where(EstherBrandConfig.user_id == user_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

        if not row:
            row = EstherBrandConfig(id=generate_ulid(), user_id=user_id)
            session.add(row)

        if "brand_name" in config and config["brand_name"] is not None:
            row.brand_name = config["brand_name"]
        if "gender" in config and config["gender"] is not None:
            row.gender = config["gender"]
        if "primary" in config and config["primary"] is not None:
            row.primary = config["primary"]
        if "accent" in config and config["accent"] is not None:
            row.accent = config["accent"]
        if "spot" in config and config["spot"] is not None:
            row.spot = config["spot"]

        await session.flush()
        return await self._load_brand_config(session, user_id)

    async def save_avatar(self, user_id: str, image_data: bytes, content_type: str, db=None) -> str:
        from app.services.image_store import save_avatar as _save_avatar_file
        avatar_url = await _save_avatar_file(user_id, image_data, content_type)

        from app.db.models import EstherBrandConfig, generate_ulid
        from sqlalchemy import select

        if db is None:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                stmt = select(EstherBrandConfig).where(EstherBrandConfig.user_id == user_id)
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if not row:
                    row = EstherBrandConfig(id=generate_ulid(), user_id=user_id)
                    session.add(row)
                row.avatar_data = None
                row.avatar_content_type = content_type
                await session.commit()
        else:
            stmt = select(EstherBrandConfig).where(EstherBrandConfig.user_id == user_id)
            result = await db.execute(stmt)
            row = result.scalar_one_or_none()
            if not row:
                row = EstherBrandConfig(id=generate_ulid(), user_id=user_id)
                db.add(row)
            row.avatar_data = None
            row.avatar_content_type = content_type
            await db.flush()

        return avatar_url

    async def get_avatar(self, user_id: str, db=None) -> tuple[bytes, str] | None:
        from app.services.image_store import get_avatar_path

        filepath = get_avatar_path(user_id)
        if filepath and filepath.exists():
            data = filepath.read_bytes()
            ext = filepath.suffix.lower()
            ct_map = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif"}
            content_type = ct_map.get(ext, "image/webp")
            return data, content_type

        from app.db.models import EstherBrandConfig
        from sqlalchemy import select

        session = db
        if session is None:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as s:
                session = s
                stmt = select(EstherBrandConfig).where(EstherBrandConfig.user_id == user_id)
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if not row or not row.avatar_data:
                    return None
                data = base64.b64decode(row.avatar_data)
                content_type = row.avatar_content_type or "image/png"
                return data, content_type

        stmt = select(EstherBrandConfig).where(EstherBrandConfig.user_id == user_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row or not row.avatar_data:
            return None
        return base64.b64decode(row.avatar_data), row.avatar_content_type or "image/png"

    async def produce(
        self,
        scene: str,
        description: str,
        template_id: str,
        user_id: str = "",
        brand_overrides: dict | None = None,
        extra_instructions: str = "",
        llm=None,
    ) -> dict:
        brand_config = await self.get_brand_config(user_id) if user_id else {}

        merged_brand_overrides = brand_overrides or {}
        if brand_config.get("primary") and "primary" not in merged_brand_overrides:
            merged_brand_overrides["primary"] = brand_config["primary"]
        if brand_config.get("accent") and "accent" not in merged_brand_overrides:
            merged_brand_overrides["accent"] = brand_config["accent"]
        if brand_config.get("spot") and "spot" not in merged_brand_overrides:
            merged_brand_overrides["spot"] = brand_config["spot"]

        if brand_config.get("brand_name"):
            if extra_instructions:
                extra_instructions += "\n"
            extra_instructions += f"品牌/IP名称：{brand_config['brand_name']}，模板中涉及品牌名的地方请使用此名称，不得使用 Esther 或其他名称。"
        if brand_config.get("avatar_url"):
            if extra_instructions:
                extra_instructions += "\n"
            extra_instructions += f"头像图片路径：{brand_config['avatar_url']}，模板中需要头像时请使用此路径，不得使用其他头像。"

        context = build_context(scene, merged_brand_overrides or None, extra_instructions)

        if llm is None:
            try:
                from app.config import get_settings
                from app.adapters.deepseek import DeepSeekAdapter

                s = get_settings()
                if not s.deepseek_api_key:
                    return {
                        "success": False,
                        "template_id": template_id,
                        "issues": [],
                        "error": "deepseek_api_key 未配置，请在配置管理中填写 API Key",
                    }
                llm = DeepSeekAdapter(
                    api_key=s.deepseek_api_key,
                    base_url=s.deepseek_base_url,
                    model=s.deepseek_model_v3,
                    max_tokens=8192,
                    temperature=0.3,
                )
                logger.info(f"[esther_factory] LLM ready: {s.deepseek_model_v3}, max_tokens=8192")
            except Exception as e:
                logger.error(f"[esther_factory] LLM unavailable: {e}")
                return {
                    "success": False,
                    "template_id": template_id,
                    "issues": [],
                    "error": f"LLM 不可用: {e}",
                }

        user_message = (
            f"场景：{scene}\n\n"
            f"需求描述：{description}\n\n"
            f"模板ID：{template_id}\n\n"
            "请根据上述需求生产一个 Jinja2 模板。"
        )

        try:
            resp = await llm.chat(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"以下是 Esther 设计系统的知识库：\n\n{context}"},
                    {"role": "user", "content": user_message},
                ],
            )
            raw_output = (resp.get("content") or "").strip()
        except Exception as e:
            logger.error(f"[esther_factory] LLM call failed: {e}")
            return {
                "success": False,
                "template_id": template_id,
                "issues": [],
                "error": f"LLM call failed: {e}",
            }

        parsed = _parse_llm_output(raw_output)
        if not parsed:
            return {
                "success": False,
                "template_id": template_id,
                "issues": [],
                "error": "无法解析 LLM 输出，未找到 ---SCHEMA--- / ---TEMPLATE--- 分隔符",
                "raw_output": raw_output[:500],
            }

        schema_json, template_html = parsed

        if "id" not in schema_json:
            schema_json["id"] = template_id
        if "scene" not in schema_json:
            schema_json["scene"] = scene

        template_html = _auto_fix_forbidden(template_html)

        meta_json = {
            "scene": scene,
            "description": description,
            "brand": {
                "use_default": not bool(brand_overrides),
                "overrides": brand_overrides or {},
            },
        }

        issues = validate_template_package(schema_json, template_html, meta_json)
        errors = [i for i in issues if i["level"] == "error"]

        if not errors:
            await self._save_template_db(
                user_id, template_id, schema_json, template_html, meta_json, scene
            )
            logger.info(f"[esther_factory] template '{template_id}' saved to DB for user '{user_id}'")
        else:
            logger.warning(
                f"[esther_factory] template '{template_id}' has {len(errors)} errors, not saved"
            )

        return {
            "success": len(errors) == 0,
            "template_id": template_id,
            "issues": issues,
            "error": None if not errors else f"{len(errors)} 个质检错误，模板未保存",
        }

    async def _save_template_db(
        self,
        user_id: str,
        template_id: str,
        schema_json: dict,
        template_html: str,
        meta_json: dict,
        scene: str = "cards",
    ) -> None:
        from app.db.models import EstherTemplate, generate_ulid
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            stmt = select(EstherTemplate).where(
                EstherTemplate.user_id == user_id,
                EstherTemplate.template_id == template_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if not row:
                row = EstherTemplate(
                    id=generate_ulid(),
                    user_id=user_id,
                    template_id=template_id,
                )
                session.add(row)

            row.schema_json = schema_json
            row.template_html = template_html
            row.meta_json = meta_json
            row.scene = scene
            await session.commit()

    async def _list_templates_db(self, user_id: str) -> list[dict]:
        from app.db.models import EstherTemplate
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            stmt = (
                select(EstherTemplate)
                .where(EstherTemplate.user_id == user_id)
                .order_by(EstherTemplate.created_at.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [
                {
                    "id": row.template_id,
                    "name": row.schema_json.get("name", row.template_id) if row.schema_json else row.template_id,
                    "scene": row.scene or "unknown",
                    "fields_count": len(row.schema_json.get("fields", [])) if row.schema_json else 0,
                }
                for row in rows
            ]

    async def _get_template_db(self, user_id: str, template_id: str) -> dict | None:
        from app.db.models import EstherTemplate
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            stmt = select(EstherTemplate).where(
                EstherTemplate.user_id == user_id,
                EstherTemplate.template_id == template_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if not row:
                return None
            return {
                "template_id": row.template_id,
                "schema_json": row.schema_json,
                "template_html": row.template_html,
                "meta_json": row.meta_json,
                "scene": row.scene,
            }

    async def _delete_template_db(self, user_id: str, template_id: str) -> bool:
        from app.db.models import EstherTemplate
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import select, delete

        async with AsyncSessionLocal() as session:
            stmt = delete(EstherTemplate).where(
                EstherTemplate.user_id == user_id,
                EstherTemplate.template_id == template_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def render(self, template_id: str, data: dict, brand: dict | None = None, user_id: str = "") -> str:
        brand_config = await self.get_brand_config(user_id) if user_id else {}
        config_brand = {}
        if brand_config.get("primary"):
            config_brand["primary"] = brand_config["primary"]
        if brand_config.get("accent"):
            config_brand["accent"] = brand_config["accent"]
        if brand_config.get("spot"):
            config_brand["spot"] = brand_config["spot"]
        if brand_config.get("avatar_url"):
            config_brand["avatar_url"] = brand_config["avatar_url"]
        if brand_config.get("brand_name"):
            config_brand["brand_name"] = brand_config["brand_name"]
        merged = {**config_brand, **(brand or {})}

        tpl = await self._get_template_db(user_id, template_id) if user_id else None
        if tpl and tpl.get("template_html"):
            final_brand = {**DEFAULT_BRAND}
            if merged:
                final_brand.update(merged)
            env = Environment(loader=BaseLoader(), autoescape=False)
            jinja_template = env.from_string(tpl["template_html"])
            return jinja_template.render(**data, brand=final_brand)

        return _render_from_file(template_id, data, merged)

    async def get_schema(self, user_id: str, template_id: str) -> dict | None:
        tpl = await self._get_template_db(user_id, template_id) if user_id else None
        if tpl:
            return tpl.get("schema_json")
        from .renderer import get_schema as _get_schema_file
        return _get_schema_file(template_id)

    async def get_meta(self, user_id: str, template_id: str) -> dict | None:
        tpl = await self._get_template_db(user_id, template_id) if user_id else None
        if tpl:
            return tpl.get("meta_json")
        from .renderer import get_meta as _get_meta_file
        return _get_meta_file(template_id)

    async def list_templates(self, user_id: str) -> list[dict]:
        if user_id:
            return await self._list_templates_db(user_id)
        return []

    def list_scenes(self) -> list[dict]:
        return list_scenes()

    async def import_template(
        self,
        user_id: str,
        template_id: str,
        schema_json: dict,
        template_html: str,
        meta_json: dict | None = None,
        overwrite: bool = False,
    ) -> dict:
        existing = await self._get_template_db(user_id, template_id)
        if existing and not overwrite:
            return {
                "success": False,
                "template_id": template_id,
                "issues": [],
                "error": f"模板 '{template_id}' 已存在，如需覆盖请开启 overwrite 选项",
            }

        if not meta_json:
            meta_json = {
                "scene": schema_json.get("scene", "cards"),
                "description": schema_json.get("name", ""),
                "brand": {"use_default": True, "overrides": {}},
                "imported": True,
            }
        else:
            meta_json["imported"] = True

        if "id" not in schema_json:
            schema_json["id"] = template_id

        issues = validate_template_package(schema_json, template_html, meta_json)
        errors = [i for i in issues if i["level"] == "error"]

        if errors:
            return {
                "success": False,
                "template_id": template_id,
                "issues": issues,
                "error": f"{len(errors)} 个质检错误，导入失败",
            }

        scene = meta_json.get("scene", schema_json.get("scene", "cards"))
        await self._save_template_db(user_id, template_id, schema_json, template_html, meta_json, scene)
        logger.info(f"[esther_factory] template '{template_id}' imported to DB for user '{user_id}'")

        return {
            "success": True,
            "template_id": template_id,
            "issues": issues,
            "error": None,
        }

    async def export_template(self, user_id: str, template_id: str) -> dict | None:
        tpl = await self._get_template_db(user_id, template_id)
        if not tpl:
            return None

        return {
            "template_id": tpl["template_id"],
            "schema": tpl["schema_json"],
            "template_html": tpl["template_html"],
            "meta": tpl["meta_json"],
        }


def _parse_llm_output(raw: str) -> tuple[dict, str] | None:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    m = _OUTPUT_RE.search(cleaned)
    if not m:
        return None

    schema_str = m.group(1).strip()
    template_str = m.group(2).strip()

    if schema_str.startswith("```"):
        schema_str = schema_str.split("\n", 1)[-1]
    if schema_str.endswith("```"):
        schema_str = schema_str.rsplit("```", 1)[0]
    schema_str = schema_str.strip()

    try:
        schema_json = json.loads(schema_str)
    except json.JSONDecodeError as e:
        logger.warning(f"[esther_factory] schema JSON parse error: {e}")
        return None

    return schema_json, template_str