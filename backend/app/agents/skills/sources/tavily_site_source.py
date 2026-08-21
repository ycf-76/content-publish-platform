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

多域名支持：
- site_domain 支持空格分隔的多个域名，如 "163.com sohu.com sina.com.cn"
- 每个域名分别搜索，结果合并去重后返回
- 用于小红书/抖音等对搜索引擎屏蔽的平台，改搜替代内容源
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
        platform_name: 平台标识（"zhihu" / "weibo" / "xiaohongshu_web"）
        site_domain: 站内搜索域名，支持空格分隔多个域名
                     单域名: "zhihu.com"
                     多域名: "163.com sohu.com sina.com.cn"（分别搜索合并）
        tavily_source: 已初始化的 TavilySource 实例（共享其 _call_tavily 能力）
    """

    def __init__(
        self,
        platform_name: str,
        site_domain: str,
        tavily_source: Any,
    ) -> None:
        self._platform_name = platform_name
        self._site_domains = [d.strip() for d in site_domain.split() if d.strip()]
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
        """站内搜索：query 拼接 site:domain 限定来源。多域名分别搜索合并。"""
        all_results = await self._search_multi_domain(
            keyword, limit, topic="general", days=None,
        )
        logger.info(
            f"[{self._platform_name}] search '{keyword}': "
            f"got {len(all_results)} results"
        )
        return all_results[:limit]

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """获取平台热门（用 site 搜索 + 热门通用词兜底）。"""
        all_results = await self._search_multi_domain(
            category or "热门", limit, topic="news", days=7,
        )
        logger.info(
            f"[{self._platform_name}] get_trending: got {len(all_results)} results"
        )
        return all_results[:limit]

    async def _search_multi_domain(
        self,
        keyword: str,
        limit: int,
        topic: str = "general",
        days: int | None = None,
    ) -> list[TrendingContent]:
        """多域名搜索：每个域名分别搜索，结果合并去重。"""
        seen_urls: set[str] = set()
        all_results: list[TrendingContent] = []

        per_domain_limit = max(limit, 10)

        for domain in self._site_domains:
            query = f"{keyword} site:{domain}"
            data = await self._tavily._call_tavily(query, per_domain_limit, topic=topic, days=days)
            if not data:
                continue

            results_raw = data.get("results", [])
            images = data.get("images", [])

            for idx, item in enumerate(results_raw):
                content = self._normalize(item, images, idx)
                if content and content.url not in seen_urls:
                    seen_urls.add(content.url)
                    if content.likes == 0:
                        content.likes = 100
                    all_results.append(content)

        return all_results

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

            # 封面图：优先从 result 内部的 images 字段提取
            cover_img = ""
            result_images = item.get("images") or []
            if result_images:
                first_img = result_images[0]
                if isinstance(first_img, str):
                    cover_img = first_img
                elif isinstance(first_img, dict):
                    cover_img = first_img.get("url") or ""
            # 兜底：用顶层 images 列表按索引匹配
            if not cover_img and idx < len(images):
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
                raw={"score": score, "site": self._site_domains},
            )
        except Exception as e:
            logger.warning(f"[{self._platform_name}] normalize failed: {e}")
            return None

    async def close(self) -> None:
        logger.info(f"[{self._platform_name}] closed (shared tavily client)")