"""Skill abstract base class.

Corresponds to architecture doc Ch.5 (Layer C).
All concrete capabilities (search/analyze/image_gen/publish) inherit this.
Red line: skills layer must NOT import LangGraph or make flow decisions.

可插拔 Skill 架构（v2）：
- 每个节点（analyze/image_gen/copywrite/audit）对应一个 node_type
- 同一个 node_type 下可注册多个 Skill 实现（如 copywrite 节点下有「活泼少女」「知性优雅」等多个 Skill）
- 第三方 Skill 通过 backend/skills/ 目录扫描自动注册
- 节点运行时按 state.model_settings.skill_name 从 registry 加载对应 Skill
- 风格/温度/模型作为 Skill 构造参数注入，不再硬编码到 prompt 字符串
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.engine.schemas import Permission
from app.agents.clarification_schema import ClarifyFieldMeta


class Skill(ABC):
    """Capability-layer base class.

    每个 Skill 包装一次具体的能力调用：
    - xhs_search: 小红书搜索（via MCP）
    - vl_analyze: Qwen-VL 图像理解
    - generate_image: 通义万相/即梦图片生成
    - analyze: 选题分析（viral_analyzer + LLM 归因）
    - copywrite: 文案生成
    - audit: 合规审核

    可插拔元数据（子类通过类属性声明）：
    - node_type: 该 Skill 服务于哪个节点（"analyze"/"copywrite"/"image_gen"/"audit"）
    - name: Skill 唯一标识（如 "lively_girl_copywrite"），用于前端选择和后端路由
    - display_name: 前端展示名（如 "活泼少女风文案"）
    - description: Skill 描述（前端 tooltip 用）
    - default_config: 默认配置（温度/模型等），可被用户在右侧工作区覆盖

    子类通过 `required_permissions` 声明所需权限，由 Executor/Harness
    在 execute() 之前调用 permission_gate.require() 做门控。
    """

    # ===== 可插拔元数据（子类必须声明） =====
    node_type: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    default_config: dict[str, Any] = {}

    # ===== 自描述提示词系统 =====
    prompt_guidance: str = ""
    platform: str = ""
    trigger_words: list[str] = []

    # ===== 路由分类（skill_router 使用）=====
    skill_category: str = ""
    skill_priority: str = ""

    # ===== 通用元数据 =====
    input_schema: type[BaseModel] = BaseModel
    output_schema: type[BaseModel] = BaseModel
    execution_policy: Literal["direct", "mcp", "sandbox"] = "direct"
    required_permissions: list[Permission] = []

    # ===== 渐进式澄清元数据 =====
    clarify_meta: dict[str, ClarifyFieldMeta] = {}

    @abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the capability call, return structured result.

        约定：实现里不再做权限校验（由调用方统一在 execute 之前门控）。
        """
        raise NotImplementedError

    @classmethod
    def metadata(cls) -> dict[str, Any]:
        """返回 Skill 元数据（供前端渲染下拉框、tooltip）。"""
        module_file = getattr(cls, "__module__", "")
        is_third_party = module_file.startswith("_third_party_skill_")
        return {
            "node_type": cls.node_type,
            "name": cls.name,
            "display_name": cls.display_name or cls.name,
            "description": cls.description,
            "default_config": cls.default_config,
            "is_third_party": is_third_party,
            "is_prompt_skill": issubclass(cls, PromptDrivenSkill),
            "skill_category": cls.skill_category,
            "skill_priority": cls.skill_priority,
        }


