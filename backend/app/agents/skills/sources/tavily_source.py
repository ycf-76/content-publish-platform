"""Tavily 全网搜索内容源。

Tavily 是专为 AI Agent 设计的搜索 API，特点：
- 端点：POST https://api.tavily.com/search
- 返回结构化结果（title / url / content / score）+ 图片（images）
- 支持 search_depth: "basic"（快速）/ "advanced"（深度，更贵）
- 支持 topic: "general"（通用）/ "news"（新闻）
- 需要 API Key，申请地址：https://app.tavily.com/

与 HackerNews/Reddit 的区别：
- Tavily 是全网搜索（Google/Bing 级覆盖面），不限定单一社区
- 直接返回 content 摘要和 cover_img，无需自己抓 og:image
- 支持中英文关键词，无需翻译重试
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.agents.skills.sources.base import ContentSource, TrendingContent
from app.agents.skills.sources.translator import translate_batch

logger = logging.getLogger(__name__)

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilySource(ContentSource):
    """Tavily 全网搜索内容源。

    - search_trending: 调 /search，topic=general，按 score 排序
    - get_trending: 调 /search，topic=news + 空关键词兜底（Tavily 无"热门"概念）
    - 自动翻译 title/content 为中文（原文保留在 *_original 字段）
    - include_images=True 直接拿到封面图 URL，无需抓 og:image
    """

    @property
    def name(self) -> str:
        return "tavily"

    def __init__(
        self,
        api_key: str,
        search_depth: str = "basic",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        # search_depth: "basic"（默认，便宜） / "advanced"（深度，更贵）
        # MVP 用 basic 控制成本，后续可按需切到 advanced
        self.search_depth = search_depth
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "User-Agent": "multi-agent-xhs-platform/1.0",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _translate_results(
        self, results: list[TrendingContent]
    ) -> list[TrendingContent]:
        """批量翻译 title + summary 为中文（原文保留在 *_original）。

        翻译失败时降级为原文，不阻塞流程。
        """
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
        logger.info(f"[tavily] translated {len(results)} items (zh-CN)")
        return results

    def _normalize_result(
        self,
        item: dict[str, Any],
        images: list[dict[str, str]],
        idx: int,
    ) -> TrendingContent | None:
        """归一化 Tavily 单条搜索结果。

        Tavily result 结构：
        - title: 标题
        - url: URL
        - content: 正文摘要（已由 Tavily 提取，约 200-500 字）
        - score: 相关度分数（0-1，越高越相关）
        - raw_content: 原始 HTML（search_depth=advanced 时才有）
        """
        try:
            url = item.get("url") or ""
            title = (item.get("title") or "").strip()
            content = (item.get("content") or "").strip()

            if not url or not title:
                return None

            # score 作为相关度/热度指标，转成 likes（供前端排序展示）
            score = float(item.get("score") or 0)
            # 把 score (0-1) 放大到 likes 量级（供 interactions 排序）
            likes = int(score * 1000)

            # 封面图：优先用 images 列表（Tavily 已提取）
            # Tavily images 格式可能是字符串列表 ["url1", "url2"] 或字典列表 [{"url": "..."}]
            cover_img = ""
            if idx < len(images):
                img_item = images[idx]
                if isinstance(img_item, str):
                    cover_img = img_item
                elif isinstance(img_item, dict):
                    cover_img = img_item.get("url") or ""

            summary = content[:200] if content else title[:200]

            return TrendingContent(
                platform="tavily",
                # Tavily 无 content_id，用 url hash 兜底
                content_id=f"tavily_{idx}_{hash(url) & 0xFFFFFFFF}",
                title=title,
                summary=summary,
                content=content,
                author="",  # Tavily basic 不返回作者
                url=url,
                likes=likes,
                comments=0,
                shares=0,
                views=0,
                cover_img=cover_img,
                published_at="",  # basic 模式不返回发布时间
                tags=[],
                title_original=title,
                summary_original=summary,
                content_original=content,
                raw={"score": score},
            )
        except Exception as e:
            logger.warning(f"[tavily] normalize failed: {e}")
            return None

    async def _call_tavily(
        self,
        query: str,
        limit: int,
        topic: str = "general",
        days: int | None = None,
    ) -> dict[str, Any]:
        """统一调 Tavily /search 端点。

        Args:
            query: 搜索关键词（空字符串时用 "trending" 兜底）
            limit: max_results
            topic: "general" / "news"
            days: 仅 topic=news 时生效，限制返回最近 N 天的结果（默认 None 不限）

        Returns:
            Tavily 响应 JSON（含 results 和 images）
        """
        client = await self._ensure_client()

        # 空关键词时用通用 query 兜底（Tavily 要求 query 非空）
        if not query.strip():
            query = "trending topics today"

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": self.search_depth,
            "topic": topic,
            "max_results": min(limit, 20),  # Tavily 上限 20
            "include_images": True,
            "include_answer": False,
            "include_raw_content": False,
        }
        # days 仅 news topic 支持，general topic 加了会报错
        if days is not None and topic == "news":
            payload["days"] = max(1, int(days))

        try:
            resp = await client.post(_TAVILY_SEARCH_URL, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"[tavily] HTTP {e.response.status_code}: {e.response.text[:300]}"
            )
            # 401/403: API Key 无效；429: 限流；402: 欠费
            return {}
        except Exception as e:
            logger.error(f"[tavily] search failed: {e}")
            return {}

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """用 Tavily /search 搜索。

        Args:
            keyword: 搜索关键词（中英文均可，Tavily 自动处理）
            limit: 返回条数上限（Tavily 单次最多 20 条）
            time_range: 时间范围（Tavily 不直接支持，忽略参数）
        """
        data = await self._call_tavily(keyword, limit, topic="general")
        if not data:
            return []

        results_raw = data.get("results", [])
        images = data.get("images", [])

        results: list[TrendingContent] = []
        for idx, item in enumerate(results_raw):
            content = self._normalize_result(item, images, idx)
            if content:
                results.append(content)

        logger.info(
            f"[tavily] search '{keyword}': "
            f"got {len(results_raw)} results, {len(results)} normalized, "
            f"{len(images)} images"
        )

        sliced = results[:limit]
        # 批量翻译为中文（原文保留在 *_original 字段）
        return await self._translate_results(sliced)

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """获取热门内容（Tavily 无"热门"概念，用 news topic 兜底）。

        Args:
            category: 可选分类（如 "technology" / "business"），作为 query
            limit: 返回条数上限
        """
        query = category or "trending news today"
        # 监控抓取只要当日新闻（days=1），避免旧新闻混入轮播图
        data = await self._call_tavily(query, limit, topic="news", days=1)
        if not data:
            return []

        results_raw = data.get("results", [])
        images = data.get("images", [])

        results: list[TrendingContent] = []
        for idx, item in enumerate(results_raw):
            content = self._normalize_result(item, images, idx)
            if content:
                # news topic 给一个基础互动量，避免被过滤
                if content.likes == 0:
                    content.likes = 100
                results.append(content)

        logger.info(
            f"[tavily] get_trending category={category}: "
            f"got {len(results)} results"
        )

        sliced = results[:limit]
        return await self._translate_results(sliced)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("[tavily] closed")
