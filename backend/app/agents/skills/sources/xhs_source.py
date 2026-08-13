"""小红书内容源（包装现有 mcp_manager）。

保留小红书爬取能力，但不作为默认数据源（风控风险）。
后续用户配置 + 桥接页面就绪时可用。

架构：
  XhsSource
    → mcp_manager.search_notes()        # 现有 MCPClientManager
    → PluginMCPClient / XhsMCPClient    # 现有实现
    → 浏览器扩展 / Playwright worker     # 现有底层

返回的 dict 字段（来自 xhs_search._normalize）：
  note_id, title, summary, likes, comments, url, cover_img, author

归一化成 TrendingContent 时补全缺失字段。
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.skills.sources.base import ContentSource, TrendingContent

logger = logging.getLogger(__name__)


class XhsSource(ContentSource):
    """小红书内容源（委托给现有 mcp_manager）。

    注意：小红书搜索有风控风险，默认不启用。
    需要桥接页面在线 + 浏览器扩展加载 + 登录态有效。
    """

    @property
    def name(self) -> str:
        return "xiaohongshu"

    def __init__(self) -> None:
        # 延迟 import，避免循环依赖
        self._mcp_manager: Any = None

    def _get_manager(self):
        if self._mcp_manager is None:
            from app.agents.skills.mcp.xhs_client import mcp_manager
            self._mcp_manager = mcp_manager
        return self._mcp_manager

    def _normalize(self, raw: dict[str, Any]) -> TrendingContent | None:
        """把 search_with_details 的 dict 归一化成 TrendingContent。

        详情采集后（detail_collected=True）包含完整字段：
        likes/comments/collects/shares/desc/tags/type/author_id/author_avatar
        未采集详情的条目只有基础字段（likes 来自搜索页，comments=0）。
        """
        try:
            note_id = str(raw.get("note_id") or "")
            if not note_id:
                return None

            title = (raw.get("title") or "").strip()
            # desc 是小红书笔记正文（详情采集后才有）
            desc = (raw.get("desc") or "").strip()
            summary = (raw.get("summary") or desc).strip()
            content = desc or summary
            author = raw.get("author") or ""
            url = raw.get("url") or ""
            cover_img = raw.get("cover_img") or ""
            likes = int(raw.get("likes") or 0)
            comments = int(raw.get("comments") or 0)
            shares = int(raw.get("shares") or 0)
            collects = int(raw.get("collects") or 0)
            tags_raw = raw.get("tags") or []
            tags = tags_raw if isinstance(tags_raw, list) else []

            return TrendingContent(
                platform="xiaohongshu",
                content_id=note_id,
                title=title,
                summary=summary[:200],
                content=content,
                author=author,
                url=url,
                likes=likes,
                comments=comments,
                shares=shares,
                collects=collects,
                views=0,
                cover_img=cover_img,
                published_at="",
                tags=tags,
                raw=raw,
            )
        except Exception as e:
            logger.warning(f"[xiaohongshu] normalize failed: {e}")
            return None

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """调 mcp_manager.search_notes_with_details 获取带详情的搜索结果。

        小批深层数据采集：搜索 min(limit,8) 条，对 top 5 点击进入详情页，
        拦截 feed XHR 提取 likes/comments/collects/shares/desc/tags 等完整字段。
        绕过直接 goto /explore/{note_id} 被风控(300031)的问题。
        """
        manager = self._get_manager()
        # 小批深层数据采集：限制搜索条数（避免风控），详情采集 top 5
        search_limit = min(limit, 8)
        detail_top_n = min(5, search_limit)
        try:
            result = await manager.search_notes_with_details(
                keyword, limit=search_limit, detail_top_n=detail_top_n
            )
            raw_results = result.get("results", [])
            details_collected = result.get("details_collected", 0)
            results: list[TrendingContent] = []
            for raw in raw_results:
                content = self._normalize(raw)
                if content:
                    results.append(content)
            logger.info(
                f"[xiaohongshu] search '{keyword}': "
                f"got {len(raw_results)} raw, {len(results)} normalized, "
                f"{details_collected} details collected"
            )
            return results[:limit]
        except Exception as e:
            logger.error(f"[xiaohongshu] search_trending failed: {e}")
            raise

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """小红书没有"全站热门"API，需通过关键词搜索。

        如果不提供 category，返回空列表。
        """
        if not category:
            logger.info("[xiaohongshu] get_trending requires category (keyword), got empty")
            return []
        return await self.search_trending(category, limit)

    async def close(self) -> None:
        # mcp_manager 的生命周期由 init_mcp_clients 管理，这里不主动关闭
        logger.info("[xiaohongshu] close (no-op, lifecycle managed by mcp_manager)")