class PromptDrivenSkill(Skill):
    """SKILL.md 驱动的 Skill —— 零代码新增策划/分析/审核类能力。

    只需提供 skill_md_path（SKILL.md 文件路径），基类自动：
    1. 读取 SKILL.md 作为 prompt 模板
    2. 注入用户画像（有/无双轨）
    3. 注入 references 知识
    4. 调 LLM 生成结果
    5. 返回结构化 dict

    子类只需声明类属性，不需要写 execute()。
    """

    skill_md_path: str = ""

    class _InputSchema(BaseModel):
        topic: str = Field(default="", description="选题主题（选题评估用）")
        content: str = Field(default="", description="待检查内容文本（质量关卡用）")
        platform: str = Field(default="", description="目标平台（小红书/抖音/知乎等）")
        extra_context: str = Field(default="", description="补充背景信息")

    input_schema: type[BaseModel] = _InputSchema
    reference_paths: list[str] = []
    _md_cache: str | None = None
    _ref_cache: str | None = None

    CARD_HTML_OPEN = "<!--card-html-->"
    CARD_HTML_CLOSE = "<!--/card-html-->"

    _CARD_THEME_CSS = """<style>
:root{color-scheme:light dark;
--surface:#faf9f7;--card:#ffffff;--elevated:#ffffff;
--text:#403c35;--text-strong:#211e1a;--muted:#6e6960;
--border:#e8e4dc;--border-strong:#d6d0c5;
--accent:#bd4531;--accent-fill:#bd4531;--accent-fg:#ffffff;
--ok:#15803d;--warn:#b45309;--danger:#dc2626;--info:#2563eb;
--radius:10px;--radius-full:9999px;
--font-body:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
--font-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--accent-subtle:color-mix(in srgb,var(--accent) 10%,transparent);
--ok-subtle:color-mix(in srgb,var(--ok) 10%,transparent);
--warn-subtle:color-mix(in srgb,var(--warn) 12%,transparent);
--danger-subtle:color-mix(in srgb,var(--danger) 10%,transparent);
--info-subtle:color-mix(in srgb,var(--info) 10%,transparent)}
@media(prefers-color-scheme:dark){:root{
--surface:#0e1015;--card:#161920;--elevated:#191c24;
--text:#d4d4d8;--text-strong:#f4f4f5;--muted:#8b8b94;
--border:#1e2028;--border-strong:#2e3040;
--accent:#ff5c5c;--accent-fill:#d13c3c;--accent-fg:#ffffff;
--ok:#22c55e;--warn:#f59e0b;--danger:#ef4444;--info:#3b82f6}}
*{box-sizing:border-box;margin:0;padding:0}
html,body{margin:0;padding:0}
body{font:14px/1.5 var(--font-body);color:var(--text);background:var(--elevated)}
h1,h2,h3{margin:0 0 8px;color:var(--text-strong);font-weight:600}
h1{font-size:18px}h2{font-size:16px}h3{font-size:14px}
p{margin:0 0 8px}a{color:var(--accent)}
.ui-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px}
.badge{display:inline-block;font-size:12px;padding:2px 10px;border-radius:999px;background:var(--accent-subtle);color:var(--accent)}
.metric{font-size:24px;font-weight:600;color:var(--text-strong)}
.muted{color:var(--muted)}
</style>"""

    @staticmethod
    def _strip_non_html_prefix(text: str) -> str:
        """剥离 LLM 输出中 HTML 标签前的说明性文字。

        LLM 有时会在 <!--card-html--> 标记内部开头添加设计思路/配色解释等文字，
        如 '>为什么是青蓝...' 或 'DEVELOPER TOOL · CLI' 等。
        此方法找到第一个 < 字符（HTML 标签开始），删除之前所有非 HTML 文本。
        """
        text = text.strip()
        if text.startswith("<"):
            return text
        first_tag = text.find("<")
        if first_tag <= 0:
            return text
        prefix = text[:first_tag].strip()
        if prefix:
            import logging
            logging.getLogger(__name__).warning(
                f"[_wrap_card_html] Stripped non-HTML prefix ({len(prefix)} chars): "
                f"{prefix[:80]}{'...' if len(prefix) > 80 else ''}"
            )
        return text[first_tag:]

    @staticmethod
    def _strip_non_html_suffix(text: str) -> str:
        """剥离 LLM 输出中 HTML 标签后的说明性文字。"""
        text = text.strip()
        last_close = text.rfind(">")
        if last_close < 0 or last_close >= len(text) - 1:
            return text
        suffix = text[last_close + 1:].strip()
        if suffix and not suffix.startswith("<"):
            import logging
            logging.getLogger(__name__).warning(
                f"[_wrap_card_html] Stripped non-HTML suffix ({len(suffix)} chars): "
                f"{suffix[:80]}{'...' if len(suffix) > 80 else ''}"
            )
            return text[:last_close + 1]
        return text

    @staticmethod
    def _wrap_card_html(html_block: str) -> str:
        """包裹卡片 HTML 为完整文档。

        卡片 HTML 在 iframe 中渲染，必须是自包含的——
        不注入外部主题 CSS，避免 .card / body / * 等选择器冲突覆盖卡片自身样式。
        仅补齐缺失的 <meta> 标签。

        viewport 宽度保持 1080，与卡片 CSS 设计尺寸一致（.xhs-card 1080×1440）。
        前端 iframe 通过 transform:scale() 缩放到容器大小。

        自动清理：剥离 LLM 混入的说明性文字（HTML 标签前后的非 HTML 文本）。
        """
        stripped = PromptDrivenSkill._strip_non_html_prefix(html_block)

        if stripped.lower().startswith("<!doctype") or stripped.lower().startswith("<html"):
            if "<meta " not in stripped[:500]:
                if "<head>" in stripped:
                    head_open = stripped.index("<head>") + len("<head>")
                    stripped = stripped[:head_open] + '<meta charset="utf-8"><meta name="viewport" content="width=1080,initial-scale=1">' + stripped[head_open:]
            else:
                import re
                stripped = re.sub(r'<meta\s+name=["\']viewport["\'][^>]*>', '<meta name="viewport" content="width=1080,initial-scale=1">', stripped, flags=re.IGNORECASE)
            return PromptDrivenSkill._strip_non_html_suffix(stripped)

        wrapped = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=1080,initial-scale=1"></head><body>{stripped}</body></html>"""
        return PromptDrivenSkill._strip_non_html_suffix(wrapped)

    @staticmethod
    def _extract_card_pages(raw: str) -> tuple[list[dict], list[str]]:
        """从 LLM 输出中提取 <!--card-html--> 块，构建 card_draft.pages 结构。

        每个 <!--card-html-->...<!--/card-html--> 块对应一张卡片页面。
        借鉴 Easel show_widget：对提取的 HTML 调用 _wrap_card_html 包裹主题 CSS。
        返回 (pages, html_urls)，无卡片时返回 ([], [])。
        """
        import re
        import uuid

        if not raw or PromptDrivenSkill.CARD_HTML_OPEN not in raw:
            return [], []

        pattern = re.escape(PromptDrivenSkill.CARD_HTML_OPEN) + r"([\s\S]*?)" + re.escape(PromptDrivenSkill.CARD_HTML_CLOSE)
        blocks = re.findall(pattern, raw)
        if not blocks:
            return [], []

        pages = []
        html_urls = []
        for i, html_block in enumerate(blocks):
            html_block = html_block.strip()
            if not html_block:
                continue
            wrapped = PromptDrivenSkill._wrap_card_html(html_block)
            page_id = f"page_{uuid.uuid4().hex[:8]}"
            page_type = "cover" if i == 0 else ("ending" if i == len(blocks) - 1 else "content")
            pages.append({
                "id": page_id,
                "type": page_type,
                "title": f"卡片 {i + 1}",
                "htmlContent": wrapped,
            })
            html_urls.append(f"card-html://inline/{page_id}")

        return pages, html_urls

    _FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    @classmethod
    def _load_skill_md(cls) -> str:
        cache = cls.__dict__.get("_md_cache")
        if cache is not None:
            return cache
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "agents" / "prompts" / "skills" / cls.skill_md_path
        raw = p.read_text(encoding="utf-8") if p.exists() else ""
        match = cls._FRONTMATTER_RE.match(raw)
        content = raw[match.end():] if match else raw
        cls._md_cache = content
        return content

    @classmethod
    def _load_references(cls) -> str:
        cache = cls.__dict__.get("_ref_cache")
        if cache is not None:
            return cache
        from pathlib import Path
        parts: list[str] = []
        base = Path(__file__).resolve().parent.parent / "agents" / "prompts"
        for ref in cls.reference_paths:
            rp = base / ref
            if rp.exists():
                content = rp.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"---\n# {ref}\n\n{content}")
        result = "\n\n".join(parts)
        cls._ref_cache = result
        return result

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        llm = inputs.get("llm")
        if not llm:
            return {"error": "LLM not available", "verdict": "❌ LLM不可用"}

        skill_md = self._load_skill_md()
        if not skill_md:
            return {"error": f"SKILL.md not found: {self.skill_md_path}", "verdict": "❌ 配置缺失"}

        references = self._load_references()

        user_profile = inputs.get("user_profile") or {}
        profile_block = ""
        if user_profile:
            from app.api.schemas.profile import UserProfile
            try:
                profile_obj = UserProfile(**user_profile)
                profile_block = profile_obj.to_prompt_context()
            except Exception:
                profile_block = ""
        no_profile_hint = ""
        if not profile_block:
            no_profile_hint = "\n\n[提示：用户未提供创作者画像，使用通用标准评估。提供画像可获得更精准的匹配评估。]"

        topic = inputs.get("topic", "")
        content = inputs.get("content", "")
        platform = inputs.get("platform", "")
        extra_context = inputs.get("extra_context", "")

        user_msg_parts = []
        if topic:
            user_msg_parts.append(f"选题: {topic}")
        if content:
            user_msg_parts.append(f"待检查内容:\n{content}")
        if platform:
            user_msg_parts.append(f"目标平台: {platform}")
        if extra_context:
            user_msg_parts.append(f"补充背景: {extra_context}")
        if not user_msg_parts:
            user_msg_parts.append("(未提供具体输入，请根据上下文执行)")
        user_msg = "\n".join(user_msg_parts)

        system_parts = [skill_md.strip()]
        if references:
            system_parts.append(f"\n\n## 领域知识参考\n\n{references}")
        if profile_block:
            system_parts.append(f"\n\n## 创作者画像\n\n{profile_block}")
        system_parts.append(no_profile_hint)
        system_prompt = "\n".join(system_parts)

        try:
            from app.engine.governance.skill_hooks import skill_governance
            await skill_governance.pre_llm_call(estimated_tokens=3000)

            is_card_skill = "card" in self.name or "poster" in self.name or "infographic" in self.name
            card_max_tokens = 8192 if is_card_skill else None

            resp = await llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=card_max_tokens,
            )
            raw = resp.get("content", "")
            skill_governance.post_llm_call(tokens_used=len(raw) * 2)

            safety_warnings = skill_governance.content_safety_check(raw)
            if safety_warnings:
                from app.engine.governance.skill_hooks import logger as gov_logger
                gov_logger.warning(f"[{self.name}] content safety: {safety_warnings}")

            # Auto-fix: LLM may wrap HTML in markdown code blocks instead of
            # <!--card-html--> markers. Fix before extracting card pages.
            from app.engine.harness.executor.loop import LoopExecutor
            raw = LoopExecutor._fix_card_html_markers(raw)

            card_pages, html_urls = self._extract_card_pages(raw)

            result = {
                "report": raw,
                "platform": platform or "未指定",
                "has_profile": bool(profile_block),
                "_source": "llm",
            }
            if topic:
                result["topic"] = topic
            if content:
                result["content_length"] = len(content)
            if card_pages:
                result["card_draft"] = {
                    "title": topic or "",
                    "template": self.name,
                    "pages": card_pages,
                    "htmlUrls": html_urls,
                }
            return result
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"[{self.name}] LLM call failed: {e}")
            return {"error": str(e), "verdict": "❌ 评估失败", "_source": "fallback"}