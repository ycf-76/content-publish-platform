"""Search router — 独立的全网搜接口（不走工作流）。

用途：
- 用户在工作台搜索卡片选择平台后，先预览搜索结果，再决定是否启动工作流
- 支持全网搜（platform=空）和指定平台搜（platform=hackernews/builtin/...）

权限控制：
- 邮箱登录用户：可搜索所有平台

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
) -> StandardResponse[SearchResponse]:
    """全网搜接口（不走工作流，立即返回结果）。

    权限控制：
    - 所有登录用户可搜索所有平台
    """
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
) -> StandardResponse[list[dict]]:
    """列出所有可用的搜索平台（供前端渲染平台选择器）。

    列出所有可用的搜索平台（供前端渲染平台选择器）。
    """
    from app.tools.sources.manager import source_manager

    has_xhs = False  # QR login removed

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
        "twitter": {
            "label": "Twitter/X",
            "desc": "全球热点风向标（基于 Tavily 站内搜索，零风控）",
        },
        "youtube": {
            "label": "YouTube",
            "desc": "全球视频趋势（YouTube Data API v3，需 API Key）",
        },
        "tiktok": {
            "label": "TikTok",
            "desc": "短视频趋势灵感（基于 Tavily 站内搜索，零风控）",
        },
        "medium": {
            "label": "Medium",
            "desc": "海外深度长文（基于 Tavily 站内搜索，零风控）",
        },
        "devto": {
            "label": "Dev.to",
            "desc": "技术圈热门文章（免费 API，零风控）",
        },
        "github": {
            "label": "GitHub",
            "desc": "开源项目/技术工具热点（免费 API，零风控）",
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
        "toutiao": {
            "label": "头条",
            "desc": "今日头条热搜（Tavily 站内搜索，零风控）",
        },
        "hb-weibo": {
            "label": "微博热搜",
            "desc": "微博实时热搜榜（公益 API，零风控）",
            "is_hotboard": True,
        },
        "hb-douyin": {
            "label": "抖音热搜",
            "desc": "抖音实时热搜榜（公益 API，零风控）",
            "is_hotboard": True,
        },
        "hb-zhihu": {
            "label": "知乎热榜",
            "desc": "知乎实时热榜（公益 API，零风控）",
            "is_hotboard": True,
        },
        "hb-toutiao": {
            "label": "头条热搜",
            "desc": "头条实时热搜榜（公益 API，零风控）",
            "is_hotboard": True,
        },
        "hb-baidu": {
            "label": "百度热搜",
            "desc": "百度实时热搜榜（公益 API，零风控）",
            "is_hotboard": True,
        },
        "hb-bilibili": {
            "label": "B站热搜",
            "desc": "B站实时热搜榜（公益 API，零风控）",
            "is_hotboard": True,
        },
        "hb-rednote": {
            "label": "小红书热搜",
            "desc": "小红书实时热搜榜（公益 API，零风控）",
            "is_hotboard": True,
        },
    }

    try:
        from app.tools.sources.hotboard_source import load_hotboard_config
        for _key, _cfg in load_hotboard_config().items():
            if _key not in platform_meta:
                platform_meta[_key] = {
                    "label": _cfg.get("label", _key),
                    "desc": f"{_cfg.get('label', _key)}实时热搜（公益 API，零风控）",
                    "is_hotboard": True,
                }
            else:
                platform_meta[_key]["is_hotboard"] = True
    except Exception:
        pass

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
            "is_hotboard": meta.get("is_hotboard", False),
        }
        if is_xhs and not has_xhs:
            p["locked"] = True
        platforms.append(p)

    return StandardResponse(data=platforms)