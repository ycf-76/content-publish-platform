"""Serper 全网搜索内容源（Google SERP 数据）。

Serper 是 Google 搜索结果 API，特点：
- 端点：POST https://google.serper.dev/search
- 返回 Google 原始 SERP JSON（organic / knowledgeGraph / peopleAlsoAsk）
- 2,500 次免费额度，无需信用卡
- 之后 $0.30/千次，全网最便宜的 Google SERP API
- 申请地址：https://serper.dev/

与 Tavily 的区别：
- Tavily 返回 AI 友好的 content 摘要 + 图片，专为 Agent 设计
- Serper 返回 Google 原始搜索结果，有 snippet（摘要）但无全文
- Serper 更便宜，适合做 Tavily 额度用完后的降级备选
- Serper 支持 Google 全垂类：Search/Images/News/Maps/Places/Videos/Shopping/Scholar

用途：
- Tavily 额度耗尽时的降级搜索源
- 搜 "小红书 + 关键词" 获取被转载/引用的小红书内容
- site: 站内搜索（知乎/微博/B站等搜索引擎可索引的中文平台）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.tools.sources.base import ContentSource, TrendingContent
from app.tools.sources.translator import translate_batch

logger = logging.getLogger(__name__)

_SERPER_SEARCH_URL = "https://google.serper.dev/search"


class SerperSource(ContentSource):
    """Serper 全网搜索内容源（Google SERP）。

    - search_trending: 调 /search，按 position 排序
    - get_trending: 调 /search，topic=news
    - 自动翻译 snippet 为中文（原文保留在 *_original 字段）
    """

    @property
    def name(self) -> str:
        return "serper"

    def __init__(
        self,
        api_key: str,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            from app.tools.sources.base import get_proxy_url
            proxy = get_proxy_url()
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
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
        logger.info(f"[serper] translated {len(results)} items (zh-CN)")
        return results

    def _normalize_result(
        self,
        item: dict[str, Any],
        idx: int,
    ) -> TrendingContent | None:
        """归一化 Serper organic 单条结果。

        Serper organic result 结构：
        - title: 标题
        - link: URL
        - snippet: 摘要（Google 生成，约 150-300 字）
        - position: 排名位置（1-based）
        - sitelinks: 子链接（可选）
        """
        try:
            url = item.get("link") or ""
            title = (item.get("title") or "").strip()
            snippet = (item.get("snippet") or "").strip()

            if not url or not title:
                return None

            position = int(item.get("position") or (idx + 1))
            likes = max(0, 1000 - position * 50)

            summary = snippet[:200] if snippet else title[:200]

            return TrendingContent(
                platform="serper",
                content_id=f"serper_{idx}_{hash(url) & 0xFFFFFFFF}",
                title=title,
                summary=summary,
                content=snippet,
                author="",
                url=url,
                likes=likes,
                comments=0,
                shares=0,
                views=0,
                cover_img="",
                published_at="",
                tags=[],
                title_original=title,
                summary_original=summary,
                content_original=snippet,
                raw={"position": position},
            )
        except Exception as e:
            logger.warning(f"[serper] normalize failed: {e}")
            return None

    async def _call_serper(
        self,
        query: str,
        limit: int = 20,
        topic: str = "general",
        tbs: str = "",
    ) -> dict[str, Any]:
        """调 Serper /search 端点。

        Args:
            query: 搜索关键词
            limit: 返回条数
            topic: "general" / "news" / "images" / "videos" / "scholar"
            tbs: 时间范围过滤（"qdr:h"=1小时, "qdr:d"=1天, "qdr:w"=1周, "qdr:m"=1月, "qdr:y"=1年）
        """
        client = await self._ensure_client()

        if not query.strip():
            query = "trending topics today"

        payload: dict[str, Any] = {
            "q": query,
            "num": min(limit, 20),
            "gl": "cn",
            "hl": "zh-cn",
        }
        if topic == "news":
            payload["tbm"] = "nws"
        elif topic == "images":
            payload["tbm"] = "isch"
        elif topic == "videos":
            payload["tbm"] = "vid"
        elif topic == "scholar":
            payload["tbm"] = "sch"
        if tbs:
            payload["tbs"] = tbs

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                resp = await client.post(_SERPER_SEARCH_URL, json=payload)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code == 429 and attempt < max_retries:
                    wait = 2 ** attempt + 1
                    logger.warning(
                        f"[serper] 429 rate limited (attempt {attempt+1}/{max_retries+1}), "
                        f"retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"[serper] HTTP {status_code}: {e.response.text[:300]}")
                return {}
            except Exception as e:
                logger.error(f"[serper] search failed: {e}")
                return {}
        return {}

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        tbs_map = {"hour": "qdr:h", "day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}
        tbs = tbs_map.get(time_range, "")

        data = await self._call_serper(keyword, limit, topic="general", tbs=tbs)
        if not data:
            return []

        results_raw = data.get("organic", [])
        results: list[TrendingContent] = []
        for idx, item in enumerate(results_raw):
            content = self._normalize_result(item, idx)
            if content:
                results.append(content)

        logger.info(f"[serper] search '{keyword}': got {len(results)} results")

        sliced = results[:limit]
        return await self._translate_results(sliced)

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        query = category or "trending news today"
        data = await self._call_serper(query, limit, topic="news", tbs="qdr:d")
        if not data:
            return []

        news_key = "news" if "news" in data else "organic"
        results_raw = data.get(news_key, [])
        results: list[TrendingContent] = []
        for idx, item in enumerate(results_raw):
            content = self._normalize_result(item, idx)
            if content:
                if content.likes == 0:
                    content.likes = 100
                results.append(content)

        logger.info(f"[serper] get_trending category={category}: got {len(results)} results")

        sliced = results[:limit]
        return await self._translate_results(sliced)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("[serper] closed")