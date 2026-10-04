"""YouTube 内容数据源（YouTube Data API v3）。

YouTube Data API v3 特点：
- 端点：https://www.googleapis.com/youtube/v3/
- 免费配额：10,000 单位/天（搜索一次消耗 ~100 单位，约 100 次搜索/天）
- 需要 API Key（申请：https://console.cloud.google.com/apis/credentials）
- 返回结构化数据：title / description / thumbnails / viewCount / likeCount / channelTitle

用途：
- 获取全球视频趋势（对标小红书视频笔记）
- 按关键词搜索热门视频（穿搭/美妆/美食/旅行/Vlog）
- 获取频道热门视频

与 TikTok 源的区别：
- YouTube 有官方 API，数据结构化、稳定、无风控
- TikTok 无公开 API，只能走 Tavily 站搜
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.tools.sources.base import ContentSource, TrendingContent
from app.tools.sources.translator import translate_batch

logger = logging.getLogger(__name__)

_YT_API_BASE = "https://www.googleapis.com/youtube/v3"
_YT_VIDEO_FIELDS = "items(id,snippet(title,description,thumbnails,channelTitle,publishedAt),statistics(viewCount,likeCount,commentCount))"


class YouTubeSource(ContentSource):
    """YouTube 内容源（Data API v3）。

    - search_trending: 搜索视频（type=video, order=viewCount/relevance）
    - get_trending: 获取热门视频列表（chart=mostPopular）
    - 自动翻译 title + description 为中文
    """

    @property
    def name(self) -> str:
        return "youtube"

    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
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
        logger.info(f"[youtube] translated {len(results)} items (zh-CN)")
        return results

    def _parse_iso_duration(self, duration: str) -> str:
        """ISO 8601 duration (PT#H#M#S) → 可读字符串。"""
        import re
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        if not match:
            return duration
        h, m, s = (int(g) if g else 0 for g in match.groups())
        parts = []
        if h:
            parts.append(f"{h}小时")
        if m:
            parts.append(f"{m}分")
        if s:
            parts.append(f"{s}秒")
        return "".join(parts) or "0秒"

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        client = await self._ensure_client()

        published_after = self._time_range_to_iso(time_range)

        params: dict[str, Any] = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "viewCount",
            "maxResults": min(limit, 50),
            "key": self._api_key,
            "videoEmbeddable": "true",
        }
        if published_after:
            params["publishedAfter"] = published_after

        try:
            resp = await client.get(f"{_YT_API_BASE}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[youtube] search '{keyword}' failed: {e}")
            return []

        items = data.get("items", [])
        if not items:
            return []

        video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]
        stats_map = await self._fetch_video_stats(client, video_ids)

        results = []
        for item in items:
            vid = item.get("id", {}).get("videoId", "")
            snippet = item.get("snippet", {})
            stats = stats_map.get(vid, {})

            thumb = snippet.get("thumbnails", {})
            cover = ""
            for quality in ("high", "medium", "default"):
                if thumb.get(quality, {}).get("url"):
                    cover = thumb[quality]["url"]
                    break

            results.append(TrendingContent(
                platform="youtube",
                content_id=vid,
                title=snippet.get("title", ""),
                summary=snippet.get("description", "")[:200],
                content=snippet.get("description", ""),
                author=snippet.get("channelTitle", ""),
                url=f"https://www.youtube.com/watch?v={vid}",
                likes=int(stats.get("likeCount", 0)),
                views=int(stats.get("viewCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                cover_img=cover,
                published_at=snippet.get("publishedAt", ""),
                tags=["youtube", "video"],
                title_original=snippet.get("title", ""),
                summary_original=snippet.get("description", "")[:200],
                content_original=snippet.get("description", ""),
            ))

        results = await self._translate_results(results)
        logger.info(f"[youtube] search '{keyword}': got {len(results)} results")
        return results

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        client = await self._ensure_client()

        params: dict[str, Any] = {
            "part": "snippet,contentDetails,statistics",
            "chart": "mostPopular",
            "maxResults": min(limit, 50),
            "key": self._api_key,
        }
        if category:
            category_id = self._map_category(category)
            if category_id:
                params["videoCategoryId"] = category_id

        try:
            resp = await client.get(f"{_YT_API_BASE}/videos", params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[youtube] get_trending failed: {e}")
            return []

        items = data.get("items", [])
        results = []
        for item in items:
            vid = item.get("id", "")
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content_details = item.get("contentDetails", {})

            thumb = snippet.get("thumbnails", {})
            cover = ""
            for quality in ("maxres", "high", "medium", "default"):
                if thumb.get(quality, {}).get("url"):
                    cover = thumb[quality]["url"]
                    break

            duration = content_details.get("duration", "")

            results.append(TrendingContent(
                platform="youtube",
                content_id=vid,
                title=snippet.get("title", ""),
                summary=snippet.get("description", "")[:200],
                content=snippet.get("description", ""),
                author=snippet.get("channelTitle", ""),
                url=f"https://www.youtube.com/watch?v={vid}",
                likes=int(stats.get("likeCount", 0)),
                views=int(stats.get("viewCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                cover_img=cover,
                published_at=snippet.get("publishedAt", ""),
                tags=["youtube", "video", "trending"] + ([duration] if duration else []),
                title_original=snippet.get("title", ""),
                summary_original=snippet.get("description", "")[:200],
                content_original=snippet.get("description", ""),
            ))

        results = await self._translate_results(results)
        logger.info(f"[youtube] get_trending: got {len(results)} results")
        return results

    async def _fetch_video_stats(
        self,
        client: httpx.AsyncClient,
        video_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not video_ids:
            return {}

        stats_map: dict[str, dict[str, Any]] = {}
        batch_size = 50
        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i:i + batch_size]
            params = {
                "part": "statistics",
                "id": ",".join(batch),
                "key": self._api_key,
            }
            try:
                resp = await client.get(f"{_YT_API_BASE}/videos", params=params)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("items", []):
                    stats_map[item["id"]] = item.get("statistics", {})
            except Exception as e:
                logger.warning(f"[youtube] fetch stats batch failed: {e}")

        return stats_map

    def _time_range_to_iso(self, time_range: str) -> str:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        deltas = {
            "day": timedelta(days=1),
            "week": timedelta(weeks=1),
            "month": timedelta(days=30),
            "year": timedelta(days=365),
        }
        delta = deltas.get(time_range)
        if delta:
            return (now - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
        return ""

    def _map_category(self, category: str) -> str:
        mapping = {
            "music": "10",
            "gaming": "20",
            "sports": "17",
            "news": "25",
            "entertainment": "24",
            "film": "1",
            "education": "27",
            "tech": "28",
            "travel": "19",
            "howto": "26",
            "fashion": "26",
            "beauty": "26",
        }
        return mapping.get(category.lower(), "")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None