"""ReAct entry point for structured, editable social cards."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.clarification_schema import ClarifyFieldMeta, ClarifyOption, ClarifyWhen
from app.cards.composer import compose_deck
from app.cards.recipe import DEFAULT_RECIPE, RecipeId, recipe_options
from app.cards.schema import THEMES, ThemeId
from app.core.skill_base import Skill
from app.core.skill_registry import register

# 主题预览图约定路径（与 recipe 预览图由同一套脚本产出）
THEME_PREVIEW_BASE = "/static/recipe-preview/theme"


def _theme_options() -> list[ClarifyOption]:
    """9 套主题直接由 THEMES 编译 —— 加主题只改 schema.py，这里不用动。"""
    return [
        ClarifyOption(
            label=spec["label"],
            value=name,
            description=spec["hint"],
            preview_url=f"{THEME_PREVIEW_BASE}/{name}.png",
        )
        for name, spec in THEMES.items()
    ]


class CardComposeInput(BaseModel):
    topic: str = Field(min_length=1, max_length=80, description="卡片主题")
    content: str = Field(default="", max_length=6000, description="用户提供的正文/要点；有现成文案应完整传入")
    asset_ids: list[str] = Field(default_factory=list, max_length=3, description="用户已上传的素材 asset_id；不传则不使用图片")
    # 之前只写了 ["ink","warm"]，另外 7 套主题 LLM 根本选不到。统一走 schema.ThemeId。
    theme_id: ThemeId = Field(
        default="ink",
        description="视觉风格：杂志编辑/暖卡纸/瑞士极简/新中式墨韵/奶油温柔/极客终端/多巴胺Y2K/高奢黑金/手账贴纸",
    )
    image_layout: Literal["top", "side", "overlay"] = Field(default="top", description="图片布局：顶图封面、右图正文、全图覆字")
    recipe_id: RecipeId = Field(
        default=DEFAULT_RECIPE,
        description="整套骨架序列：干货清单/步骤教程/数据解读/观点金句/对比选购/时间线叙事",
    )


@register
class ComposeCardDeckSkill(Skill):
    node_type = "produce"
    name = "compose_card_deck"
    display_name = "结构化图文卡片"
    description = (
        "根据主题和文案制作小红书图文卡片，生成不同几何版式的结构化可编辑草稿；"
        "可使用当前用户已上传到素材库的 asset_id 放入图片位。"
        "做图文/知识卡片优先调用本工具；不支持文生图时必须告知用户，而非伪装生成。"
        "recipe_id（整套骨架）与 theme_id（视觉风格）是审美决策："
        "用户明确说了就按他说的传；没说就**留空不要猜**，系统会让用户自己选。"
    )
    skill_category = "create"
    skill_priority = "hot"
    trigger_words = ["做图文", "卡片", "知识卡", "加图片", "制作卡片"]
    input_schema = CardComposeInput

    # 澄清字段：让用户拍板「整套骨架」与「视觉风格」，而不是由 LLM 自由发挥。
    #
    # ⚠️ 字段名必须与 CardComposeInput 的入参名一致：
    #   loop.py 的 Stage 0 用 `_fname in arguments` 判断是否已明确 —— 名字对不上时，
    #   LLM 明明传了 recipe_id 仍会被拦下来问一遍，且澄清结果也灌不进工具入参。
    #
    # 时机用 missing 而不是 always，配合 `_fname in _already_clarified` 的判定：
    #   第一次真正弹卡让用户选，答过之后自动记住，不再打断熟练用户。
    #   真正的可控感由成品上的常驻「换骨架 / 换风格」保证，不靠事前拦截。
    #
    # auto_default 的差异是刻意的：
    #   骨架 / 风格 = 用户最该拍板的两项 → False，第一次必须选（否则只会拿到 LLM 的猜测）
    #   图片用法 = 技术性强、用户通常没概念 → True，走默认值 + 非阻塞建议卡
    clarify_meta: dict[str, ClarifyFieldMeta] = {
        "recipe_id": ClarifyFieldMeta(
            hint="这套卡片用哪种骨架？",
            when=ClarifyWhen.missing,
            default=DEFAULT_RECIPE,
            auto_default=False,
            options=[ClarifyOption(**opt) for opt in recipe_options()],
        ),
        "theme_id": ClarifyFieldMeta(
            hint="视觉风格选哪个？",
            when=ClarifyWhen.missing,
            default="ink",
            auto_default=False,
            options=_theme_options(),
        ),
        "image_layout": ClarifyFieldMeta(
            hint="图片怎么用？",
            when=ClarifyWhen.missing,
            default="top",
            auto_default=True,
            options=[
                ClarifyOption(label="顶图封面", value="top", description="图片放封面顶部，正文用排版页"),
                ClarifyOption(label="右图正文", value="side", description="正文页左侧清单、右侧配图"),
                ClarifyOption(label="全图覆字", value="overlay", description="整页大图 + 底部压字，氛围感强"),
            ],
        ),
    }

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        context = inputs.get("_context")
        user_id = getattr(context, "user_id", None)
        if not user_id:
            return {"error": "无法确认当前用户身份，不能读取图片素材"}
        try:
            args = CardComposeInput.model_validate({
                key: value for key, value in inputs.items() if key in CardComposeInput.model_fields
            })
            draft = await compose_deck(
                topic=args.topic, content=args.content, user_id=str(user_id),
                llm=inputs.get("llm"), asset_ids=args.asset_ids,
                theme_id=args.theme_id, image_layout=args.image_layout,
                recipe_id=args.recipe_id,
            )
        except ValueError as exc:
            return {"error": str(exc), "_source": "structured_cards"}
        return {
            "card_draft": draft,
            "report": f"已制作 {len(draft['pages'])} 张可编辑结构化卡片，已在作品区提供预览。",
            "_source": "structured_cards",
        }
