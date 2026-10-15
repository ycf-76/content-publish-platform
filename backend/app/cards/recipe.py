"""整套卡片的骨架序列（recipe）—— 用户拍板的那一层。

设计约束（来自产品决策，改这个文件前先读）：
1. **数量锁死 6 个，不再增加**（7±2）。将来要加模板，加在底层的 layout_id，不动这一层。
   用户永远不直接面对模板库，只面对这 6 个意图选项 —— 这是「模板多了不好处理」的结构性解法。
2. **recipe 是软约束**：它锁定「用哪几个版式族」和顺序，页数仍由内容量决定。
3. **recipe 的主要介入点是 `_plan` 的 prompt**（`composer.py`）：让 LLM 按骨架组织内容，
   而不是事后把内容硬套进版式 —— 硬套必然出现密度不够或溢出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# 预览图约定路径：由「骨架预览图生成脚本」离线渲染一次，落在前端静态目录。
PREVIEW_BASE = "/static/recipe-preview"


@dataclass(frozen=True)
class Recipe:
    id: str
    label: str                          # 中文名（澄清卡选项标题）
    hint: str                           # 一句话（澄清卡选项副标题）
    best_for: str                       # 适用场景
    preferred_kinds: tuple[str, ...]    # 主力 section kind（注入 _plan prompt）
    aux_kinds: tuple[str, ...]          # 可补充的 kind
    sequence: tuple[str, ...]           # 页版式序列（预览图渲染用）
    guidance: str                       # 注入 _plan prompt 的骨架指引
    preview_url: str = field(default="")

    def __post_init__(self) -> None:
        if not self.preview_url:
            # frozen dataclass 里用 object.__setattr__ 是标准做法
            object.__setattr__(self, "preview_url", f"{PREVIEW_BASE}/{self.id}.png")


RECIPES: dict[str, Recipe] = {
    "knowledge_list": Recipe(
        id="knowledge_list",
        label="干货清单型",
        hint="封面 + 要点账本 + 收尾",
        best_for="知识科普 / 干货清单 / 避坑经验",
        preferred_kinds=("list",),
        aux_kinds=("bento", "text"),
        sequence=("cover_display", "list_ledger", "list_ledger", "end_cta"),
        guidance=(
            "用户选了「干货清单型」：把内容拆成 2-3 屏清单，每屏 5-6 条要点，"
            "每条都要有 note 副行（写清为什么/怎么用/举个例子），不要只写两个字的词。"
            "清单信息密度最高，优先用 list，少用 text。"
        ),
    ),
    "tutorial_steps": Recipe(
        id="tutorial_steps",
        label="步骤教程型",
        hint="封面 + 步骤流程 + 收尾",
        best_for="教程 / 方法 / 操作流程",
        preferred_kinds=("steps",),
        aux_kinds=("list", "text"),
        sequence=("cover_display", "steps_flow", "steps_flow", "end_cta"),
        guidance=(
            "用户选了「步骤教程型」：拆成 4-5 步（steps），每步写清「做什么 + 为什么」，"
            "为什么写进 note。步骤要有时序感，不要拆成并列的清单。"
        ),
    ),
    "data_insight": Recipe(
        id="data_insight",
        label="数据解读型",
        hint="封面 + 核心数字 + 矩阵拆解 + 收尾",
        best_for="数据报告 / 调研结果 / 效果展示",
        preferred_kinds=("stat", "bento"),
        aux_kinds=("compare", "list"),
        sequence=("cover_display", "stat_card", "bento_grid", "end_cta"),
        guidance=(
            "用户选了「数据解读型」：先给一个核心数字（stat），必须写满 "
            "kicker + big + unit + note（这数字在说什么）+ source（数据来源）五层；"
            "再用 bento 矩阵 4-6 格拆解，每格写满 kicker+big+unit+note。"
            "孤立的大数字会被判不合格。"
        ),
    ),
    "opinion_quote": Recipe(
        id="opinion_quote",
        label="观点金句型",
        hint="封面 + 金句 + 要点展开 + 收尾",
        best_for="情感 / 观点 / 书评 / 生活感悟",
        preferred_kinds=("quote", "list"),
        aux_kinds=("text",),
        sequence=("cover_display", "quote_callout", "list_ledger", "end_cta"),
        guidance=(
            "用户选了「观点金句型」：一屏 quote 金句（60-80 字 + author 出处 + kicker 日期，"
            "三锚点缺一不可，否则空白会被读成「缺内容」），再用 1 屏 list 把观点展开成要点。"
        ),
    ),
    "compare_pick": Recipe(
        id="compare_pick",
        label="对比选购型",
        hint="封面 + 左右对比 + 结论清单 + 收尾",
        best_for="测评 / 选购 / 前后对比 / 方案取舍",
        preferred_kinds=("compare",),
        aux_kinds=("list", "bento"),
        sequence=("cover_display", "compare_split", "list_ledger", "end_cta"),
        guidance=(
            "用户选了「对比选购型」：主屏用 compare，至少 5 组对比行、两栏都要有内容、"
            "尽量给每行加维度标签（回答「这一行在比什么」）；再用 1 屏 list 给结论。"
        ),
    ),
    "timeline_story": Recipe(
        id="timeline_story",
        label="时间线叙事型",
        hint="封面 + 时间线 + 要点回顾 + 收尾",
        best_for="经历复盘 / 成长记录 / 项目回顾",
        preferred_kinds=("timeline",),
        aux_kinds=("list", "text"),
        sequence=("cover_display", "timeline_flow", "list_ledger", "end_cta"),
        guidance=(
            "用户选了「时间线叙事型」：主屏用 timeline，3-5 条时间锚点，"
            "每条必须有 date + text + note（背景说明）；按时间排序而非按重要性排序。"
        ),
    ),
}

RECIPE_IDS: tuple[str, ...] = tuple(RECIPES)
DEFAULT_RECIPE = "knowledge_list"

# 与 RECIPES 一一对应的字面量类型，供工具入参使用。
# 新增 recipe 时必须同步这里 —— 故意重复一次，让 type checker 在漏改时报错。
RecipeId = Literal[
    "knowledge_list", "tutorial_steps", "data_insight",
    "opinion_quote", "compare_pick", "timeline_story",
]


def get_recipe(recipe_id: str | None) -> Recipe:
    """取 recipe，未知 id 或 None 都退回默认（不让调用方崩）。"""
    return RECIPES.get(recipe_id or "", RECIPES[DEFAULT_RECIPE])


def recipe_guidance(recipe_id: str | None) -> str:
    """注入 `_plan` prompt 的骨架指引。"""
    return get_recipe(recipe_id).guidance


def recipe_kinds(recipe_id: str | None) -> tuple[str, ...]:
    """该骨架建议的 section kind（主力 + 补充）。"""
    r = get_recipe(recipe_id)
    return r.preferred_kinds + r.aux_kinds


def recipe_options() -> list[dict[str, str]]:
    """给 clarify_meta 用的选项清单（前端直接渲染 label/hint/preview_url）。"""
    return [
        {
            "label": r.label,
            "value": r.id,
            "description": f"{r.hint} · 适合{r.best_for}",
            "preview_url": r.preview_url,
        }
        for r in RECIPES.values()
    ]
