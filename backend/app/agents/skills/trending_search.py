"""Trending search skill（多平台版本）。

替代 XhsSearchSkill，支持从多个平台（Reddit / HackerNews / 小红书）搜索热门内容。
返回统一的 TrendingContent 数据结构，下游 analyze 节点不关心数据来自哪个平台。

设计：
- 通过 SourceManager 获取 ContentSource
- 默认平台由 settings.default_source_platform 决定
- LLM 可以通过 platform 参数指定平台（如 "reddit" / "hackernews"）
- 过滤逻辑：按互动量（likes + comments）过滤低热度内容
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


class TrendingSearchInput(BaseModel):
    """Input for trending search skill."""

    keyword: str = Field(..., description="Search keyword / 主题关键词")
    limit: int = Field(default=20, ge=1, le=100, description="返回条数上限")
    platform: str = Field(
        default="",
        description="平台名（空 = 默认平台）：reddit / hackernews / xiaohongshu",
    )
    time_range: str = Field(
        default="week",
        description="时间范围：day / week / month / year / all",
    )
    min_interactions: int = Field(
        default=10,
        ge=0,
        description="最低互动量阈值（likes + comments），过滤低热度内容",
    )


class TrendingSearchSkill(Skill):
    """多平台热门内容搜索 skill。

    通过 SourceManager 分发到对应平台的 ContentSource。
    自动过滤低互动量内容，按互动量降序排序。
    """

    name = "trending_search"
    description = (
        "Search trending content from multiple platforms "
        "(Reddit / HackerNews / Xiaohongshu). "
        "Returns unified TrendingContent list sorted by interactions."
    )
    input_schema = TrendingSearchInput
    required_permissions = [Permission.XHS_SEARCH]  # 复用搜索权限

    def __init__(self, llm: LLMProtocol | None = None) -> None:
        super().__init__()
        self.llm = llm

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行多平台综合搜索。

        流程：
        1. platform 参数为空时，并发搜索所有已注册平台（综合返回，标注来源）
           platform 参数非空时，只搜指定平台
        2. 合并结果，过滤低互动量，按互动量降序排序
        3. 截断到 limit
        4. 空结果 fallback：对默认平台调 get_trending（热门榜兜底），让工作流能继续跑
           disable_fallback=True 时跳过此步（供上层 graph.py 自行控制兜底时机）
        """
        in_ = TrendingSearchInput.model_validate(inputs)
        disable_fallback = inputs.get("disable_fallback", False)

        # platform 为空 → 多平台综合搜索；非空 → 单平台搜索
        if in_.platform:
            raw_results, searched_platforms = await self._search_single(
                in_.platform, in_.keyword, in_.limit * 2, in_.time_range
            )
        else:
            raw_results, searched_platforms = await self._search_all_platforms(
                in_.keyword, in_.limit * 2, in_.time_range
            )

        # 转成 dict 并计算互动量
        items: list[dict[str, Any]] = []
        for content in raw_results:
            d = content.to_dict()
            d["interactions"] = d["likes"] + d["comments"] + d["shares"]
            items.append(d)

        # 过滤低互动量
        before = len(items)
        items = [it for it in items if it["interactions"] >= in_.min_interactions]
        dropped_low = before - len(items)

        # 按互动量降序排序
        items.sort(key=lambda x: x["interactions"], reverse=True)
        final_results = items[:in_.limit]

        # ===== 空结果 fallback：热门榜兜底 =====
        # 所有关键词搜索都 0 结果时，对【用户指定的平台】调 get_trending，
        # 让工作流能继续跑（analyze/image_gen 有素材可用）
        # 红线：只 fallback 到用户指定的平台，绝不偷偷切到默认平台（小红书）。
        # disable_fallback=True 时跳过（供上层 graph.py 先做翻译重试，再自行兜底）
        fallback_used = False
        if not final_results and not disable_fallback:
            final_results, fallback_platform = await self._fallback_to_trending(
                in_.platform, in_.limit, in_.min_interactions
            )
            fallback_used = bool(final_results)
            if fallback_used:
                logger.info(
                    f"[skill] trending_search: keyword '{in_.keyword}' 无结果，"
                    f"已用 {fallback_platform} 热门榜兜底，返回 {len(final_results)} 条"
                )

        summary = self._summarize_result_multi(
            platforms=searched_platforms,
            total_raw=len(raw_results),
            final_count=len(final_results),
            dropped_low=dropped_low,
            min_interactions=in_.min_interactions,
            first_title=final_results[0]["title"] if final_results else "",
            fallback_used=fallback_used,
            keyword=in_.keyword,
        )
        logger.info(
            f"[skill] trending_search platforms={searched_platforms}: "
            f"raw={len(raw_results)} → low_interactions dropped={dropped_low} "
            f"→ final={len(final_results)} (min_interactions={in_.min_interactions})"
            + (" [fallback=trending]" if fallback_used else "")
        )

        return {
            "results": final_results,
            "summary": summary,
            "count": len(final_results),
            "filter_stats": {
                "raw_count": len(raw_results),
                "dropped_low_interactions": dropped_low,
                "min_interactions": in_.min_interactions,
                "searched_platforms": searched_platforms,
                "fallback_used": fallback_used,
            },
            "platform": ",".join(searched_platforms) if searched_platforms else "none",
        }

    async def _search_single(
        self,
        platform: str,
        keyword: str,
        limit: int,
        time_range: str,
    ) -> tuple[list, list[str]]:
        """单平台搜索。返回 (results, [platform_name])。"""
        source = self._get_source(platform)
        if source is None:
            available = self._list_platforms()
            logger.warning(
                f"[skill] platform '{platform}' not available, "
                f"registered: {available}"
            )
            return [], []
        try:
            results = await source.search_trending(keyword, limit, time_range)
        except Exception as e:
            logger.error(f"[skill] trending_search failed on {source.name}: {e}")
            # 向上抛，让 fetch_and_save 能透传真实错误给前端
            raise
        return results, [source.name]

    async def _search_all_platforms(
        self,
        keyword: str,
        limit: int,
        time_range: str,
    ) -> tuple[list, list[str]]:
        """并发搜索所有已注册平台，合并结果。

        每个平台各抓 limit 条，合并后由上层统一排序截断。
        单平台失败不影响其他平台。
        """
        import asyncio

        from app.agents.skills.sources.manager import source_manager

        platforms = source_manager.list_platforms()
        if not platforms:
            logger.warning("[skill] no content source registered")
            return [], []

        # 全网搜索排除小红书：小红书需 Playwright + 登录态，易触发风控，
        # 由用户显式选择 xiaohongshu 平台时单独搜索，不混入全网并发
        platforms = [p for p in platforms if p != "xiaohongshu"]
        if not platforms:
            logger.warning("[skill] no content source after excluding xiaohongshu")
            return [], []

        async def _search_one(plat: str) -> tuple[list, str]:
            src = source_manager.get_source(plat)
            if src is None:
                return [], plat
            try:
                # 每个平台各抓 limit 条（不多抓，避免单个平台占用过多配额）
                r = await src.search_trending(keyword, limit, time_range)
                return r, plat
            except Exception as e:
                logger.error(f"[skill] trending_search failed on {plat}: {e}")
                return [], plat

        # 并发搜索所有平台
        # return_exceptions=True：单平台异常/超时不拖累其他平台
        tasks = [_search_one(p) for p in platforms]
        results_per_platform = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list = []
        searched: list[str] = []
        for item in results_per_platform:
            # gather return_exceptions=True 时，异常对象会出现在结果列表里
            if isinstance(item, Exception):
                logger.warning(f"[skill] multi-platform gather: a platform failed: {item}")
                continue
            r, plat = item
            searched.append(plat)
            all_results.extend(r)

        logger.info(
            f"[skill] multi-platform search '{keyword}': "
            f"platforms={searched}, total={len(all_results)}"
        )
        return all_results, searched

    async def _fallback_to_trending(
        self,
        platform: str,
        limit: int,
        min_interactions: int,
    ) -> tuple[list[dict[str, Any]], str]:
        """热门榜兜底：关键词搜索全空时，对【用户指定平台】调 get_trending。

        红线：只 fallback 到用户指定的平台，绝不偷偷切到默认平台（小红书）。
        - platform 非空：用该平台的热门榜（用户指定 HackerNews 就用 HackerNews）
        - platform 为空（全网搜索）：用默认平台兜底（全网本就含小红书）
        返回 (final_results_dict_list, platform_name)。
        """
        source = self._get_source(platform)
        if source is None:
            return [], "none"

        try:
            raw = await source.get_trending(limit=limit * 2)
        except Exception as e:
            logger.error(f"[skill] fallback get_trending failed on {source.name}: {e}")
            return [], source.name

        items: list[dict[str, Any]] = []
        for content in raw:
            d = content.to_dict()
            d["interactions"] = d["likes"] + d["comments"] + d["shares"]
            items.append(d)

        items = [it for it in items if it["interactions"] >= min_interactions]
        items.sort(key=lambda x: x["interactions"], reverse=True)
        return items[:limit], source.name

    def _get_source(self, platform: str):
        """获取 ContentSource。"""
        from app.agents.skills.sources.manager import source_manager

        if platform:
            return source_manager.get_source(platform)
        return source_manager.get_default()

    def _list_platforms(self) -> list[str]:
        from app.agents.skills.sources.manager import source_manager
        return source_manager.list_platforms()

    @staticmethod
    def _summarize_result_multi(
        platforms: list[str],
        total_raw: int,
        final_count: int,
        dropped_low: int,
        min_interactions: int,
        first_title: str,
        fallback_used: bool,
        keyword: str,
    ) -> str:
        """多平台搜索结果摘要。"""
        platforms_str = "+".join(platforms) if platforms else "none"
        if final_count == 0:
            return (
                f"[{platforms_str}] 关键词 '{keyword}' 搜到 {total_raw} 条，"
                f"过滤低互动(<{min_interactions}) {dropped_low} 条后无结果"
            )
        if fallback_used:
            return (
                f"[{platforms_str}] 关键词 '{keyword}' 无结果，"
                f"已用 {platforms_str} 热门榜兜底，返回 {final_count} 条，"
                f"首条：{first_title[:40]}"
            )
        return (
            f"[{platforms_str}] 关键词 '{keyword}' 搜到 {total_raw} 条 → "
            f"过滤低互动(<{min_interactions}) {dropped_low} 条 → "
            f"保留 {final_count} 条热门内容，首条：{first_title[:40]}"
        )


# ===== 兼容层：保留 XhsSearchSkill 名称，内部委托给 TrendingSearchSkill =====
# 这样 graph.py / factory.py 里引用 XhsSearchSkill 的代码不用改太多

class XhsSearchSkill(TrendingSearchSkill):
    """兼容包装：XhsSearchSkill 现在委托给多平台搜索。

    保留旧名称避免破坏现有 import，但行为已改为多平台。
    默认平台由 settings.default_source_platform 决定。
    """

    name = "xhs_search"  # 保留旧名字，LLM prompt 里还是叫 xhs_search
    description = (
        "Search trending content from multiple platforms. "
        "Legacy name 'xhs_search' kept for compatibility."
    )
