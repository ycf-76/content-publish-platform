"""Template registry.

Phase 1 scope:
- Define template manifest models.
- Register builtin templates.
- Provide filtered metadata lookups for the frontend and image plan matcher.

Later phases will add third-party template package scanning, user templates,
format plans, and renderer resolution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlatformFormat(BaseModel):
    """A platform-specific output format."""

    platform: str
    format: str = "3:4"
    width: int = 1080
    height: int = 1440
    safe_area: dict[str, int] = Field(default_factory=dict)


class PlatformProfile(BaseModel):
    """A social platform with supported output formats."""

    platform: str
    display_name: str
    formats: dict[str, PlatformFormat] = Field(default_factory=dict)


class TemplateField(BaseModel):
    """A single editable slot in a template schema."""

    key: str
    type: str
    label: str = ""
    required: bool = False


class TemplateManifest(BaseModel):
    """Declarative metadata for one renderable template."""

    id: str
    name: str
    category: list[str] = Field(default_factory=list)
    description: str = ""
    platforms: dict[str, PlatformFormat] = Field(default_factory=dict)
    fields: list[TemplateField] = Field(default_factory=list)
    page_types: list[str] = Field(default_factory=list)
    page_type_fields: dict[str, list[str]] = Field(default_factory=dict)
    category_keywords: list[str] = Field(default_factory=list)
    theme: dict[str, str] = Field(default_factory=dict)
    default_decoration: dict[str, Any] = Field(default_factory=dict)
    renderer: str = "frontend_builtin"
    source: str = "builtin"

    def metadata(self) -> dict[str, Any]:
        """Return a JSON-friendly summary used by the API."""
        return self.model_dump()


def _pf(
    platform: str,
    format_name: str,
    width: int,
    height: int,
    safe_area: dict[str, int] | None = None,
) -> PlatformFormat:
    return PlatformFormat(
        platform=platform,
        format=format_name,
        width=width,
        height=height,
        safe_area=safe_area or {},
    )


def _field(key: str, type_name: str, label: str, required: bool = False) -> TemplateField:
    return TemplateField(key=key, type=type_name, label=label, required=required)


def _all_platform_formats() -> dict[str, PlatformFormat]:
    return {
        "xiaohongshu": _pf(
            "xiaohongshu",
            "3:4",
            1080,
            1440,
            {"top": 80, "bottom": 80, "left": 60, "right": 60},
        ),
        "douyin": _pf(
            "douyin",
            "9:16",
            1080,
            1920,
            {"top": 120, "bottom": 200, "left": 40, "right": 40},
        ),
        "wechat": _pf(
            "wechat",
            "3:4",
            1080,
            1440,
            {"top": 70, "bottom": 70, "left": 60, "right": 60},
        ),
    }


_ALL_PAGE_TYPES = [
    "cover",
    "content",
    "quote",
    "list",
    "dark_panel",
    "end_page",
    "compare",
    "icon_text",
    "steps",
    "code_panel",
    "numbered_cards",
    "newspaper",
    "big_quote",
]


PLATFORM_PROFILES: dict[str, PlatformProfile] = {
    "xiaohongshu": PlatformProfile(
        platform="xiaohongshu",
        display_name="小红书",
        formats={
            "3:4": _pf(
                "xiaohongshu",
                "3:4",
                1080,
                1440,
                {"top": 80, "bottom": 80, "left": 60, "right": 60},
            ),
        },
    ),
    "douyin": PlatformProfile(
        platform="douyin",
        display_name="抖音",
        formats={
            "9:16": _pf(
                "douyin",
                "9:16",
                1080,
                1920,
                {"top": 120, "bottom": 200, "left": 40, "right": 40},
            ),
        },
    ),
    "wechat": PlatformProfile(
        platform="wechat",
        display_name="微信",
        formats={
            "3:4": _pf(
                "wechat",
                "3:4",
                1080,
                1440,
                {"top": 70, "bottom": 70, "left": 60, "right": 60},
            ),
            "1:1": _pf(
                "wechat",
                "1:1",
                1080,
                1080,
                {"top": 60, "bottom": 60, "left": 60, "right": 60},
            ),
        },
    ),
}


PAGE_TYPE_FIELDS: dict[str, list[TemplateField]] = {
    "cover": [
        _field("title", "string", "标题", True),
        _field("subtitle", "string", "副标题"),
        _field("footer", "string", "署名"),
        _field("highlight", "string", "高亮关键词"),
        _field("tag", "string", "分类标签"),
    ],
    "content": [
        _field("title", "string", "小标题"),
        _field("content", "text", "正文", True),
    ],
    "quote": [
        _field("content", "text", "金句", True),
        _field("footer", "string", "出处"),
    ],
    "list": [
        _field("title", "string", "清单标题"),
        _field("listItems", "array", "清单项", True),
    ],
    "dark_panel": [
        _field("emoji", "string", "装饰 emoji"),
        _field("decoNumber", "string", "装饰数字"),
        _field("listItems", "array", "洞察列表", True),
    ],
    "end_page": [
        _field("content", "text", "结束语"),
        _field("ctaText", "string", "行动号召"),
        _field("footer", "string", "署名"),
        _field("decoNumber", "string", "装饰引号"),
    ],
    "compare": [
        _field("compareLeftTitle", "string", "左栏标题"),
        _field("compareRightTitle", "string", "右栏标题"),
        _field("compareLeftItems", "array", "左栏要点"),
        _field("compareRightItems", "array", "右栏要点"),
    ],
    "icon_text": [
        _field("iconTextPairs", "array", "图标文字对"),
    ],
    "steps": [
        _field("title", "string", "步骤标题"),
        _field("decoNumber", "string", "装饰数字"),
        _field("steps", "array", "步骤列表", True),
    ],
    "code_panel": [
        _field("title", "string", "代码标题"),
        _field("codeContent", "text", "代码内容", True),
        _field("codeLang", "string", "代码语言"),
    ],
    "numbered_cards": [
        _field("title", "string", "编号卡片标题"),
        _field("decoNumber", "string", "装饰数字"),
        _field("numberedItems", "array", "编号要点", True),
    ],
    "newspaper": [
        _field("masthead", "string", "报头"),
        _field("newspaperCols", "array", "新闻栏目", True),
    ],
    "big_quote": [
        _field("content", "text", "金句", True),
        _field("footer", "string", "署名"),
        _field("decoNumber", "string", "装饰引号"),
    ],
}


BUILTIN_TEMPLATES: list[TemplateManifest] = [
    TemplateManifest(
        id="minimal_white",
        name="极简白底",
        category=["知识", "干货", "教育"],
        description="白底黑字红色点缀，适合干货清单、知识科普",
        platforms=_all_platform_formats(),
        fields=[
            _field("title", "string", "标题", True),
            _field("subtitle", "string", "副标题"),
            _field("content", "text", "正文"),
            _field("listItems", "array", "清单项"),
        ],
        page_types=_ALL_PAGE_TYPES,
        page_type_fields={
            "cover": ["title", "subtitle", "footer"],
            "content": ["title", "content"],
            "quote": ["content", "footer"],
            "list": ["title", "listItems"],
        },
        category_keywords=[
            "知识", "干货", "科普", "教育", "学习", "职场", "方法", "技巧",
            "思维", "认知", "提升", "成长", "读书", "笔记",
        ],
        default_decoration={
            "type": "noise",
            "color1": "#92400E",
            "color2": "#78716C",
            "opacity": 0.06,
            "param1": 0.5,
            "param2": 1,
        },
        theme={
            "bg": "#FFFFFF",
            "surface": "#F7F8FA",
            "text": "#1A1A1A",
            "subtext": "#6B7280",
            "accent": "#FF2442",
            "accentSoft": "#FFE8EC",
        },
    ),
    TemplateManifest(
        id="warm_card",
        name="暖色卡片",
        category=["生活方式", "美食", "旅行"],
        description="米黄底深棕字，温馨感，适合生活方式、美食、旅行",
        platforms=_all_platform_formats(),
        fields=[
            _field("title", "string", "标题", True),
            _field("subtitle", "string", "副标题"),
            _field("content", "text", "正文"),
            _field("listItems", "array", "清单项"),
        ],
        page_types=_ALL_PAGE_TYPES,
        page_type_fields={
            "cover": ["title", "subtitle", "footer"],
            "content": ["title", "content"],
            "quote": ["content", "footer"],
            "list": ["title", "listItems"],
        },
        category_keywords=[
            "美食", "食谱", "早餐", "晚餐", "午餐", "旅行", "旅游", "生活方式",
            "家居", "穿搭", "美妆", "护肤", "日常", "生活", "咖啡", "烘焙",
            "探店", "节日", "宠物", "花艺",
        ],
        default_decoration={
            "type": "gradient_orbs",
            "color1": "#FDE68A",
            "color2": "#FCA5A5",
            "opacity": 0.3,
            "param1": 0.25,
            "param2": 0.65,
        },
        theme={
            "bg": "#FBF6EC",
            "surface": "#F0E6D2",
            "text": "#4A3728",
            "subtext": "#8B7355",
            "accent": "#D97706",
            "accentSoft": "#FDE68A",
        },
    ),
    TemplateManifest(
        id="dark_tech",
        name="深色科技",
        category=["科技", "AI", "编程"],
        description="深蓝底白字霓虹绿点缀，适合科技、AI、编程",
        platforms=_all_platform_formats(),
        fields=[
            _field("title", "string", "标题", True),
            _field("subtitle", "string", "副标题"),
            _field("content", "text", "正文"),
            _field("steps", "array", "步骤"),
        ],
        page_types=_ALL_PAGE_TYPES,
        page_type_fields={
            "cover": ["title", "subtitle", "footer"],
            "content": ["title", "content"],
            "quote": ["content", "footer"],
            "list": ["title", "listItems"],
        },
        category_keywords=[
            "科技", "ai", "编程", "代码", "数码", "互联网", "python",
            "javascript", "技术", "开发", "软件", "工具", "效率", "电脑",
            "手机", "算法", "数据", "机器学习", "前端", "后端",
        ],
        default_decoration={
            "type": "grid_lines",
            "color1": "#94A3B8",
            "color2": "#475569",
            "opacity": 0.12,
            "param1": 80,
            "param2": 1,
        },
        theme={
            "bg": "#0F172A",
            "surface": "#1E293B",
            "text": "#F1F5F9",
            "subtext": "#94A3B8",
            "accent": "#10B981",
            "accentSoft": "#064E3B",
        },
    ),
    TemplateManifest(
        id="esther_brand",
        name="Esther 品牌",
        category=["知识", "干货", "职场"],
        description="品牌三色加奶白底加衬线标题，适合知识科普、干货分享",
        platforms=_all_platform_formats(),
        fields=[
            _field("title", "string", "标题", True),
            _field("subtitle", "string", "副标题"),
            _field("content", "text", "正文"),
            _field("steps", "array", "步骤"),
        ],
        page_types=_ALL_PAGE_TYPES,
        page_type_fields={
            "cover": ["title", "subtitle", "footer", "highlight", "tag"],
            "content": ["title", "content"],
            "quote": ["content", "footer"],
            "list": ["title", "listItems", "footer"],
            "dark_panel": ["title", "emoji", "decoNumber", "listItems", "content"],
            "end_page": ["title", "content", "ctaText", "footer", "decoNumber"],
        },
        category_keywords=[
            "知识", "干货", "科普", "教育", "学习", "职场", "方法", "技巧",
            "思维", "认知", "提升", "成长", "读书", "笔记",
        ],
        default_decoration={
            "type": "gradient_orbs",
            "color1": "#2B7FD8",
            "color2": "#F4D758",
            "opacity": 0.25,
            "param1": 0.3,
            "param2": 0.7,
        },
        theme={
            "bg": "#FEFCF6",
            "surface": "#FAF6EB",
            "text": "#1A1A2E",
            "subtext": "#4A4A5A",
            "accent": "#2B7FD8",
            "accentSoft": "#D6E9F8",
        },
    ),
    TemplateManifest(
        id="esther_dark",
        name="Esther 墨韵",
        category=["科技", "AI", "深度思考"],
        description="深色墨底加金色强调加衬线标题，适合科技、AI、编程",
        platforms=_all_platform_formats(),
        fields=[
            _field("title", "string", "标题", True),
            _field("subtitle", "string", "副标题"),
            _field("content", "text", "正文"),
            _field("steps", "array", "步骤"),
        ],
        page_types=_ALL_PAGE_TYPES,
        page_type_fields={
            "cover": ["title", "subtitle", "footer", "highlight", "tag"],
            "content": ["title", "content"],
            "quote": ["content", "footer"],
            "list": ["title", "listItems", "footer"],
            "dark_panel": ["title", "emoji", "decoNumber", "listItems", "content"],
            "end_page": ["title", "content", "ctaText", "footer", "decoNumber"],
        },
        category_keywords=[
            "科技", "ai", "编程", "代码", "数码", "互联网", "python",
            "javascript", "技术", "开发", "软件", "工具", "效率", "电脑",
            "手机", "算法", "数据", "机器学习", "前端", "后端",
        ],
        default_decoration={
            "type": "geometric",
            "color1": "#F4D758",
            "color2": "#2B7FD8",
            "opacity": 0.12,
            "param1": 0.7,
            "param2": 30,
        },
        theme={
            "bg": "#1A1A2E",
            "surface": "#2A2A3E",
            "text": "#E8E4DE",
            "subtext": "#8A8A9A",
            "accent": "#F4D758",
            "accentSoft": "#3A3A4E",
        },
    ),
    TemplateManifest(
        id="esther_warm",
        name="Esther 暖阳",
        category=["生活方式", "美食", "旅行"],
        description="暖奶底加橙棕强调加圆润字体，适合生活方式、美食、旅行",
        platforms=_all_platform_formats(),
        fields=[
            _field("title", "string", "标题", True),
            _field("subtitle", "string", "副标题"),
            _field("content", "text", "正文"),
            _field("listItems", "array", "清单项"),
        ],
        page_types=_ALL_PAGE_TYPES,
        page_type_fields={
            "cover": ["title", "subtitle", "footer", "highlight", "tag"],
            "content": ["title", "content"],
            "quote": ["content", "footer"],
            "list": ["title", "listItems", "footer"],
            "dark_panel": ["title", "emoji", "decoNumber", "listItems", "content"],
            "end_page": ["title", "content", "ctaText", "footer", "decoNumber"],
        },
        category_keywords=[
            "美食", "食谱", "早餐", "晚餐", "午餐", "旅行", "旅游", "生活方式",
            "家居", "穿搭", "美妆", "护肤", "日常", "生活", "咖啡", "烘焙",
            "探店", "节日", "宠物", "花艺",
        ],
        default_decoration={
            "type": "gradient_orbs",
            "color1": "#F4D758",
            "color2": "#E84A5F",
            "opacity": 0.2,
            "param1": 0.25,
            "param2": 0.6,
        },
        theme={
            "bg": "#FFF8F0",
            "surface": "#FFE8D6",
            "text": "#3E2F23",
            "subtext": "#8B7355",
            "accent": "#D97706",
            "accentSoft": "#FDE68A",
        },
    ),
]


class TemplateRegistry:
    """In-memory template registry.

    Phase 1 keeps builtin templates in Python. Later phases will make this
    scan `backend/templates/` and merge user templates from the database.
    """

    def __init__(self) -> None:
        self._templates: dict[str, TemplateManifest] = {
            template.id: template for template in BUILTIN_TEMPLATES
        }

    def get(self, template_id: str) -> TemplateManifest | None:
        return self._templates.get(template_id)

    def list(
        self,
        platform: str | None = None,
        category: str | None = None,
    ) -> list[TemplateManifest]:
        result: list[TemplateManifest] = []
        for template in self._templates.values():
            if platform and platform not in template.platforms:
                continue
            if category and category not in template.category:
                continue
            result.append(template)
        return result

    def list_page_types(self) -> list[str]:
        """Return supported page types from the registry schema."""
        return list(PAGE_TYPE_FIELDS.keys())

    def page_type_fields(self, page_type: str) -> list[TemplateField]:
        """Return field metadata for a page type."""
        return PAGE_TYPE_FIELDS.get(page_type, [])

    def field_names_for_page(
        self,
        template_id: str,
        page_type: str,
    ) -> list[str]:
        """Return concrete field names supported by a template page type."""
        template = self.get(template_id)
        if template is None:
            return []
        if template.page_type_fields:
            return template.page_type_fields.get(page_type, [])
        return [field.key for field in self.page_type_fields(page_type)]

    def supports_page_type(self, template_id: str, page_type: str) -> bool:
        """Return whether a template declares support for a page type."""
        return bool(self.field_names_for_page(template_id, page_type))

    def default_template_id(self) -> str:
        """Return a deterministic default template id."""
        templates = self.list()
        return templates[0].id if templates else "esther_brand"

    def list_platform_profiles(self) -> list[PlatformProfile]:
        return list(PLATFORM_PROFILES.values())

    def get_platform_profile(self, platform: str) -> PlatformProfile | None:
        return PLATFORM_PROFILES.get(platform)

    def get_platform_format(
        self,
        platform: str,
        format_name: str | None,
    ) -> PlatformFormat | None:
        profile = self.get_platform_profile(platform)
        if profile is None:
            return None
        if format_name:
            return profile.formats.get(format_name)
        return next(iter(profile.formats.values()), None)

    def resolve_platform_format(
        self,
        platform: str,
        format_name: str | None,
    ) -> dict[str, Any]:
        """Resolve a platform format to a dict with safe fallback."""
        platform_format = self.get_platform_format(platform, format_name)
        if platform_format is None:
            platform_format = self.get_platform_format("xiaohongshu", "3:4")
        if platform_format is None:
            return {
                "platform": "xiaohongshu",
                "format": "3:4",
                "width": 1080,
                "height": 1440,
                "safe_area": {},
            }
        return {
            "platform": platform_format.platform,
            "format": platform_format.format,
            "width": platform_format.width,
            "height": platform_format.height,
            "safe_area": platform_format.safe_area,
        }


_registry: TemplateRegistry | None = None


def get_template_registry() -> TemplateRegistry:
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
    return _registry
