"""Search router — 独立的全网搜接口（不走工作流）。

用途：
- 用户在工作台搜索卡片选择平台后，先预览搜索结果，再决定是否启动工作流
- 支持全网搜（platform=空）和指定平台搜（platform=hackernews/builtin/...）

与 workflow router 的区别：
- workflow router 启动完整工作流（8 个节点），搜索只是第一个节点
- search router 只做搜索，立即返回结果，不启动工作流
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.schemas.common import StandardResponse

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
) -> StandardResponse[SearchResponse]:
    """全网搜接口（不走工作流，立即返回结果）。

    - platform 为空：并发搜索所有已注册平台，综合返回
    - platform 非空：只搜指定平台
    - 所有平台都 0 结果：对默认平台调 get_trending 热门榜兜底
    """
    from app.agents.skills.trending_search import TrendingSearchSkill

    skill = TrendingSearchSkill()
    output = await skill.execute({
        "keyword": keyword,
        "limit": limit,
        "min_interactions": 0,  # 预览搜索不过滤低互动，让用户看到全部结果
        "time_range": "week",
        "platform": platform,
    })

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
async def list_platforms() -> StandardResponse[list[dict]]:
    """列出所有可用的搜索平台（供前端渲染平台选择器）。

    返回平台名 + 显示名 + 描述，前端按此渲染平台选择按钮。
    """
    from app.agents.skills.sources.manager import source_manager

    # 平台元信息（显示名 + 描述）
    platform_meta = {
        "tavily": {
            "label": "全网搜索",
            "desc": "Tavily 全网搜索（Google/Bing 级覆盖面，中英文通吃）",
        },
        "zhihu": {
            "label": "知乎",
            "desc": "知乎问答/文章（基于 Tavily 站内搜索）",
        },
        "weibo": {
            "label": "微博",
            "desc": "微博热搜/博文（基于 Tavily 站内搜索）",
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
            "desc": "小红书真实笔记（需启用且登录）",
        },
    }

    registered = source_manager.list_platforms()
    default_platform = source_manager._default_platform

    platforms = []
    for name in registered:
        meta = platform_meta.get(name, {"label": name, "desc": ""})
        platforms.append({
            "name": name,
            "label": meta["label"],
            "desc": meta["desc"],
            "is_default": name == default_platform,
        })

    return StandardResponse(data=platforms)
