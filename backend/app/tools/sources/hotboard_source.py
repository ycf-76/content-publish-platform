"""可插拔热榜内容源 — 调公益 API 拿实时热搜排名。

与 sogou/tavily 等关键词搜索引擎不同，热榜源直接调 60s/xxapi 等
公益 API，返回的是平台实时热搜 Top N（带热度值），不是关键词匹配结果。

配置驱动：
- hotboard_sources.json 定义每个热榜平台的 primary/backup URL
- enabled=true 的平台启动时自动注册为 ContentSource
- 添加/删除/禁用源只需改 JSON，无需改代码

数据源：
- 60s API (v2): https://60s.crystelf.top/v2/{platform} — 国内镜像，免费，无需 Key
- xxapi (v2): https://v2.xxapi.cn/api/{platform}hot — 60s 降级备选
- 原始域名 60s.viki.moe 已迁移至 CF Workers，国内 403，已弃用

SSL：公益镜像证书可能过期/自签，verify=False（只读公开数据，安全风险可接受）
"""

from __future__ import annotations

import json
import logging
import time
import warnings
from pathlib import Path
from typing import Any

import httpx

from app.tools.sources.base import ContentSource, TrendingContent

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "hotboard_sources.json"

_CACHE_TTL = 300

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def load_hotboard_config() -> dict[str, dict[str, Any]]:
    """读取热榜源配置 JSON。

    Returns:
        {platform_key: {label, primary, backup, enabled}, ...}
        只返回 enabled=true 的条目。
    """
    if not _CONFIG_PATH.exists():
        logger.warning(f"[hotboard] config not found: {_CONFIG_PATH}")
        return {}
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"[hotboard] config parse error: {e}")
        return {}

    result = {}
    for key, val in raw.items():
        if key.startswith("_"):
            continue
        if not isinstance(val, dict):
            continue
        if not val.get("enabled", False):
            continue
        if not val.get("primary"):
            continue
        result[key] = val
    return result


def _parse_hot_response(data: Any) -> list[dict[str, Any]]:
    """解析 60s/xxapi 响应，兼容多种嵌套结构。

    60s v2: {"code": 200, "data": [{title, hot, url}, ...]}
    部分端点: {"code": 200, "data": {"data": [...]}}
    xxapi:   {"code": 200, "data": [{title, hot, url}, ...]}
    """
    if isinstance(data, dict):
        payload = data.get("data")
        if isinstance(payload, dict):
            payload = payload.get("data") or payload.get("list") or []
    elif isinstance(data, list):
        payload = data
    else:
        return []

    items = []
    if not isinstance(payload, list):
        return []

    for it in payload:
        if isinstance(it, str):
            title = it.strip()
            if not title:
                continue
            items.append({"title": title, "hot": 0, "url": ""})
            continue
        if not isinstance(it, dict):
            continue
        title = it.get("title") or it.get("word") or it.get("name") or it.get("keyword")
        if not title:
            continue
        hot_raw = it.get("hot") or it.get("hot_value") or it.get("num") or 0
        try:
            hot_val = int(float(str(hot_raw)))
        except (ValueError, TypeError):
            hot_val = 0
        url = it.get("url") or it.get("link") or it.get("mobil_url") or ""
        items.append({
            "title": str(title).strip(),
            "hot": hot_val,
            "url": str(url).strip(),
        })
    return items


class HotboardSource(ContentSource):
    """单个热榜平台内容源。

    每个实例代表一个平台（如 weibo/douyin/zhihu），
    通过 primary/backup URL 调公益 API 拿实时热搜。
    主源失败自动降级到备源。
    """

    def __init__(
        self,
        platform_key: str,
        label: str,
        primary_url: str,
        backup_url: str = "",
        timeout: float = 10.0,
    ) -> None:
        self._key = platform_key
        self._label = label
        self._primary_url = primary_url
        self._backup_url = backup_url
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._cache: tuple[float, list[TrendingContent]] | None = None

    @property
    def name(self) -> str:
        return self._key

    @property
    def label(self) -> str:
        return self._label

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"User-Agent": _BROWSER_UA},
                follow_redirects=True,
                verify=False,
            )
        return self._client

    async def _fetch_json(self, url: str) -> dict[str, Any] | None:
        """请求单个 URL，返回 JSON 或 None。"""
        client = await self._ensure_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[hotboard] {self._key} fetch {url} failed: {e}")
            return None

    async def _fetch_hotlist(self) -> list[dict[str, Any]]:
        """主源 → 备源，自动降级。"""
        for url in (self._primary_url, self._backup_url):
            if not url:
                continue
            data = await self._fetch_json(url)
            if data is None:
                continue
            items = _parse_hot_response(data)
            if items:
                logger.info(f"[hotboard] {self._key}: got {len(items)} items from {url}")
                return items
        logger.warning(f"[hotboard] {self._key}: all sources failed")
        return []

    def _to_trending_content(
        self, items: list[dict[str, Any]]
    ) -> list[TrendingContent]:
        """转成统一 TrendingContent 结构。"""
        now = time.time()
        results = []
        for i, it in enumerate(items):
            hot = it.get("hot", 0)
            results.append(TrendingContent(
                platform=self._key,
                content_id=f"hotboard_{self._key}_{i}",
                title=it["title"],
                summary=it["title"],
                content=it["title"],
                author=self._label,
                url=it.get("url", ""),
                likes=hot,
                comments=0,
                shares=0,
                views=0,
                cover_img="",
                published_at="",
                tags=[self._label, "热搜"],
                title_original=it["title"],
                summary_original=it["title"],
                content_original=it["title"],
                raw={"hot": hot, "rank": i + 1},
            ))
        return results

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """关键词过滤热搜：先拿全量热榜，再按关键词过滤。"""
        all_items = await self._get_all_cached()
        if not keyword.strip():
            return all_items[:limit]

        kw_lower = keyword.strip().lower()
        filtered = [
            it for it in all_items
            if kw_lower in it.title.lower() or kw_lower in it.summary.lower()
        ]
        if not filtered:
            return all_items[:limit]
        return filtered[:limit]

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """获取实时热搜榜。"""
        all_items = await self._get_all_cached()
        return all_items[:limit]

    async def _get_all_cached(self) -> list[TrendingContent]:
        """带缓存的全量热榜获取（5 分钟 TTL）。"""
        now = time.time()
        if self._cache and now - self._cache[0] < _CACHE_TTL:
            return self._cache[1]

        raw = await self._fetch_hotlist()
        items = self._to_trending_content(raw)

        if items:
            self._cache = (now, items)
        elif self._cache:
            items = self._cache[1]

        return items

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info(f"[hotboard] {self._key} closed")