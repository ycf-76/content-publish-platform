"""基于 Tavily 的站内搜索内容源（知乎 / 微博等）。

设计动机：
- 知乎、微博没有稳定的官方公开 API，直接爬虫易触发风控（小红书前车之鉴）
- 复用 Tavily 搜索引擎做 `site:zhihu.com` / `site:weibo.com` 站内搜索
- 不需要额外 API Key（与 TavilySource 共享同一 key）
- 不接触 Playwright，不违反项目约束

数据特点：
- 返回的是搜索引擎抓取的网页快照（title + content 摘要 + url）
- 无互动数据（likes/comments 等），likes 用 tavily score 估算
- 中文内容无需翻译（跳过 translate_batch）
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.skills.sources.base import ContentSource, TrendingContent

logger = logging.getLogger(__name__)


class TavilySiteSource(ContentSource):
    """基于 Tavily 的站内搜索源。

    通过 `site:<domain>` 限定 Tavily 搜索范围，实现知乎/微博等平台内容获取。
    一个实例对应一个平台（构造时传入 platform_name + site_domain）。

    Args:
        platform_name: 平台标识（"zhihu" / "weibo"）
        site_domain: 站内搜索域名（"zhihu.com" / "weibo.com"）
        tavily_source: 已初始化的 TavilySource 实例（共享其 _call_tavily 能力）
    """

    def __init__(
        self,
        platform_name: str,
        site_domain: str,
        tavily_source: Any,
    ) -> None:
        self._platform_name = platform_name
        self._site_domain = site_domain
        self._tavily = tavily_source

    @property
    def name(self) -> str:
        return self._platform_name

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """站内搜索：query 拼接 site:domain 限定来源。"""
        query = f"{keyword} site:{self._site_domain}"
        data = await self._tavily._call_tavily(query, limit, topic="general")
        if not data:
            return []

        results_raw = data.get("results", [])
        images = data.get("images", [])

        results: list[TrendingContent] = []
        for idx, item in enumerate(results_raw):
            content = self._normalize(item, images, idx)
            if content:
                results.append(content)

        logger.info(
            f"[{self._platform_name}] search '{keyword}': "
            f"got {len(results_raw)} results, {len(results)} normalized"
        )
        # 中文平台内容无需翻译
        return results[:limit]

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """获取平台热门（用 site 搜索 + 热门通用词兜底）。"""
        query = (category or "热门") + f" site:{self._site_domain}"
        data = await self._tavily._call_tavily(query, limit, topic="news", days=7)
        if not data:
            return []

        results_raw = data.get("results", [])
        images = data.get("images", [])

        results: list[TrendingContent] = []
        for idx, item in enumerate(results_raw):
            content = self._normalize(item, images, idx)
            if content:
                if content.likes == 0:
                    content.likes = 100
                results.append(content)

        logger.info(
            f"[{self._platform_name}] get_trending: got {len(results)} results"
        )
        return results[:limit]

    def _normalize(
        self,
        item: dict[str, Any],
        images: list,
        idx: int,
    ) -> TrendingContent | None:
        """归一化单条结果（与 TavilySource 类似，但 platform 标记为本平台）。"""
        try:
            url = item.get("url") or ""
            title = (item.get("title") or "").strip()
            content = (item.get("content") or "").strip()

            if not url or not title:
                return None

            score = float(item.get("score") or 0)
            likes = int(score * 1000)

            cover_img = ""
            if idx < len(images):
                img_item = images[idx]
                if isinstance(img_item, str):
                    cover_img = img_item
                elif isinstance(img_item, dict):
                    cover_img = img_item.get("url") or ""

            summary = content[:200] if content else title[:200]

            return TrendingContent(
                platform=self._platform_name,
                content_id=f"{self._platform_name}_{idx}_{hash(url) & 0xFFFFFFFF}",
                title=title,
                summary=summary,
                content=content,
                author="",
                url=url,
                likes=likes,
                comments=0,
                shares=0,
                views=0,
                cover_img=cover_img,
                published_at="",
                tags=[],
                raw={"score": score, "site": self._site_domain},
            )
        except Exception as e:
            logger.warning(f"[{self._platform_name}] normalize failed: {e}")
            return None

    async def close(self) -> None:
        # 共享 TavilySource 的 client，由 TavilySource 自己关闭
        logger.info(f"[{self._platform_name}] closed (shared tavily client)")
