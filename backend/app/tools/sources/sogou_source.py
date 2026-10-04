"""头条搜索内容源（免费，无需 API Key，国内直连，中文分词优秀）。

so.toutiao.com 是字节跳动旗下的搜索引擎，特点：
- 完全免费，无需 API Key
- 国内直连，无需代理
- 中文分词准确，搜索结果质量高
- 反爬宽松，服务器端请求即可正常获取结果
- 内容覆盖全网（包括头条号/微信公众号/知乎/B站等）
- 搜索结果自带封面图（toutiaoimg.com CDN）

与搜狗/Bing 的区别：
- 搜狗：反爬严格，连续搜索触发验证页面，不可靠
- Bing 中国版：服务器端请求时中文分词崩溃（拆成单字），不可用
- 头条搜索：反爬宽松 + 中文分词准确 + 国内直连，最可靠的免费方案

解析策略：
- 用 /search/jump 链接的 jtoken 分组，每组 = 一条搜索结果
- 组内第一个有意义的链接文本 = 标题
- 组内较长的链接文本 = 摘要
- 来源信息匹配日期/网站名模式
- 封面图：从组附近 HTML 提取 img 标签
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from typing import Any

import httpx

from app.tools.sources.base import ContentSource, TrendingContent
from app.tools.sources.translator import translate_batch

logger = logging.getLogger(__name__)

_TOUTIAO_SEARCH_URL = "https://so.toutiao.com/search"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_BROWSER_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

_RE_JUMP_LINK = re.compile(
    r'<a[^>]*href="(/search/jump\?[^"]*)"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_RE_JTOKEN = re.compile(r"jtoken=([a-f0-9]+)")
_RE_IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"', re.DOTALL | re.IGNORECASE)
_RE_TAG_STRIP = re.compile(r"<[^>]+>")
_RE_HTML_ENTITY = re.compile(r"&#(\d+);|&amp;|&lt;|&gt;|&quot;|&#x([0-9a-fA-F]+);")
_RE_NOISE = re.compile(
    r"^(\d+次播放|\d+:\d+$|\d{4}年\d+月\d+日$|.*网\d{4}年\d+月\d+日$|\d+月\d+日$)"
)
_RE_SOURCE = re.compile(r"\d{4}年|网$")


def _decode_html_entities(text: str) -> str:
    def _replace(m: re.Match) -> str:
        if m.group(1):
            return chr(int(m.group(1)))
        if m.group(2):
            return chr(int(m.group(2), 16))
        entity = m.group(0)
        return {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"'}.get(entity, entity)

    return _RE_HTML_ENTITY.sub(_replace, text)


def _strip_tags(html: str) -> str:
    return _RE_TAG_STRIP.sub("", html).strip()


class SogouSource(ContentSource):
    """头条搜索内容源（免费，无需 API Key，国内直连）。

    - search_trending: 调 so.toutiao.com/search，按相关性排序
    - get_trending: 调 so.toutiao.com/search，热门话题搜索
    - 中文分词准确，搜索结果质量高
    - 反爬宽松，服务器端请求即可正常获取
    - 封面图：从搜索结果中提取 img 标签

    注意：虽然类名叫 SogouSource（历史原因），实际使用的是头条搜索。
    """

    @property
    def name(self) -> str:
        return "sogou"

    def __init__(
        self,
        timeout: float = 20.0,
        max_retries: int = 2,
        min_interval: float = 3.0,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers=_BROWSER_HEADERS,
                follow_redirects=True,
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
        logger.info(f"[sogou] translated {len(results)} items (zh-CN)")
        return results

    def _parse_html(self, html: str) -> list[TrendingContent]:
        all_jumps = list(_RE_JUMP_LINK.finditer(html))
        if not all_jumps:
            return []

        groups: dict[str, list[dict[str, Any]]] = OrderedDict()
        for m in all_jumps:
            href = m.group(1)
            jt_match = _RE_JTOKEN.search(href)
            if not jt_match:
                continue
            jtoken = jt_match.group(1)
            if jtoken not in groups:
                groups[jtoken] = []
            text = _strip_tags(_decode_html_entities(m.group(2)))
            groups[jtoken].append({
                "text": text,
                "href": href,
                "pos": m.start(),
            })

        results: list[TrendingContent] = []
        idx = 0

        for items in groups.values():
            if not items:
                continue
            items.sort(key=lambda x: x["pos"])

            title = ""
            snippet = ""
            source = ""
            url = f"https://so.toutiao.com{_decode_html_entities(items[0]['href'])}"

            for item in items:
                text = item["text"]
                if not text or len(text) < 3:
                    continue

                if _RE_NOISE.match(text):
                    source = text
                    continue

                if not title and 4 < len(text) < 120:
                    title = text
                elif not snippet and len(text) > 15:
                    snippet = text[:300]
                elif _RE_SOURCE.search(text) and not source:
                    source = text

            if not title:
                continue

            summary = snippet[:200] if snippet else title[:200]

            cover_img = ""
            pos_start = items[0]["pos"]
            pos_end = items[-1]["pos"] + 500
            block = html[max(0, pos_start - 500):min(len(html), pos_end)]
            img_match = _RE_IMG_SRC.search(block)
            if img_match:
                img_url = img_match.group(1).strip()
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    img_url = "https://so.toutiao.com" + img_url
                if img_url.startswith("http"):
                    cover_img = img_url

            position = idx + 1
            likes = max(0, 1000 - position * 50)

            results.append(TrendingContent(
                platform="sogou",
                content_id=f"sogou_{idx}_{hash(url) & 0xFFFFFFFF}",
                title=title,
                summary=summary,
                content=snippet or summary,
                author=source,
                url=url,
                likes=likes,
                comments=0,
                shares=0,
                views=0,
                cover_img=cover_img,
                published_at="",
                tags=[],
                title_original=title,
                summary_original=summary,
                content_original=snippet or summary,
                raw={"position": position, "source": source},
            ))
            idx += 1

        return results

    async def _call_toutiao(
        self,
        query: str,
        limit: int = 20,
        page: int = 0,
    ) -> str:
        client = await self._ensure_client()

        if not query.strip():
            query = "今日热点"

        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self._last_request_time = time.monotonic()

        params: dict[str, Any] = {
            "keyword": query,
        }

        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.get(_TOUTIAO_SEARCH_URL, params=params)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code == 429 and attempt < self.max_retries:
                    wait = 2 ** attempt + 1
                    logger.warning(
                        f"[sogou] 429 rate limited (attempt {attempt+1}/{self.max_retries+1}), "
                        f"retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"[sogou] HTTP {status_code}: {e.response.text[:300]}")
                return ""
            except Exception as e:
                logger.error(f"[sogou] search failed: {e}")
                return ""
        return ""

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        html = await self._call_toutiao(keyword, limit)
        if not html:
            return []

        results = self._parse_html(html)
        logger.info(f"[sogou] search '{keyword}': got {len(results)} results")

        sliced = results[:limit]
        translated = await self._translate_results(sliced)
        return translated

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        query = category if category else "今日热点"
        return await self.search_trending(query, limit)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("[sogou] closed")