"""Xiaohongshu search skill.

Searches Xiaohongshu via MCP Client Manager (plugin + local).
已接通 mcp_manager：plugin client 为主，本地 Playwright 兜底（D17 双模架构）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.agents.skills.base import Skill
from app.agents.skills.permissions import Permission

if TYPE_CHECKING:
    from app.agents.adapters.llm_base import LLMProtocol

logger = logging.getLogger(__name__)


class XhsSearchInput(BaseModel):
    """Input for XHS search skill."""

    keyword: str = Field(..., description="Search keyword")
    limit: int = Field(default=20, ge=1, le=100, description="Number of notes to retrieve")
    account_id: str = Field(default="", description="XHS account ID (optional, for context)")
    min_likes: int = Field(default=100, ge=0, description="最低点赞数阈值，过滤低热度笔记")
    require_cover: bool = Field(default=True, description="是否要求封面图非空")


class XhsNoteSummary(BaseModel):
    """Summary of a Xiaohongshu note."""

    note_id: str
    title: str
    summary: str
    likes: int
    comments: int
    images_base64: list[str] = Field(default_factory=list)


class XhsSearchSkill(Skill):
    """Xiaohongshu search skill.

    Uses MCP Client Manager (plugin primary + local fallback).
    Rate limit 由 MCP 层负责，这里只做一次调用。
    增强逻辑：过滤无效/低热度结果 + 按点赞数降序排序，聚焦热门和趋势话题。
    """

    name = "xhs_search"
    description = "Search Xiaohongshu notes by keyword (filtered by popularity, sorted by likes desc)"
    input_schema = XhsSearchInput
    output_schema = XhsNoteSummary
    required_permissions = [Permission.XHS_SEARCH]

    def __init__(self, llm: LLMProtocol | None = None) -> None:
        super().__init__()
        self.llm = llm

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute search via MCP Client Manager.

        增强逻辑：
        1. 向 MCP 层多抓一些（limit * 2）作为过滤前的候选池
        2. 清洗字段
        3. 过滤无效项：无 note_id、无标题、无封面图（如要求）
        4. 过滤低热度：likes < min_likes
        5. 按 likes 降序排序
        6. 截断到 limit
        """
        in_ = XhsSearchInput.model_validate(inputs)
        client = self._get_xhs_client()
        # 多抓一倍作为过滤候选池，避免过滤后数量不足
        fetch_n = in_.limit * 2
        raw_results = await client.search_notes(in_.keyword, limit=fetch_n)

        # 1. 字段清洗
        cleaned = [self._normalize(r) for r in raw_results]

        # 2. 过滤无效项
        before_invalid = len(cleaned)
        cleaned = [r for r in cleaned if self._is_valid(r, in_.require_cover)]
        dropped_invalid = before_invalid - len(cleaned)

        # 3. 过滤低热度
        before_popularity = len(cleaned)
        cleaned = [r for r in cleaned if r["likes"] >= in_.min_likes]
        dropped_low_likes = before_popularity - len(cleaned)

        # 4. 按点赞数降序排序（热门优先）
        cleaned.sort(key=lambda r: r["likes"], reverse=True)

        # 5. 截断到 limit
        final_results = cleaned[:in_.limit]

        summary = self._summarize_result(
            total_raw=len(raw_results),
            final_count=len(final_results),
            dropped_invalid=dropped_invalid,
            dropped_low_likes=dropped_low_likes,
            min_likes=in_.min_likes,
            first_title=final_results[0]["title"] if final_results else "",
        )
        logger.info(
            f"[skill] xhs_search filter: raw={len(raw_results)} → "
            f"invalid dropped={dropped_invalid} → low_likes dropped={dropped_low_likes} "
            f"→ final={len(final_results)} (min_likes={in_.min_likes})"
        )

        return {
            "results": final_results,
            "summary": summary,
            "count": len(final_results),
            "filter_stats": {
                "raw_count": len(raw_results),
                "dropped_invalid": dropped_invalid,
                "dropped_low_likes": dropped_low_likes,
                "min_likes": in_.min_likes,
            },
        }

    def _get_xhs_client(self):
        """返回全局 MCPClientManager（plugin 主 + local 兜底）。"""
        from app.agents.skills.mcp.xhs_client import mcp_manager
        if mcp_manager._plugin_client is None and mcp_manager._local_client is None:
            raise RuntimeError(
                "MCPClientManager 未初始化：请先在 lifespan 调用 init_mcp_clients()"
            )
        return mcp_manager

    @staticmethod
    def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
        """把 MCP 返回的 raw dict 清洗成稳定的 XhsNoteSummary 兼容结构。"""
        return {
            "note_id": str(raw.get("note_id", "")).strip(),
            "title": str(raw.get("title", "")).strip(),
            "summary": str(raw.get("desc") or raw.get("summary", ""))[:200].strip(),
            "likes": int(raw.get("likes", 0) or 0),
            "comments": int(raw.get("comments", 0) or 0),
            "url": str(raw.get("url", "")).strip(),
            "cover_img": str(raw.get("cover_img", "")).strip(),
            "author": str(raw.get("author", "")).strip(),
        }

    @staticmethod
    def _is_valid(note: dict[str, Any], require_cover: bool) -> bool:
        """判断笔记是否有效：必须有 note_id 和标题，可选要求封面图。

        过滤掉：
        - 无 note_id（无法定位笔记）
        - 标题为空（通常是广告位/推荐位/异常卡片，非真实笔记）
        - 无封面图（如 require_cover=True，无封面图的笔记视觉价值低）
        """
        if not note.get("note_id"):
            return False
        if not note.get("title"):
            return False
        if require_cover and not note.get("cover_img"):
            return False
        return True

    @staticmethod
    def _summarize_result(
        total_raw: int,
        final_count: int,
        dropped_invalid: int,
        dropped_low_likes: int,
        min_likes: int,
        first_title: str,
    ) -> str:
        """D16 trace 文案，含过滤统计。"""
        if final_count == 0:
            return (
                f"搜到 {total_raw} 条，过滤无效 {dropped_invalid} 条、"
                f"低热度(<{min_likes}赞) {dropped_low_likes} 条后无结果，建议降低 min_likes 或换关键词"
            )
        return (
            f"搜到 {total_raw} 条 → 过滤无效 {dropped_invalid} 条 + "
            f"低热度(<{min_likes}赞) {dropped_low_likes} 条 → 保留 {final_count} 条热门笔记，"
            f"首条：{first_title[:40]}"
        )


class XhsSearchSkillV2(Skill):
    """接收外部注入 MCP client 的 search skill（用于测试/自定义路由）。"""

    name = "xhs_search"
    description = "Search Xiaohongshu notes by keyword"
    input_schema = XhsSearchInput
    output_schema = XhsNoteSummary
    required_permissions = [Permission.XHS_SEARCH]

    def __init__(self, mcp_client: Any) -> None:
        super().__init__()
        self.mcp_client = mcp_client

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = XhsSearchInput.model_validate(inputs)
        # MCP client 返回 list[dict]，不是 XhsNoteSummary 对象，不能调 .model_dump()
        raw_results = await self.mcp_client.search_notes(in_.keyword, limit=in_.limit)
        cleaned = [XhsSearchSkill._normalize(r) for r in raw_results]
        return {
            "results": cleaned,
            "count": len(cleaned),
        }
