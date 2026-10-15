"""Versioned card contract. The LLM never supplies markup or asset URLs."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator

from app.cards.color import derive_tokens, accessible_accent


class Heading(BaseModel):
    id: str
    type: Literal["heading"] = "heading"
    text: str = Field(min_length=1, max_length=80)


class Text(BaseModel):
    id: str
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=600)


class Item(BaseModel):
    """清单/步骤的一个条目：主行 + 副行 + 右侧标签。

    之前条目只是 `str`，一行只能装一条短语——这是密度上不去的根因：
    同样填满 3:4 画幅，单行需要 6 行，带副行只要 4 行，而模型更愿意写
    4 条带说明的要点，而不是 6 条光秃短语。
    旧的 `str` 条目会自动归一化成 `{"text": ...}`，历史 Deck 无需迁移。
    """

    text: str = Field(default="", max_length=90)
    note: str = Field(default="", max_length=120)
    tag: str = Field(default="", max_length=16)

    @model_validator(mode="before")
    @classmethod
    def _from_bare_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"text": data}
        return data

    @model_validator(mode="after")
    def _require_content(self) -> Item:
        if not (self.text or self.note or self.tag):
            raise ValueError("条目不能为空")
        return self


class CompareRow(BaseModel):
    """对比表的一行：可选的维度标签 + 左右两列。

    `label` 回答"这一行到底在比什么"。旧的二元组 `[左, 右]` 会自动归一化，
    新的三元组 `[标签, 左, 右]` 也可以直接用。
    """

    label: str = Field(default="", max_length=30)
    left: str = Field(default="", max_length=85)
    right: str = Field(default="", max_length=85)

    @model_validator(mode="before")
    @classmethod
    def _from_sequence(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)):
            parts = [str(part) for part in data]
            if len(parts) >= 3:
                return {"label": parts[0], "left": parts[1], "right": parts[2]}
            if len(parts) == 2:
                return {"left": parts[0], "right": parts[1]}
            if len(parts) == 1:
                return {"left": parts[0]}
        return data

    @model_validator(mode="after")
    def _require_content(self) -> CompareRow:
        if not (self.left or self.right or self.label):
            raise ValueError("对比行不能为空")
        return self


class ListBlock(BaseModel):
    id: str
    type: Literal["list"] = "list"
    items: list[Item] = Field(min_length=1, max_length=8)
    # 视觉变体：空串 "" = 经典账本（默认，向后兼容）。见 VARIANT_OPTIONS。
    variant: str = Field(default="", max_length=20)


class Steps(BaseModel):
    id: str
    type: Literal["steps"] = "steps"
    items: list[Item] = Field(min_length=2, max_length=7)
    variant: str = Field(default="", max_length=20)


class Compare(BaseModel):
    id: str
    type: Literal["compare"] = "compare"
    left_title: str = Field(max_length=30)
    right_title: str = Field(max_length=30)
    rows: list[CompareRow] = Field(min_length=2, max_length=6)
    variant: str = Field(default="", max_length=20)


class ImageBlock(BaseModel):
    id: str
    type: Literal["image"] = "image"
    media_id: str = Field(min_length=1)
    source: Literal["upload", "ai"] = "upload"
    resolved_url: str = Field(pattern=r"^/uploads/assets/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+\.(jpg|png|webp|gif)$")
    alt: str = Field(default="配图", max_length=80)


class Cta(BaseModel):
    id: str
    type: Literal["cta"] = "cta"
    text: str = Field(min_length=1, max_length=60)


class Cell(BaseModel):
    """矩阵 bento 与单数据卡 stat 共同使用的「一格数据」。

    五层结构来自 Easel `card-recipes.md` 对数据卡的规定：
    kicker 顶分类 → big 主数字 → unit 单位 → note 解读 → source 来源。
    任何一层都不能省——只放一个「200%」看起来很廉价，必须有 kicker 告诉读者
    这数字是什么意思、note 告诉读者怎么解读、source 告诉读者凭什么信。
    """

    kicker: str = Field(default="", max_length=20)
    big: str = Field(default="", max_length=24)
    unit: str = Field(default="", max_length=16)
    note: str = Field(default="", max_length=80)
    source: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def _require_content(self) -> Cell:
        if not (self.big or self.kicker or self.note):
            raise ValueError("格子不能为空（至少给 big / kicker / note 其中之一）")
        return self


class BentoGrid(BaseModel):
    """Easel 9 骨架里我们之前缺失的「D 矩阵 Bento」。

    2-6 格 3 列自适应网格：每格独立承载一条数据点，kicker+big+unit+note+source
    五层在同一格里堆叠——多格组合时天然吃高度，是清单页欠填时的高容量骨架。
    """

    id: str
    type: Literal["bento_grid"] = "bento_grid"
    cells: list[Cell] = Field(min_length=2, max_length=6)
    variant: str = Field(default="", max_length=20)


class Stat(BaseModel):
    """Easel `card-recipes.md` 的「data 卡」骨架——单条数据强调展示。

    比 BentoGrid 更聚焦：所有视觉重量集中在一个格子上，数字字号比 bento
    更大、note 更长。同一个 Cell 模型，方便审计/编辑接口做统一处理。
    """

    id: str
    type: Literal["stat"] = "stat"
    cell: Cell
    variant: str = Field(default="", max_length=20)


class TimelineItem(BaseModel):
    """时间线的一个锚点：日期/时间戳 + 标题 + 副行（可选）。

    与 Steps 的差别是「按时间排序」而不是「按流程顺序」——同样作为列表型
    骨架承载，渲染上采用「左侧时间戳条 + 右侧标题/说明」两段式。
    """

    date: str = Field(default="", max_length=20)
    text: str = Field(default="", max_length=90)
    note: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _require_content(self) -> "TimelineItem":
        if not (self.text or self.date):
            raise ValueError("时间线条目至少要有日期或标题")
        return self


class Timeline(BaseModel):
    """Easel layout-laws.md 第 27 行提到的「时间线」骨架——并排展示同一线索的多个时间锚点。

    与 steps_flow 的差别：steps 强调「先 A 后 B 后 C」的流程，时间线强调
    「在 2024-Q1 / 2024-Q2 / 2024-Q3」这种时间序的并列。两版式由模型按语义选择，
    不允许强行互转（否则把流程改写成时间序就丢了因果）。
    """

    id: str
    type: Literal["timeline"] = "timeline"
    items: list[TimelineItem] = Field(min_length=3, max_length=8)
    variant: str = Field(default="", max_length=20)


class Quote(BaseModel):
    """Easel card-recipes.md 的「金句/陈述卡」——唯一允许较空的骨架。

    允许 ≤60% 内容覆盖率，但**必须补三锚点**（layout-laws.md 第 30 行）：
    顶部 kicker/日期 + 底部出处行 + 上下发丝线。任何一项缺失都会把"呼吸"读成"欠填"。
    """

    id: str
    type: Literal["quote"] = "quote"
    text: str = Field(min_length=1, max_length=120)
    author: str = Field(default="", max_length=40)
    kicker: str = Field(default="", max_length=30)

    @model_validator(mode="after")
    def _require_content(self) -> Quote:
        if not self.text.strip():
            raise ValueError("金句正文不能为空")
        return self


class Kicker(BaseModel):
    """顶部小标签（单页栏目名 / 分类）。

    `CARD_DSL_P1_SPEC` 规划 15 个 Block，首批只落地 11 个，kicker 与 footer
    是最基础却缺席的两个——Easel `layout-laws.md` 规定金句卡「必须补三锚点：
    顶 kicker/日期 + 底出处行 + 发丝线」，缺了它们，留白会被读成欠填而非呼吸。
    deck 级 kicker 是整套卡片的分类（渲染成贴顶标签 + 页码），
    本块是**单页自己**的小标题（如栏目名），渲染在内容区顶部。
    """

    id: str
    type: Literal["kicker"] = "kicker"
    text: str = Field(min_length=1, max_length=30)


class Footer(BaseModel):
    """底部信息栏（该页专属的来源 / 注释 / 免责）。

    与 deck 级 title 水印的区别：那个是每页绝对定位的固定页脚，
    本块是该页自己的补充说明，渲染在**内容区底部**，参与填满画幅。
    """

    id: str
    type: Literal["footer"] = "footer"
    text: str = Field(min_length=1, max_length=60)


class QaPair(BaseModel):
    q: str = Field(min_length=1, max_length=60)
    a: str = Field(min_length=1, max_length=120)


class Qa(BaseModel):
    """问答对：FAQ / 答疑类内容的主力骨架。

    一对问答天然吃两行高度（问题一行、回答一到两行），3 对就能铺满大半画幅，
    比纯正文段落更适合「读者最关心的几个问题」这类内容。
    """

    id: str
    type: Literal["qa"] = "qa"
    pairs: list[QaPair] = Field(min_length=2, max_length=5)


class Code(BaseModel):
    """代码面板：等宽字体 + 深色底。

    技术类卡片的核心组件。lang 只作标注（渲染成右上角小标签）不做语法高亮——
    避免引入额外依赖，且社媒卡片上高亮的收益远小于排版本身。
    """

    id: str
    type: Literal["code"] = "code"
    lang: str = Field(default="text", max_length=16)
    content: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def _require_content(self) -> "Code":
        if not self.content.strip():
            raise ValueError("代码内容不能为空")
        return self


class IconPair(BaseModel):
    # lucide 图标名（线性图标）。Easel anti-ai-slop 铁律：禁用 emoji 当图标。
    icon: str = Field(min_length=1, max_length=30)
    text: str = Field(min_length=1, max_length=20)


class IconGrid(BaseModel):
    """图标要点网格：图标 + 短文本成对并置（3-6 对）。

    适合「能力清单 / 特性速览 / 注意事项」这类并列短句，比账本行更轻、
    比矩阵更省字，是纯排版页里信息密度与呼吸感的折中解。
    """

    id: str
    type: Literal["icon_grid"] = "icon_grid"
    pairs: list[IconPair] = Field(min_length=3, max_length=6)


Block = Annotated[Union[Heading, Text, ListBlock, Steps, Compare, ImageBlock, Cta, BentoGrid, Stat,
                       Timeline, Quote, Kicker, Footer, Qa, Code, IconGrid],
                  Field(discriminator="type")]

LAYOUTS: dict[str, tuple[str, ...]] = {
    "cover_display": ("heading",),
    "cover_top_image": ("heading", "image"),
    "content_text": ("heading", "text"),
    "list_ledger": ("heading", "list"),
    "steps_flow": ("heading", "steps"),
    "compare_split": ("heading", "compare"),
    "image_right_ledger": ("heading", "list", "image"),
    "image_bg_overlay": ("heading", "image"),
    "end_cta": ("heading", "cta"),
    # P1 新版式：矩阵与单数据卡
    "bento_grid": ("heading", "bento_grid"),
    "stat_card": ("heading", "stat"),
    # P2 新版式：时间线与金句
    "timeline_flow": ("heading", "timeline"),
    "quote_callout": ("quote",),
}

# 每个组件可切换的视觉变体。空串 "" 表示经典版式（默认，向后兼容旧 Deck）。
# 与 LAYOUTS 正交：版式决定几何骨架，变体决定同一骨架下的视觉语气。
# renderer.py 只对非空变体追加 `variant-<v>` class，CSS 据此切换；经典渲染完全不动。
VARIANT_OPTIONS: dict[str, list[str]] = {
    "list": ["", "cards", "tags"],
    "steps": ["", "chips", "minimal"],
    "compare": ["", "table"],
    "bento_grid": ["", "masonry", "row"],
    "stat": ["", "ring", "underline"],
    "timeline": ["", "dots", "slim"],
}

# 风格不是「换个配色」，而是锁死一套视觉决定：字体族 + 字重策略 + 配色 + 版式性格。
# 参考 Easel card-design 的设计系统立场——「没人做设计决定」= 模型取统计平均值 = 廉价感。
# 每个风格都给出可复用的完整 spec，整套卡片全程只用这一套，不允许自由发挥。
# 风格不是「换个配色」，而是锁死一套视觉决定：字体族 + 字重策略 + 配色 + 版式性格。
# 参考 Easel card-design 的设计系统立场——「没人做设计决定」= 模型取统计平均值 = 廉价感。
# 每个风格都给出可复用的完整 spec，整套卡片全程只用这一套，不允许自由发挥。
#
# 第十一版改动（针对「配色太单一」）：
#   1) 重区分纸色——9 套旧纸色里有 5 套挤在 #f1ede4~#FBF7F0 的暖米区间（ΔE 极近），
#      改成 Easel 的差异化纸色：靛蓝瓷 / 牛皮 / 瑞士白 / 宣纸 / 奶油 / 终端黑 / 多巴胺黄 /
#      黑金 / 手账奶白 / 森林绿 / 沙丘棕 / 植物叶绿，相邻纸色肉眼可辨。
#   2) 点缀轴（accent axis）——每套主题可声明 `accents`（逗号分隔的 hex 列表），
#      把「一个写死的强调色」变成「可切换的强调色板」。`accent` 仍是默认（索引 0），
#      运行时用 `.{name}.accent-{i}` 仅覆盖 --accent，其余视觉决定不变。
#   3) 新增 forest / dune / botanical 三套主题（均为增量，旧 deck 的 9 个 id 保持不变）。
THEMES: dict[str, dict[str, str]] = {
    # 靛蓝瓷：冷调纸 + 衬线，像高级读书笔记（Easel Indigo Porcelain）
    "ink": {
        "label": "靛蓝瓷",
        "hint": "冷调纸衬线，适合知识/深度/书评",
        "font": "'Noto Serif CJK SC','Source Han Serif SC',serif",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "500",
        "radius": "4px",
        "bg": "#f2f4f5", "text": "#0a1f3d", "accent": "#315d93",
        "accents": "#315d93,#2e6b4f,#8f7650",
        "on_image_bg": "#0a1f3d", "on_image_text": "#f5f2ea",
    },
    # 牛皮纸：更暖更生活化（Easel Kraft Paper）
    "warm": {
        "label": "牛皮纸",
        "hint": "暖棕纸感，适合生活/情感/美食",
        "font": "'Noto Serif CJK SC','Source Han Serif SC',serif",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "500",
        "radius": "6px",
        "bg": "#eedfc7", "text": "#2a1e13", "accent": "#9b5a2e",
        "accents": "#9b5a2e,#2e6b4f",
        "on_image_bg": "#2a1e13", "on_image_text": "#eedfc7",
    },
    # 瑞士极简：白底黑字、零圆角零阴影（Easel Swiss，点缀轴=克莱因蓝/柠檬黄/柠檬绿/安全橙）
    "swiss": {
        "label": "瑞士极简",
        "hint": "白底点缀轴，适合科技/AI/产品/数据",
        "font": "'Noto Sans SC','Inter',sans-serif",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "200",
        "radius": "0px",
        "bg": "#fafaf8", "text": "#0a0a0a", "accent": "#002FA7",
        "accents": "#002FA7,#FFD500,#C5E803,#FF6B35",
        "on_image_bg": "#0a0a0a", "on_image_text": "#fafaf8",
    },
    # 新中式墨韵：宣纸墨色 + 朱砂点缀（Easel Chinese Ink）
    "inkwash": {
        "label": "新中式墨韵",
        "hint": "宣纸朱砂，适合国风/文化/诗词/节气",
        "font": "'Noto Serif CJK SC','Source Han Serif SC',serif",
        "kicker_font": "'Noto Serif CJK SC',serif",
        "display_weight": "600",
        "radius": "0px",
        "bg": "#f3efe4", "text": "#1a1a1a", "accent": "#a8322d",
        "accents": "#a8322d,#b08d57",
        "on_image_bg": "#1a1a1a", "on_image_text": "#f3efe4",
    },
    # 奶油温柔：莫兰迪柔色（Easel Morandi/Cream，点缀轴=莫兰迪四色）
    "cream": {
        "label": "奶油莫兰迪",
        "hint": "奶油莫兰迪，适合护肤/家居/治愈",
        "font": "'Noto Sans SC','Microsoft YaHei',sans-serif",
        "kicker_font": "'Noto Sans SC',sans-serif",
        "display_weight": "600",
        "radius": "24px",
        "bg": "#FAF6EF", "text": "#5A4F45", "accent": "#A3B0A0",
        "accents": "#A3B0A0,#8CA3AD,#C9A9A6,#9B8AA0",
        # cream 的正文色用偏深的暖灰（#5A4F45），压在图上才读得清，反色层仍自己给深底
        "on_image_bg": "#4a3f36", "on_image_text": "#FAF6EF",
    },
    # 极客终端：深底 + 等宽字（点缀轴=绿/琥珀）
    "terminal": {
        "label": "极客终端",
        "hint": "深底等宽绿字，适合编程/技术教程",
        "font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "700",
        "radius": "0px",
        "bg": "#0d1117", "text": "#c9d1d9", "accent": "#3fb950",
        "accents": "#3fb950,#e3b341",
        "on_image_bg": "#0d1117", "on_image_text": "#c9d1d9",
    },
    # 多巴胺 Y2K：高饱和撞色 + 粗黑字（Easel Dopamine，点缀轴=粉/克莱因蓝/安全橙）
    "dopamine": {
        "label": "多巴胺 Y2K",
        "hint": "高饱和撞色，适合潮流/穿搭/年轻向",
        "font": "'Noto Sans SC','Inter',sans-serif",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "900",
        "radius": "0px",
        "bg": "#FFD500", "text": "#0a0a0a", "accent": "#FF5CA8",
        "accents": "#FF5CA8,#002FA7,#FF6B35",
        "on_image_bg": "#0a0a0a", "on_image_text": "#ffffff",
    },
    # 高奢黑金：近黑底 + 细金线（点缀轴=金）
    "luxe_noir": {
        "label": "高奢黑金",
        "hint": "近黑底细金线，适合高端/影视/发布",
        "font": "'Noto Serif CJK SC','Source Han Serif SC',serif",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "200",
        "radius": "0px",
        "bg": "#0e0d0c", "text": "#ece2cf", "accent": "#d4a04a",
        "accents": "#d4a04a",
        "on_image_bg": "#0e0d0c", "on_image_text": "#ece2cf",
    },
    # 手账贴纸：奶白纸 + 胶带色块（Easel Journal，点缀轴=胶带四色）
    "journal": {
        "label": "手账贴纸",
        "hint": "奶白纸胶带风，适合学习/清单/日常复盘",
        "font": "'Noto Sans SC','Microsoft YaHei',sans-serif",
        "kicker_font": "'Noto Sans SC','Microsoft YaHei',sans-serif",
        "display_weight": "500",
        "radius": "16px",
        "bg": "#FBF7F0", "text": "#3a3632", "accent": "#B8D8C8",
        "accents": "#B8D8C8,#F3D9A4,#E8C4C4,#Bcd3E8",
        "on_image_bg": "#3a3632", "on_image_text": "#FBF7F0",
    },
    # 森林墨：Easel Forest Ink 衍生，深绿点缀（NEW）
    "forest": {
        "label": "森林墨",
        "hint": "森绿纸感，适合自然/户外/可持续/茶",
        "font": "'Noto Serif CJK SC','Source Han Serif SC',serif",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "500",
        "radius": "4px",
        "bg": "#f5f1e8", "text": "#16251b", "accent": "#2e6b4f",
        "accents": "#2e6b4f,#8f7650",
        "on_image_bg": "#16251b", "on_image_text": "#f5f1e8",
    },
    # 沙丘：Easel Dune 衍生，沙棕点缀（NEW）
    "dune": {
        "label": "沙丘",
        "hint": "沙棕纸感，适合旅行/荒漠/复古/手作",
        "font": "'Noto Sans SC','Microsoft YaHei',sans-serif",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "500",
        "radius": "8px",
        "bg": "#f0e6d2", "text": "#1f1a14", "accent": "#8f7650",
        "accents": "#8f7650,#9b5a2e",
        "on_image_bg": "#1f1a14", "on_image_text": "#f0e6d2",
    },
    # 植物学：Easel Botanical 衍生，叶绿点缀（NEW）
    "botanical": {
        "label": "植物学",
        "hint": "叶绿纸感，适合园艺/植物/食谱/科普",
        "font": "'Noto Sans SC','Microsoft YaHei',sans-serif",
        "kicker_font": "'JetBrains Mono','Noto Sans Mono CJK SC',monospace",
        "display_weight": "600",
        "radius": "12px",
        "bg": "#f6f4ee", "text": "#2f3b2c", "accent": "#7d9b76",
        "accents": "#7d9b76,#c08457,#a7bda0",
        "on_image_bg": "#2f3b2c", "on_image_text": "#f6f4ee",
    },
}

THEME_IDS: tuple[str, ...] = tuple(THEMES)

# 单一事实源：工具入参与 compose_deck 都用这个别名，避免多处 Literal 各自漂移
# （之前 card_compose.py 只写了 ["ink","warm"]，另外 4 套主题 LLM 根本选不到）。
ThemeId = Literal[
    "ink", "warm", "swiss", "inkwash", "cream", "terminal",
    "dopamine", "luxe_noir", "journal", "forest", "dune", "botanical",
]


# 图片蒙层的默认渐变遮罩。图片上的文字必须靠遮罩保证对比度，
# 不能直接用主题的 --text —— 浅色主题的深字压在照片上会读不清。
DEFAULT_IMAGE_SHADE = "linear-gradient(180deg,rgba(0,0,0,.08),rgba(0,0,0,.76))"


def _parse_accents(spec: dict[str, str]) -> list[str]:
    """Return the theme's switchable accent hexes (first = default).

    Falls back to the single ``accent`` key when ``accents`` is absent, so
    legacy/partial theme specs still compile.
    """
    raw = spec.get("accents")
    if raw:
        items = [a.strip() for a in raw.split(",") if a.strip()]
        if items:
            return items
    return [spec["accent"]]


def _accessible_accents(spec: dict[str, str]) -> list[str]:
    """Each accent run through :func:`accessible_accent` so every swatch clears the
    UI contrast floor (bg↔accent ≥ 3.0) — what the picker shows is what renders.
    """
    bg = spec["bg"]
    return [accessible_accent(bg, a) for a in _parse_accents(spec)]


def theme_accent_class(theme_id: str, accent_index: int) -> str:
    """CSS class to apply a non-default accent (``accent-{i}``), or "" for default / out-of-range."""
    if accent_index <= 0:
        return ""
    accents = _accessible_accents(THEMES[theme_id])
    if accent_index >= len(accents):
        return ""
    return f"accent-{accent_index}"


def _theme_block(name: str, spec: dict[str, str]) -> str:
    """Compile one theme's CSS variables.

    ``surface`` / ``line`` / ``muted`` / ``accent`` are **derived** from the
    theme's ``bg`` / ``text`` / (default) ``accent`` via :func:`derive_tokens`,
    which enforces WCAG contrast floors (panel vs page ≥ 1.6, secondary text ≥ 4.5,
    accent ≥ 3.0). Themes only declare a base + style; they can no longer
    accidentally hardcode a panel color indistinguishable from the page.
    ``on_image_*`` stays explicit — it is an overlay layer, not derivable.

    The **accent axis**: a theme may declare ``accents`` (comma-separated hex),
    turning one static accent into a switchable palette. The default accent
    (index 0) is compiled into the base ``.{name}`` block; each further accent
    emits a ``.{name}.accent-{i}`` override that swaps only ``--accent``.
    """
    accents = _accessible_accents(spec)
    toks = derive_tokens(spec["bg"], spec["text"], accents[0])
    base = (
        f".{name}{{--bg:{spec['bg']};"
        f"--surface:{toks['surface']};--text:{spec['text']};"
        f"--muted:{toks['muted']};--accent:{accents[0]};--line:{toks['line']};"
        f"--font:{spec['font']};--kicker-font:{spec['kicker_font']};"
        f"--display-weight:{spec['display_weight']};--radius:{spec['radius']};"
        f"--on-image-bg:{spec.get('on_image_bg', spec['text'])};"
        f"--on-image-text:{spec.get('on_image_text', '#ffffff')};"
        f"--on-image-shade:{spec.get('on_image_shade', DEFAULT_IMAGE_SHADE)};"
        f"background:var(--bg);color:var(--text)}}"
    )
    overrides = "".join(
        f".{name}.accent-{i}{{--accent:{acc}}}"
        for i, acc in enumerate(accents[1:], start=1)
    )
    return base + overrides


def theme_css() -> str:
    """把风格 spec 编译成 CSS 变量，避免手写一份总会漂移的样式表。

    `on_image_*` 是图片蒙层版式（`image_bg_overlay`）专用的反色层：
    它必须显式给在每套主题里，不能用 --text / --bg 推导 ——
    之前 renderer.py 把蒙层写死成 #23323c + 白字，导致切任何主题蒙层页都长一个样。
    """
    return "".join(_theme_block(name, spec) for name, spec in THEMES.items())


def block_slot(block_type: str) -> str:
    """把可互换的块类型归并到同一个版式槽位。

    list 与 steps 的渲染结果同构（有序条目列表），所以二者可以互相满足
    对方的必需槽位。这让同一组内容块能在「清单账本」和「步骤流程」之间切换，
    而不必重新生成内容。
    """
    return "items" if block_type in ("list", "steps") else block_type


# 通用可选块：纯标注型，任何版式叠加都不会改变版式性格或几何骨架。
UNIVERSAL_OPTIONAL: tuple[str, ...] = ("kicker", "footer")

# 版式专属可选块：会改变几何的内容块，按版式性格显式列出。
# 刻意**不用**「未列出 = 全开放」的兜底——那会让 content_text 接受 list 之类的结构块，
# 进而把 available_directions 的 editorial 判据搞坏（纯文字页本应判为不可用/会欠填）。
# 之前这里是「未列出 = 空集」，等于把组合能力写死：新增组件必须回来改代码。
LAYOUT_OPTIONAL: dict[str, tuple[str, ...]] = {
    # 封面：可挂本期导读（list）+ 正文 + 问答/图标做预告
    "cover_display": ("text", "list", "qa", "icon_grid"),
    # 图片主导版式：再塞结构块会和图片抢空间，只留正文补白（+ 通用标注块）
    "cover_top_image": ("text",),
    "image_bg_overlay": ("text",),
    "content_text": ("qa", "code", "icon_grid"),
    "list_ledger": ("icon_grid", "qa", "code"),
    "steps_flow": ("icon_grid", "qa", "code"),
    "compare_split": ("icon_grid", "qa", "code"),
    "bento_grid": ("qa", "code", "icon_grid"),
    "stat_card": ("qa", "code", "icon_grid"),
    "timeline_flow": ("qa", "code", "icon_grid"),
    "quote_callout": ("qa", "code", "icon_grid"),
    "image_right_ledger": ("qa", "code", "icon_grid"),
    # 收尾：可挂要点回顾（list）+ 正文
    "end_cta": ("text", "list", "qa", "icon_grid"),
}


def optional_blocks(layout_id: str) -> set[str]:
    """某版式允许挂载的可选 Block = 通用标注块 ∪ 该版式的专属可选块。

    新增「通用」组件（如又加一个横线/水印块）只需进 `UNIVERSAL_OPTIONAL`；
    新增「改变几何」的组件按需加进各版式的 `LAYOUT_OPTIONAL`，两者都不必再动校验逻辑。
    """
    pool = set(UNIVERSAL_OPTIONAL) | set(LAYOUT_OPTIONAL.get(layout_id, ()))
    # 校验是按槽位比的（list/steps 都归到 "items"），池子里必须两种写法都有，
    # 否则列表类 Block 会被误判为「不允许」。
    return pool | {block_slot(name) for name in pool}


class CardPage(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_]{4,32}$")
    role: Literal["cover", "body", "ending"]
    layout_id: str
    blocks: list[Block] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_layout(self) -> "CardPage":
        required = LAYOUTS.get(self.layout_id)
        if required is None:
            raise ValueError(f"未知版式: {self.layout_id}")
        kinds = [block_slot(block.type) for block in self.blocks]
        needed = [block_slot(kind) for kind in required]
        if any(kinds.count(kind) != 1 for kind in needed):
            raise ValueError(f"版式 {self.layout_id} 缺少或重复必需组件: {required}")
        optional = optional_blocks(self.layout_id)
        if any(kind not in needed and kind not in optional for kind in kinds):
            raise ValueError(f"版式 {self.layout_id} 含有不允许的组件")
        if kinds.count("text") > 1:
            raise ValueError("单页最多只能包含一个正文组件")
        if len({block.id for block in self.blocks}) != len(self.blocks):
            raise ValueError("同一页的组件 ID 不能重复")
        return self


class CardDeck(BaseModel):
    schema_version: Literal[1] = 1
    deck_id: str
    title: str = Field(min_length=1, max_length=80)
    # kicker 是每页顶部的小标签（分类/来源/日期），取代写死的装饰文字。
    # 留空时渲染器只输出页码，不再用一句与内容无关的英文占位。
    kicker: str = Field(default="", max_length=40)
    # 走 ThemeId 别名，别在这里手写第二份列表 —— 之前手写导致新增的 3 套主题
    # 能编译进 CSS 却在建 Deck 时被 Literal 拒掉（"Input should be ..."）。
    theme_id: ThemeId = "ink"
    # 强调色轴索引：0 = 主题默认强调色；1..n 对应 THEMES[theme].accents 的第 n 个。
    # 默认 0 保证旧 Deck 反序列化后外观不变（向后兼容）。
    accent_index: int = 0
    width: Literal[1080] = 1080
    height: Literal[1440] = 1440
    pages: list[CardPage] = Field(min_length=1, max_length=9)

    @model_validator(mode="after")
    def validate_sequence(self) -> "CardDeck":
        if self.pages[0].role != "cover":
            raise ValueError("第一张卡片必须是封面")
        if len({page.id for page in self.pages}) != len(self.pages):
            raise ValueError("页面 ID 不能重复")
        return self


# 每个方向只列出能表达自己特征的版式，不放通用兜底：
# 否则"图像主导"在没有任何图片时会退化成清单版式，名不副实。
# 撑不起来的方向由 available_directions 直接过滤掉，不给用户点了没反应的选项。
DIRECTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "editorial": {
        "cover": ("content_text", "cover_display"),
        "body": ("content_text",),
        "ending": ("content_text",),
    },
    "ledger": {
        "cover": ("cover_display",),
        "body": ("list_ledger",),
        "ending": ("end_cta",),
    },
    "flow": {
        "cover": ("cover_display",),
        "body": ("steps_flow",),
        "ending": ("end_cta",),
    },
    # 以「整版铺图」为特征。cover_top_image 与 image_bg_overlay 用的是同一批组件，
    # 把它放在首位等于永远切不动，所以这里直接用蒙层作为该方向的目标版式。
    "visual": {
        "cover": ("image_bg_overlay",),
        "body": ("image_bg_overlay", "image_right_ledger"),
        "ending": ("image_bg_overlay",),
    },
}


def apply_direction(deck: "CardDeck", direction_id: str) -> list[str]:
    """把整副卡片切到某个几何方向，返回被改动的页面 ID。

    方向只是"每页版式的偏好顺序"，实际落点仍要过 compatible_layouts，
    所以不会切出当前组件撑不起来的版式。
    """
    preferences = DIRECTIONS.get(direction_id)
    if preferences is None:
        raise ValueError(f"未知方向: {direction_id}")
    changed: list[str] = []
    for page in deck.pages:
        allowed = set(compatible_layouts(page))
        for layout_id in preferences.get(page.role, ()):
            if layout_id in allowed and layout_id != page.layout_id:
                page.layout_id = layout_id
                changed.append(page.id)
                break
    return changed


def available_directions(deck: "CardDeck") -> list[str]:
    """只返回真正会改变版式的方向，避免给用户一堆点了没反应的选项。"""
    result: list[str] = []
    for direction_id in DIRECTIONS:
        probe = deck.model_copy(deep=True)
        if apply_direction(probe, direction_id):
            result.append(direction_id)
    return result


def compatible_layouts(page: CardPage) -> list[str]:
    """当前页的组件集合可以合法切换到的版式。

    前端只展示这些候选，所以切换不会因缺少必需组件而失败。
    """
    kinds = {block_slot(block.type) for block in page.blocks}
    result: list[str] = []
    for layout_id, required in LAYOUTS.items():
        needed = {block_slot(kind) for kind in required}
        if not needed <= kinds:
            continue
        extra = kinds - needed
        if extra <= optional_blocks(layout_id):
            result.append(layout_id)
    return result
