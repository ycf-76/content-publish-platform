"""卡片渲染 HTTP 服务：把 app.cards DSL 暴露给前端图文编辑壳。

设计原则：
- 模型永远不写 markup（见 app/cards/schema.py 顶部注释）。本路由只是把
  已有的 renderer / composer / audit 包成 HTTP，让前端（独立进程）能消费。
- preview 端点两条路径：①前端回传完整 deck（编辑后）→ 直接 to_card_draft；
  ②topic+content 退化生成（compose_deck(llm=None)，不发起任何真机 LLM 请求）。
"""

from __future__ import annotations

import logging
import typing
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.cards.renderer import to_card_draft
from app.cards.schema import CardDeck, ThemeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cards", tags=["cards"])


class PreviewRequest(BaseModel):
    """预览请求：deck 与 (topic+content) 二选一。"""

    deck: Optional[CardDeck] = None
    topic: Optional[str] = Field(default=None, max_length=80)
    content: Optional[str] = Field(default=None, max_length=6000)
    theme_id: ThemeId = "ink"
    image_layout: Literal["top", "side", "overlay"] = "top"


def _block_type_names() -> list[str]:
    """从 Block 联合类型里抽取所有 type 字面量，给前端做「组件清单」。"""
    try:
        union = typing.get_args(CardDeck.__fields__["pages"].annotation)  # noqa: 兜底
    except Exception:
        union = None
    # 直接从 Block 判别联合里取类型名，避免对 CardDeck 内部结构的假设
    try:
        from app.cards.schema import Block

        args = typing.get_args(Block)
        # Block 是 Annotated[Union[...], Field(...)]，get_args 返回 (Union, FieldInfo)
        union_type = next((a for a in args if getattr(a, "__origin__", None) is typing.Union), None)
        if union_type is not None:
            return sorted(
                {t.model_fields["type"].default for t in typing.get_args(union_type)}
            )
    except Exception as exc:  # pragma: no cover - 反射仅用于元数据
        logger.warning("提取 block 类型名失败: %s", exc)
    return []


@router.post("/preview")
async def preview(
    req: PreviewRequest, user_id: str = Depends(get_current_user)
) -> StandardResponse[dict]:
    if req.deck is not None:
        draft = to_card_draft(req.deck)
        return StandardResponse(data=draft)

    if req.topic and req.content:
        from app.cards.composer import compose_deck

        try:
            # llm=None：走退化路径（按行拆分），不发起任何真机 LLM 请求。
            draft = await compose_deck(
                topic=req.topic,
                content=req.content,
                user_id=user_id,
                llm=None,
                theme_id=req.theme_id,
                image_layout=req.image_layout,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return StandardResponse(data=draft)

    raise HTTPException(status_code=400, detail="preview 需要 deck 或 (topic+content)")


@router.post("/audit")
async def audit_endpoint(
    req: PreviewRequest, user_id: str = Depends(get_current_user)
) -> StandardResponse[dict]:
    if req.deck is None:
        raise HTTPException(status_code=400, detail="audit 需要 deck")
    from app.cards import audit as card_audit

    reports = card_audit.audit_deck(req.deck)
    return StandardResponse(
        data={
            "reports": reports,
            "min_fill": card_audit.deck_density(req.deck)["min_fill"],
        }
    )


@router.get("/meta")
async def meta() -> StandardResponse[dict]:
    """返回可用版式 / 主题 / 可选 Block，供前端放开组合（根治固定死）。"""
    from app.cards.schema import LAYOUTS, THEMES, optional_blocks

    return StandardResponse(
        data={
            "layouts": {lid: list(required) for lid, required in LAYOUTS.items()},
            "themes": {
                name: {"label": spec.get("label", name), "hint": spec.get("hint", "")}
                for name, spec in THEMES.items()
            },
            "block_types": _block_type_names(),
            "optional_blocks": {
                lid: sorted(optional_blocks(lid)) for lid in LAYOUTS
            },
        }
    )
