"""Hacker News 内容数据源。

Hacker News API 由 Firebase 托管，完全免费、无需认证。
- 端点：https://hacker-news.firebaseio.com/v0/
- 支持拿热门故事（topstories / beststories / newstories）
- 搜索需要用 Algolia 提供的 HN Search API（https://hn.algolia.com/api）

特点：技术圈/创业圈/泛科技话题的热点
局限：内容偏向技术，不适合美妆/穿搭等生活方式话题
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.agents.skills.sources.base import ContentSource, TrendingContent
from app.agents.skills.sources.translator import translate_batch

logger = logging.getLogger(__name__)

_HN_FIREBASE_BASE = "https://hacker-news.firebaseio.com/v0"
_HN_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"

# og:image / twitter:image 正则（大小写不敏感，兼容单双引号、属性顺序）
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image(?::url|:secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TWITTER_IMAGE_RE = re.compile(
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::url|:secure_url)?["\']',
    re.IGNORECASE,
)
_TWITTER_IMAGE_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    re.IGNORECASE,
)
# <link rel="image_src" href="..."> 兜底
_LINK_IMAGE_RE = re.compile(
    r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# 真实浏览器 UA + 完整请求头（绕过 Cloudflare 等反爬）
# 关键：Sec-Fetch-* 和 Sec-Ch-Ua 头模拟真实浏览器，httpx 默认不带这些
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# 完整的浏览器请求头（绕过反爬关键）
# 注意：不带 br（brotli），httpx 默认不支持 brotli 解码
_BROWSER_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}


class HackerNewsSource(ContentSource):
    """Hacker News 内容源（零认证）。

    - search_trending 用 Algolia API（支持全文搜索 + 按热度排序）
    - get_trending 用 Firebase API（拿 topstories）
    """

    @property
    def name(self) -> str:
        return "hackernews"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": "multi-agent-xhs-platform/1.0"},
            )
        return self._client

    async def _translate_results(self, results: list[TrendingContent]) -> list[TrendingContent]:
        """批量翻译结果（title + summary），原文保留在 *_original 字段。

        翻译失败时降级为原文，不阻塞流程。
        """
        if not results:
            return results
        client = await self._ensure_client()
        # 收集所有需要翻译的文本（title + summary 各一批）
        titles = [r.title for r in results]
        summaries = [r.summary for r in results]
        # 并发翻译（translator 内部有信号量限流 + 缓存）
        zh_titles, zh_summaries = await asyncio.gather(
            translate_batch(titles, target_lang="zh-CN", client=client),
            translate_batch(summaries, target_lang="zh-CN", client=client),
        )
        # 回填：title/summary 用译文，*_original 保留英文原文
        for r, zh_t, zh_s in zip(results, zh_titles, zh_summaries):
            r.title = zh_t
            r.summary = zh_s
        logger.info(f"[hackernews] translated {len(results)} items (zh-CN)")
        return results

    async def _fetch_og_image(self, client: httpx.AsyncClient, url: str) -> str:
        """抓取单个 URL 的 og:image / twitter:image / link[image_src] / favicon。

        优先级：og:image > twitter:image > link[image_src] > favicon.ico（后端验证）
        > favicon.ico（构造 URL，让前端浏览器加载）

        只抓前 64KB HTML（og:image 在 <head> 里，不需要全文）。
        超时 8s，失败时返回构造的 favicon URL（让前端浏览器尝试加载）。
        """
        # HN 自身讨论页 / Twitter(X) 没有 og:image 或反爬，跳过
        if "news.ycombinator.com" in url:
            return ""
        if any(d in url for d in ("twitter.com", "x.com", "youtube.com", "youtu.be")):
            return ""

        from urllib.parse import urljoin, urlparse

        parsed_url = urlparse(url)
        domain = parsed_url.hostname or ""
        if not domain:
            return ""

        favicon_url = f"{parsed_url.scheme}://{domain}/favicon.ico"

        try:
            resp = await client.get(
                url,
                timeout=httpx.Timeout(8.0, connect=5.0),
                follow_redirects=True,
                headers=_BROWSER_HEADERS,
            )
            if resp.status_code == 200:
                # 只取前 64KB（og:image 在 <head> 里）
                html = resp.text[:65536]
                # 依次尝试：og:image（正序/倒序）→ twitter:image（正序/倒序）→ link[image_src]
                for pattern in (_OG_IMAGE_RE, _OG_IMAGE_RE_REV, _TWITTER_IMAGE_RE, _TWITTER_IMAGE_RE_REV, _LINK_IMAGE_RE):
                    m = pattern.search(html)
                    if m:
                        img_url = m.group(1).strip()
                        if img_url.startswith("http"):
                            return img_url
                        # 相对路径 → 拼成绝对 URL
                        if img_url.startswith("//"):
                            return "https:" + img_url
                        if img_url.startswith("/"):
                            return urljoin(url, img_url)

            # og:image 未命中：尝试 favicon.ico 作为兜底（至少有网站图标）
            try:
                fav_resp = await client.get(
                    favicon_url,
                    timeout=httpx.Timeout(5.0, connect=3.0),
                    follow_redirects=True,
                    headers={**_BROWSER_HEADERS, "Sec-Fetch-Dest": "image", "Sec-Fetch-Mode": "no-cors", "Accept": "image/*,*/*;q=0.8"},
                )
                if fav_resp.status_code == 200:
                    content_type = fav_resp.headers.get("content-type", "")
                    if content_type.startswith("image/") and len(fav_resp.content) > 100:
                        return favicon_url
            except Exception:
                pass

            # 后端抓取失败（反爬/超时）：返回构造的 favicon URL，让前端浏览器尝试加载
            # 浏览器有完整的请求头和 Cloudflare challenge 处理能力，成功率比后端高
            # 前端加载失败时用 onerror 回退到字母色块
            logger.info(f"[hackernews] og:image fetch failed, returning favicon URL for frontend: {favicon_url}")
            return favicon_url

        except Exception:
            # 网络异常：仍返回 favicon URL，让前端尝试
            return favicon_url

    async def _fetch_cover_images(self, results: list[TrendingContent]) -> None:
        """并发抓取所有结果的 og:image，直接修改 cover_img 字段。

        - 限制 8 并发，避免请求爆炸
        - 整体超时 20s（asyncio.wait_for 兜底，给反爬网站足够时间）
        - 已有 cover_img 的跳过
        """
        if not results:
            return
        client = await self._ensure_client()
        sem = asyncio.Semaphore(8)

        async def _fetch_one(r: TrendingContent) -> None:
            if r.cover_img:
                return
            async with sem:
                try:
                    r.cover_img = await self._fetch_og_image(client, r.url)
                except Exception as e:
                    logger.warning(f"[hackernews] _fetch_one failed for {r.url[:60]}: {e}")

        try:
            await asyncio.wait_for(
                asyncio.gather(*[_fetch_one(r) for r in results], return_exceptions=True),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[hackernews] fetch_cover_images timed out (20s)")

        hit = sum(1 for r in results if r.cover_img)
        logger.info(f"[hackernews] og:image fetched: {hit}/{len(results)} hits")

    def _normalize_algolia(self, hit: dict[str, Any]) -> TrendingContent | None:
        """归一化 Algolia 搜索结果。"""
        try:
            object_id = hit.get("objectID") or ""
            if not object_id:
                return None

            title = (hit.get("title") or hit.get("story_title") or "").strip()
            url = hit.get("url") or hit.get("story_url") or ""
            if not url and object_id:
                url = f"https://news.ycombinator.com/item?id={object_id}"

            author = hit.get("author") or ""
            points = int(hit.get("points") or 0)
            num_comments = int(hit.get("num_comments") or 0)
            created_at_i = int(hit.get("created_at_i") or 0)

            # 内容：优先 story_text，没有就用 comment_text
            content = (hit.get("story_text") or hit.get("comment_text") or "").strip()
            # 去除 HTML 标签（简单处理）
            if content and "<" in content:
                import re
                content = re.sub(r"<[^>]+>", "", content).strip()

            summary = content[:200] if content else title[:200]

            published_at = ""
            if created_at_i:
                published_at = datetime.fromtimestamp(created_at_i, tz=timezone.utc).isoformat()

            tags = []
            if hit.get("_tags"):
                tags = list(hit.get("_tags"))

            return TrendingContent(
                platform="hackernews",
                content_id=str(object_id),
                title=title,
                summary=summary,
                content=content,
                author=f"u/{author}",
                url=url,
                likes=points,          # HN 的 points = upvotes - downvotes
                comments=num_comments,
                shares=0,
                views=0,
                cover_img="",
                published_at=published_at,
                tags=tags,
                title_original=title,
                summary_original=summary,
                content_original=content,
                raw={
                    "type": hit.get("_tags", []),
                },
            )
        except Exception as e:
            logger.warning(f"[hackernews] normalize algolia failed: {e}")
            return None

    def _normalize_firebase(self, item: dict[str, Any]) -> TrendingContent | None:
        """归一化 Firebase API 结果。"""
        try:
            item_id = item.get("id")
            if item_id is None:
                return None

            title = (item.get("title") or "").strip()
            url = item.get("url") or ""
            if not url:
                url = f"https://news.ycombinator.com/item?id={item_id}"

            by = item.get("by") or ""
            score = int(item.get("score") or 0)
            descendants = int(item.get("descendants") or 0)
            time_ts = int(item.get("time") or 0)
            item_type = item.get("type") or ""

            content = ""
            text = item.get("text") or ""
            if text:
                import re
                content = re.sub(r"<[^>]+>", "", text).strip()

            summary = content[:200] if content else title[:200]

            published_at = ""
            if time_ts:
                published_at = datetime.fromtimestamp(time_ts, tz=timezone.utc).isoformat()

            return TrendingContent(
                platform="hackernews",
                content_id=str(item_id),
                title=title,
                summary=summary,
                content=content,
                author=f"u/{by}",
                url=url,
                likes=score,
                comments=descendants,
                shares=0,
                views=0,
                cover_img="",
                published_at=published_at,
                tags=[item_type] if item_type else [],
                title_original=title,
                summary_original=summary,
                content_original=content,
                raw={"type": item_type},
            )
        except Exception as e:
            logger.warning(f"[hackernews] normalize firebase failed: {e}")
            return None

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """用 Algolia HN Search API 搜索。

        Args:
            keyword: 搜索关键词
            limit: 返回条数
            time_range: "day" / "week" / "month" / "year" / "all"
        """
        client = await self._ensure_client()

        # 时间范围转 Algolia 的 numericFilters
        time_map = {
            "day": 86400,
            "week": 604800,
            "month": 2592000,
            "year": 31536000,
            "all": 0,
        }
        seconds = time_map.get(time_range, 604800)

        params: dict[str, Any] = {
            "query": keyword,
            "tags": "story",              # 只要故事帖，不要评论
            "hitsPerPage": min(limit, 50),
        }
        if seconds > 0:
            import time
            now = int(time.time())
            params["numericFilters"] = f"created_at_i>={now - seconds}"

        try:
            # Algolia 按 popularity 排序（points + comments 加权）
            params["restrictSearchableAttributes"] = "title,story_text"
            resp = await client.get(
                f"{_HN_ALGOLIA_BASE}/search",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            results: list[TrendingContent] = []
            for hit in hits:
                content = self._normalize_algolia(hit)
                if content:
                    results.append(content)

            logger.info(
                f"[hackernews] search '{keyword}' t={time_range}: "
                f"got {len(hits)} hits, {len(results)} normalized"
            )
            sliced = results[:limit]
            # 抓取文章封面图（og:image），让前端有真实图片而非字母占位
            await self._fetch_cover_images(sliced)
            # 批量翻译为中文（原文保留在 *_original 字段）
            return await self._translate_results(sliced)
        except Exception as e:
            logger.error(f"[hackernews] search_trending failed: {e}")
            return []

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """用 Firebase API 拿 HN 热门故事。

        Args:
            category: "top" / "best" / "new"（默认 top）
            limit: 返回条数
        """
        client = await self._ensure_client()

        category = category or "top"
        stories_path = {
            "top": "/topstories.json",
            "best": "/beststories.json",
            "new": "/newstories.json",
        }.get(category, "/topstories.json")

        try:
            # 先拿热门故事 ID 列表
            resp = await client.get(f"{_HN_FIREBASE_BASE}{stories_path}")
            resp.raise_for_status()
            story_ids: list[int] = resp.json()
            if not story_ids:
                return []

            # 取前 N 个（限制并发，避免请求爆炸）
            target_ids = story_ids[:limit]

            results: list[TrendingContent] = []
            # 用并发拿每个 story 的详情
            async def fetch_item(sid: int) -> TrendingContent | None:
                try:
                    r = await client.get(f"{_HN_FIREBASE_BASE}/item/{sid}.json")
                    r.raise_for_status()
                    item_data = r.json()
                    if item_data is None:
                        return None
                    return self._normalize_firebase(item_data)
                except Exception as e:
                    logger.warning(f"[hackernews] fetch item {sid} failed: {e}")
                    return None

            # 分批并发，每批 10 个
            batch_size = 10
            for i in range(0, len(target_ids), batch_size):
                batch = target_ids[i : i + batch_size]
                batch_results = await asyncio.gather(*[fetch_item(sid) for sid in batch])
                for c in batch_results:
                    if c:
                        results.append(c)

            logger.info(
                f"[hackernews] get_trending category={category}: "
                f"got {len(results)} normalized"
            )
            sliced = results[:limit]
            # 抓取文章封面图（og:image），让前端有真实图片而非字母占位
            await self._fetch_cover_images(sliced)
            # 批量翻译为中文（原文保留在 *_original 字段）
            return await self._translate_results(sliced)
        except Exception as e:
            logger.error(f"[hackernews] get_trending failed: {e}")
            return []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("[hackernews] closed")
