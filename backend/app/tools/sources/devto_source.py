"""Dev.to 内容数据源（REST API，免费，无需认证）。

Dev.to API 特点：
- 端点：https://dev.to/api/
- 完全免费，无需 API Key
- 返回结构化数据：title / description / tags / reactions / comments / cover_image
- 支持按标签搜索、按热度/时间排序

用途：
- 获取技术圈热门文章（编程/AI/开源/Web 开发）
- 按关键词搜索技术内容
- 适合小红书技术/职场/副业类目

局限：
- 内容偏技术，不适合美妆/穿搭话题
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.tools.sources.base import ContentSource, TrendingContent
from app.tools.sources.translator import translate_batch

logger = logging.getLogger(__name__)

_DEVTO_API_BASE = "https://dev.to/api"


class DevToSource(ContentSource):
    """Dev.to 内容源（零认证）。

    - search_trending: 按标签搜索文章（tag=keyword）
    - get_trending: 获取热门文章（top=7 / top=30）
    - 自动翻译 title + description 为中文
    """

    @property
    def name(self) -> str:
        return "devto"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            from app.tools.sources.base import get_proxy_url
            proxy = get_proxy_url()
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
                proxy=proxy or None,
            )
        return self._client

    async def _translate_results(
        self, results: list[TrendingContent]
    ) -> list[TrendingContent]:
        if not results:
            return results
        client = await self._ensure_client()
        titles = [r.title for r in results]
        summaries = [r.summary for r in results]
        zh_titles, zh_summaries = await asyncio.gather(
            translate_batch(titles, target_lang="zh-CN", client=client),
            translate_batch(summaries, target_lang="zh-CN", client=client),
        )
        for r, zh_t, zh_s in zip(results, zh_titles, zh_summaries):
            r.title = zh_t
            r.summary = zh_s
        logger.info(f"[devto] translated {len(results)} items (zh-CN)")
        return results

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        client = await self._ensure_client()

        params: dict[str, Any] = {
            "per_page": min(limit, 50),
            "top": self._time_range_to_days(time_range),
        }

        try:
            resp = await client.get(
                f"{_DEVTO_API_BASE}/articles",
                params=params,
                headers={"Accept": "application/vnd.forem.api+json"},
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            logger.error(f"[devto] search '{keyword}' failed: {e}")
            return []

        if not isinstance(items, list):
            return []

        results = []
        for item in items:
            title = item.get("title", "")
            desc = item.get("description", "") or ""
            if keyword.lower() not in title.lower() and keyword.lower() not in desc.lower():
                tag_list = item.get("tag_list", [])
                if not any(keyword.lower() in t.lower() for t in tag_list):
                    continue

            results.append(self._parse_article(item))

        results = results[:limit]
        results = await self._translate_results(results)
        logger.info(f"[devto] search '{keyword}': got {len(results)} results")
        return results

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        client = await self._ensure_client()

        params: dict[str, Any] = {
            "per_page": min(limit, 50),
            "top": 7,
        }

        try:
            resp = await client.get(
                f"{_DEVTO_API_BASE}/articles",
                params=params,
                headers={"Accept": "application/vnd.forem.api+json"},
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            logger.error(f"[devto] get_trending failed: {e}")
            return []

        if not isinstance(items, list):
            return []

        results = [self._parse_article(item) for item in items[:limit]]
        results = await self._translate_results(results)
        logger.info(f"[devto] get_trending: got {len(results)} results")
        return results

    def _parse_article(self, item: dict[str, Any]) -> TrendingContent:
        article_id = str(item.get("id", ""))
        title = item.get("title", "")
        desc = item.get("description", "") or ""
        cover = item.get("cover_image", "") or item.get("social_image", "")
        tags = item.get("tag_list", [])
        user = item.get("user", {})

        return TrendingContent(
            platform="devto",
            content_id=article_id,
            title=title,
            summary=desc[:200],
            content=desc,
            author=user.get("name", ""),
            url=item.get("url", f"https://dev.to/{user.get('username', '')}/{article_id}"),
            likes=int(item.get("positive_reactions_count", 0)),
            comments=int(item.get("comments_count", 0)),
            views=int(item.get("page_views_count", 0)),
            cover_img=cover,
            published_at=item.get("published_at", ""),
            tags=["devto"] + (tags if isinstance(tags, list) else []),
            title_original=title,
            summary_original=desc[:200],
            content_original=desc,
        )

    def _time_range_to_days(self, time_range: str) -> int:
        mapping = {"day": 1, "week": 7, "month": 30, "year": 365}
        return mapping.get(time_range, 7)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None