"""Asset ID 守卫：拦截 LLM 幻觉的假 asset_id，返回可用真 ID 供自纠。"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_HALLUCINATION_PATTERNS = re.compile(
    r"^(img_\d+|image_\d+|pic_\d+|photo_\d+|ref_\d+|图\d+|素材\d+)$",
    re.IGNORECASE,
)


async def guard_asset_ids(
    asset_ids: list[str],
    user_id: str,
    session_id: str | None = None,
) -> dict:
    """校验 asset_id 列表，拦截幻觉假 ID。

    Returns:
        {
            "ok": bool,
            "error": str | None,
            "hint": str | None,
            "available_asset_ids": list[str],
        }
    """
    from app.db.models import ImageAsset
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal

    available: list[str] = []
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ImageAsset.id)
            .where(ImageAsset.user_id == user_id)
            .order_by(ImageAsset.created_at.desc())
        )
        result = await session.execute(stmt)
        available = [row[0] for row in result.all()]

    if not asset_ids:
        return {
            "ok": False,
            "error": "asset_id 列表为空",
            "hint": "请提供至少一个有效的图片素材 ID",
            "available_asset_ids": available,
        }

    hallucinated: list[str] = []
    not_found: list[str] = []

    for aid in asset_ids:
        if _HALLUCINATION_PATTERNS.match(aid):
            hallucinated.append(aid)
        elif aid not in available:
            not_found.append(aid)

    if not hallucinated and not not_found:
        return {
            "ok": True,
            "error": None,
            "hint": None,
            "available_asset_ids": available,
        }

    parts: list[str] = []
    if hallucinated:
        parts.append(
            f"以下 asset_id 是 LLM 幻觉生成的假 ID：{hallucinated}，"
            f"不是素材库中的真实 ID"
        )
    if not_found:
        parts.append(
            f"以下 asset_id 在素材库中不存在：{not_found}"
        )

    error_msg = "；".join(parts)
    hint = (
        f"请使用 available_asset_ids 中的真实 ID 重新调用。"
        f"当前可用素材共 {len(available)} 个。"
    )

    logger.warning(
        f"[asset_ref] 守卫拦截：user={user_id}, "
        f"hallucinated={hallucinated}, not_found={not_found}, "
        f"available={len(available)}"
    )

    return {
        "ok": False,
        "error": error_msg,
        "hint": hint,
        "available_asset_ids": available,
    }