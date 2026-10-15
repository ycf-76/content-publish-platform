"""Search router â ç¬ç«çå¨ç½ææ¥å£ï¼ä¸èµ°å·¥ä½æµï¼ã

ç¨éï¼
- ç¨æ·å¨å·¥ä½å°æç´¢å¡çéæ©å¹³å°åï¼åé¢è§æç´¢ç»æï¼åå³å®æ¯å¦å¯å¨å·¥ä½æµ
- æ¯æå¨ç½æï¼platform=ç©ºï¼åæå®å¹³å°æï¼platform=hackernews/builtin/...ï¼

æéæ§å¶ï¼
- é®ç®±ç»å½ç¨æ·ï¼å¯æç´¢é¤å°çº¢ä¹¦å¤çææå¹³å°ï¼tavily/ç¥ä¹/å¾®å/HackerNews/Reddit/ç­é¨è¯é¢ï¼
- å°çº¢ä¹¦æ«ç ç»å½ç¨æ·ï¼é¢å¤è§£éå°çº¢ä¹¦æç´¢ï¼éå°çº¢ä¹¦ç»å½æ cookiesï¼

ä¸ workflow router çåºå«ï¼
- workflow router å¯å¨å®æ´å·¥ä½æµï¼8 ä¸ªèç¹ï¼ï¼æç´¢åªæ¯ç¬¬ä¸ä¸ªèç¹
- search router åªåæç´¢ï¼ç«å³è¿åç»æï¼ä¸å¯å¨å·¥ä½æµ
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.models import XhsAccount
from app.db.session import get_db

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchResultItem(BaseModel):
    """åæ¡æç´¢ç»æã"""
    platform: str
    content_id: str
    title: str
    summary: str
    author: str
    url: str
    likes: int
    comments: int
    shares: int
    views: int
    cover_img: str
    tags: list[str]


class SearchResponse(BaseModel):
    """æç´¢ååºã"""
    keyword: str
    platform: str  # å®éæç´¢çå¹³å°ï¼"hackernews,builtin" æåä¸ªå¹³å°åï¼
    count: int
    fallback_used: bool
    searched_platforms: list[str]
    summary: str
    results: list[dict]


@router.get("")
async def search(
    keyword: str = Query(..., description="æç´¢å³é®è¯"),
    platform: str = Query("", description="å¹³å°åï¼ç©º=å¨ç½æï¼ï¼tavily / builtin / hackernews / reddit / xiaohongshu"),
    limit: int = Query(20, ge=1, le=50, description="è¿åæ¡æ°ä¸é"),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[SearchResponse]:
    """å¨ç½ææ¥å£ï¼ä¸èµ°å·¥ä½æµï¼ç«å³è¿åç»æï¼ã

    æéæ§å¶ï¼
    - é®ç®±ç»å½ç¨æ·å¯æç´¢é¤å°çº¢ä¹¦å¤çææå¹³å°
    - å°çº¢ä¹¦æç´¢éè¦ç¨æ·å·²éè¿å°çº¢ä¹¦æ«ç ç»å½ï¼æææç XhsAccountï¼
    - å°è¯æç´¢å°çº¢ä¹¦ä½æ æéæ¶è¿å 403
    """
    if platform == "xiaohongshu":
        if not await _has_xhs_auth(user_id, db):
            raise HTTPException(
                status_code=403,
                detail="XHS_AUTH_REQUIRED:å°çº¢ä¹¦æç´¢éè¦åéè¿å°çº¢ä¹¦æ«ç ç»å½ææï¼è¯·å¨è´¦å·ä¸­å¿ç»å®å°çº¢ä¹¦è´¦å·",
            )

    import logging
    _logger = logging.getLogger(__name__)

    try:
        from app.tools.trending_search import TrendingSearchSkill

        skill = TrendingSearchSkill()
        output = await skill.execute({
            "keyword": keyword,
            "limit": limit,
            "min_interactions": 0,
            "time_range": "week",
            "platform": platform,
        })
    except RuntimeError as e:
        err_msg = str(e)
        _logger.error(f"[search] RuntimeError: {err_msg}")
        if "local client" in err_msg or "æ  local client" in err_msg:
            raise HTTPException(
                status_code=503,
                detail="å°çº¢ä¹¦æç´¢æå¡æä¸å¯ç¨ï¼æµè§å¨æ©å±æªè¿æ¥ï¼ï¼è¯·ä½¿ç¨å¶ä»å¹³å°æç´¢æç¨åéè¯",
            )
        raise HTTPException(status_code=500, detail=f"æç´¢å¤±è´¥: {err_msg}")
    except Exception as e:
        _logger.exception(f"[search] unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"æç´¢å¤±è´¥: {e}")

    return StandardResponse(data=SearchResponse(
        keyword=keyword,
        platform=output.get("platform", ""),
        count=output.get("count", 0),
        fallback_used=output.get("filter_stats", {}).get("fallback_used", False),
        searched_platforms=output.get("filter_stats", {}).get("searched_platforms", []),
        summary=output.get("summary", ""),
        results=output.get("results", []),
    ))


@router.get("/platforms")
async def list_platforms(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[list[dict]]:
    """ååºææå¯ç¨çæç´¢å¹³å°ï¼ä¾åç«¯æ¸²æå¹³å°éæ©å¨ï¼ã

    æéæ§å¶ï¼
    - é®ç®±ç»å½ç¨æ·ï¼å¯çå°é¤å°çº¢ä¹¦å¤çææå¹³å°
    - å°çº¢ä¹¦æ«ç ç»å½ç¨æ·ï¼é¢å¤çå°å°çº¢ä¹¦å¹³å°
    - å°çº¢ä¹¦å¹³å°å§ç»ååºä½æ è®° requires_auth=trueï¼åç«¯æ®æ­¤æ¾ç¤ºéå®ç¶æ
    """
    from app.tools.sources.manager import source_manager

    has_xhs = await _has_xhs_auth(user_id, db)

    platform_meta = {
        "tavily": {
            "label": "å¨ç½æç´¢",
            "desc": "Tavily å¨ç½æç´¢ï¼Google/Bing çº§è¦çé¢ï¼ä¸­è±æéåï¼",
        },
        "zhihu": {
            "label": "ç¥ä¹",
            "desc": "ç¥ä¹é®ç­/æç« ï¼åºäº Tavily ç«åæç´¢ï¼é¶é£æ§ï¼",
        },
        "weibo": {
            "label": "å¾®å",
            "desc": "å¾®åç­æ/åæï¼åºäº Tavily ç«åæç´¢ï¼é¶é£æ§ï¼",
        },
        "xiaohongshu_web": {
            "label": "å°çº¢ä¹¦",
            "desc": "å°çº¢ä¹¦ç­é¨ç¬è®°ï¼åºäº Tavily ç«åæç´¢ï¼é¶é£æ§ï¼",
        },
        "bilibili": {
            "label": "Bç«",
            "desc": "Bç«è§é¢/æç« ï¼åºäº Tavily ç«åæç´¢ï¼é¶é£æ§ï¼",
        },
        "douyin": {
            "label": "æé³",
            "desc": "æé³ç­é¨åå®¹ï¼åºäº Tavily ç«åæç´¢ï¼é¶é£æ§ï¼",
        },
        "pinterest": {
            "label": "Pinterest",
            "desc": "ç©¿æ­/ç¾å¦/å®¶å±çµæï¼åºäº Tavily ç«åæç´¢ï¼é¶é£æ§ï¼",
        },
        "instagram": {
            "label": "Instagram",
            "desc": "æµ·å¤çæ´»æ¹å¼çµæï¼åºäº Tavily ç«åæç´¢ï¼é¶é£æ§ï¼",
        },
        "builtin": {
            "label": "ç­é¨è¯é¢",
            "desc": "åç½®ä¸­æè¯é¢åºï¼ç©¿æ­/ç¾å¦/ç¾é£ç­ï¼é¶ç½ç»ä¾èµï¼",
        },
        "hackernews": {
            "label": "HackerNews",
            "desc": "ææ¯ç¤¾åºç­é¨ï¼è±æï¼ç§æ/åä¸è¯é¢ï¼",
        },
        "reddit": {
            "label": "Reddit",
            "desc": "æµ·å¤ç»¼åç¤¾åºï¼ééç½® API å­è¯ï¼",
        },
        "xiaohongshu": {
            "label": "å°çº¢ä¹¦",
            "desc": "å°çº¢ä¹¦çå®ç¬è®°ï¼éæ«ç ç»å½ï¼æé£æ§é£é©ï¼é»è®¤å³é­ï¼",
        },
    }

    registered = source_manager.list_platforms()
    default_platform = source_manager._default_platform

    platforms = []
    for name in registered:
        meta = platform_meta.get(name, {"label": name, "desc": ""})
        is_xhs = name == "xiaohongshu"
        p = {
            "name": name,
            "label": meta["label"],
            "desc": meta["desc"],
            "is_default": name == default_platform,
            "requires_auth": is_xhs,
            "auth_met": has_xhs if is_xhs else True,
        }
        if is_xhs and not has_xhs:
            p["locked"] = True
        platforms.append(p)

    return StandardResponse(data=platforms)


async def _has_xhs_auth(user_id: str, db: AsyncSession) -> bool:
    """æ£æ¥ç¨æ·æ¯å¦æå°çº¢ä¹¦ææï¼æ«ç ç»å½è¿ï¼æææç XhsAccountï¼ã"""
    acc_stmt = (
        select(XhsAccount)
        .where(XhsAccount.user_id == user_id)
        .order_by(XhsAccount.last_used_at.desc())
        .limit(1)
    )
    account = await db.scalar(acc_stmt)
    if account and account.xhs_user_id and not account.xhs_user_id.startswith("manual_"):
        return True
    return False   ã @×o©æn!º$¿uÌt¯ãðvz­rÇ  """Account API schemas."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request."""

    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")


class AccountResponse(BaseModel):
    """Account response."""

    account_id: str
    xhs_user_id: str
    xhs_nickname: str
    xhs_avatar_url: str = ""
    status: str
    login_method: str
 £ @ý>:®¨Ñ¤n¨Ú+,Ì¿1r7ð¼ÿÿó&"""ä¸æ¬¡æ§å¤çï¼
1. å é¤ XhsAccount æ¨¡å +  õStatus æä¸¾ + LoginMethod.QRCODE
2I ðauth.py ä¸­çæ«ç ç»å½ç«¯ç¹ (qr-lC $, 
 µ-manual)
3H WsearcJ 	¢ æéæ£æ¥
44 chemas/aÊ ø.py
5. æ¸çææG õ!å¼ç¨
"""
import os
os.chdir(os.path.dirname 0abs ÿ(__file__)))

# = ( @ ß1. models.py: ?ç