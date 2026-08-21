"""Search router — 独立的全网搜接口（不走工作流）。

用途：
- 用户在工作台搜索卡片选择平台后，先预览搜索结果，再决定是否启动工作流
- 支持全网搜（platform=空）和指定平台搜（platform=hackernews/builtin/...）

权限控制：
- 邮箱登录用户：可搜索除小红书外的所有平台（tavily/知乎/微博/HackerNews/Reddit/热门话题）
- 小红书扫码登录用户：额外解锁小红书搜索（需小红书登录态 cookies）

与 workflow router 的区别：
- workflow router 启动完整工作流（8 个节点），搜索只是第一个节点
- search router 只做搜索，立即返回结果，不启动工作流
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
    """单条搜索结果。"""
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
    """搜索响应。"""
    keyword: str
    platform: str  # 实际搜索的平台（"hackernews,builtin" 或单个平台名）
    count: int
    fallback_used: bool
    searched_platforms: list[str]
    summary: str
    results: list[dict]


@router.get("")
async def search(
    keyword: str = Query(..., description="搜索关键词"),
    platform: str = Query("", description="平台名（空=全网搜）：tavily / builtin / hackernews / reddit / xiaohongshu"),
    limit: int = Query(20, ge=1, le=50, description="返回条数上限"),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[SearchResponse]:
    """全网搜接口（不走工作流，立即返回结果）。

    权限控制：
    - 邮箱登录用户可搜索除小红书外的所有平台
    - 小红书搜索需要用户已通过小红书扫码登录（有有效的 XhsAccount）
    - 尝试搜索小红书但无权限时返回 403
    """
    if platform == "xiaohongshu":
        if not await _has_xhs_auth(user_id, db):
            raise HTTPException(
                status_code=403,
                detail="XHS_AUTH_REQUIRED:小红书搜索需要先通过小红书扫码登录授权，请在账号中心绑定小红书账号",
            )

    import logging
    _logger = logging.getLogger(__name__)

    try:
        from app.agents.skills.trending_search import TrendingSearchSkill

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
        if "local client" in err_msg or "无 local client" in err_msg:
            raise HTTPException(
                status_code=503,
                detail="小红书搜索服务暂不可用（浏览器扩展未连接），请使用其他平台搜索或稍后重试",
            )
        raise HTTPException(status_code=500, detail=f"搜索失败: {err_msg}")
    except Exception as e:
        _logger.exception(f"[search] unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")

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
    """列出所有可用的搜索平台（供前端渲染平台选择器）。

    权限控制：
    - 邮箱登录用户：可看到除小红书外的所有平台
    - 小红书扫码登录用户：额外看到小红书平台
    - 小红书平台始终列出但标记 requires_auth=true，前端据此显示锁定状态
    """
    from app.agents.skills.sources.manager import source_manager

    has_xhs = await _has_xhs_auth(user_id, db)

    platform_meta = {
        "tavily": {
            "label": "全网搜索",
            "desc": "Tavily 全网搜索（Google/Bing 级覆盖面，中英文通吃）",
        },
        "zhihu": {
            "label": "知乎",
            "desc": "知乎问答/文章（基于 Tavily 站内搜索，零风控）",
        },
        "weibo": {
            "label": "微博",
            "desc": "微博热搜/博文（基于 Tavily 站内搜索，零风控）",
        },
        "xiaohongshu_web": {
            "label": "小红书",
            "desc": "小红书热门笔记（基于 Tavily 站内搜索，零风控）",
        },
        "bilibili": {
            "label": "B站",
            "desc": "B站视频/文章（基于 Tavily 站内搜索，零风控）",
        },
        "douyin": {
            "label": "抖音",
            "desc": "抖音热门内容（基于 Tavily 站内搜索，零风控）",
        },
        "pinterest": {
            "label": "Pinterest",
            "desc": "穿搭/美妆/家居灵感（基于 Tavily 站内搜索，零风控）",
        },
        "instagram": {
            "label": "Instagram",
            "desc": "海外生活方式灵感（基于 Tavily 站内搜索，零风控）",
        },
        "builtin": {
            "label": "热门话题",
            "desc": "内置中文话题库（穿搭/美妆/美食等，零网络依赖）",
        },
        "hackernews": {
            "label": "HackerNews",
            "desc": "技术社区热门（英文，科技/创业话题）",
        },
        "reddit": {
            "label": "Reddit",
            "desc": "海外综合社区（需配置 API 凭证）",
        },
        "xiaohongshu": {
            "label": "小红书",
            "desc": "小红书真实笔记（需扫码登录，有风控风险，默认关闭）",
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
    """检查用户是否有小红书授权（扫码登录过，有有效的 XhsAccount）。"""
    acc_stmt = (
        select(XhsAccount)
        .where(XhsAccount.user_id == user_id)
        .order_by(XhsAccount.last_used_at.desc())
        .limit(1)
    )
    account = await db.scalar(acc_stmt)
    if account and account.xhs_user_id and not account.xhs_user_id.startswith("manual_"):
        return True
    return False