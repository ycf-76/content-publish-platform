"""SourceManager — 多平台内容源注册表。

职责：
1. 按 platform 名分发到对应的 ContentSource
2. 启动时根据配置初始化启用的 source
3. 提供 list_platforms() 供前端展示可用平台

设计：
- 模块级单例 source_manager（类似 mcp_manager）
- init_sources() 在 lifespan 启动时调用
- 工作流通过 get_source(platform) 获取实例
"""

from __future__ import annotations

import logging
from typing import Any

from app.tools.sources.base import ContentSource, TrendingContent

logger = logging.getLogger(__name__)


class SourceManager:
    """多平台内容源管理器。

    用法：
        from app.tools.sources.manager import source_manager
        source = source_manager.get_source("reddit")
        results = await source.search_trending("AI", limit=20)
    """

    def __init__(self) -> None:
        self._sources: dict[str, ContentSource] = {}
        self._default_platform: str = "reddit"

    def register(self, source: ContentSource) -> None:
        """注册一个内容源。"""
        self._sources[source.name] = source
        logger.info(f"[sources] registered platform: {source.name}")

    def get_source(self, platform: str) -> ContentSource | None:
        """按平台名获取 source。"""
        return self._sources.get(platform)

    def get_default(self) -> ContentSource | None:
        """获取默认平台 source。"""
        return self._sources.get(self._default_platform)

    def set_default(self, platform: str) -> None:
        """设置默认平台。"""
        if platform not in self._sources:
            logger.warning(f"[sources] cannot set default to {platform}: not registered")
            return
        self._default_platform = platform
        logger.info(f"[sources] default platform set to: {platform}")

    def list_platforms(self) -> list[str]:
        """列出所有已注册的平台。"""
        return list(self._sources.keys())

    def is_available(self, platform: str) -> bool:
        return platform in self._sources

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        platform: str = "",
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """便捷方法：按平台搜索，platform 为空时用默认平台。

        Args:
            keyword: 搜索关键词
            limit: 返回条数
            platform: 平台名（空字符串 = 默认平台）
            time_range: 时间范围
        """
        source = self.get_source(platform) if platform else self.get_default()
        if source is None:
            logger.error(
                f"[sources] platform '{platform or self._default_platform}' not available. "
                f"Registered: {self.list_platforms()}"
            )
            return []
        return await source.search_trending(keyword, limit, time_range)

    async def close_all(self) -> None:
        """关闭所有 source（应用关闭时调用）。"""
        for name, source in self._sources.items():
            try:
                await source.close()
            except Exception as e:
                logger.warning(f"[sources] close {name} failed: {e}")
        self._sources.clear()
        logger.info("[sources] all sources closed")


# 模块级单例
source_manager = SourceManager()


async def init_sources() -> None:
    """根据配置初始化内容源。

    在应用 lifespan 启动时调用。
    读取 settings 判断哪些平台启用，创建实例并注册。
    """
    from app.config import get_settings

    settings = get_settings()

    # 1. Tavily 全网搜索（需 API Key，优先注册以便全网搜索覆盖面）
    tavily_instance = None
    if settings.tavily_api_key:
        try:
            from app.tools.sources.tavily_source import TavilySource

            tavily_instance = TavilySource(api_key=settings.tavily_api_key)
            source_manager.register(tavily_instance)
        except Exception as e:
            logger.error(f"[sources] init TavilySource failed: {e}")
    else:
        logger.info("[sources] Tavily disabled (TAVILY_API_KEY not set)")

    # 1.1 Tavily Site Search 平台群（复用同一 API Key，零风控）
    #     通过 site:domain 限定搜索范围，走搜索引擎而非直接爬取
    #     注意：小红书/抖音/Instagram 对搜索引擎做了反索引，site:domain 搜不到内容
    #     因此用替代策略：搜全网 + 关键词限定，由 AI 改写为目标平台风格
    if tavily_instance is not None:
        try:
            from app.tools.sources.tavily_site_source import TavilySiteSource

            # --- 搜索引擎可索引的中文平台（效果可靠）---
            zhihu = TavilySiteSource("zhihu", "zhihu.com", tavily_instance)
            source_manager.register(zhihu)

            weibo = TavilySiteSource("weibo", "weibo.com", tavily_instance)
            source_manager.register(weibo)

            bilibili = TavilySiteSource("bilibili", "bilibili.com", tavily_instance)
            source_manager.register(bilibili)

            # --- 小红书替代：搜全网穿搭/美妆内容，AI 改写为小红书风格 ---
            #     xiaohongshu.com 对搜索引擎屏蔽，site: 搜不到笔记
            #     改搜 163.com / sohu.com / sina.com.cn 等新闻门户的生活方式频道
            #     这些站点有大量穿搭/美妆/家居内容，且搜索引擎索引完整
            xhs_alt = TavilySiteSource("xiaohongshu_web", "163.com sohu.com sina.com.cn", tavily_instance)
            source_manager.register(xhs_alt)

            # --- 抖音替代：搜 36kr.com / ifanr.com 等科技媒体的短视频/热点报道 ---
            douyin_alt = TavilySiteSource("douyin", "36kr.com ifanr.com jiemian.com", tavily_instance)
            source_manager.register(douyin_alt)

            # --- 海外生活方式平台 ---
            pinterest = TavilySiteSource("pinterest", "pinterest.com", tavily_instance)
            source_manager.register(pinterest)

            # Instagram 对搜索引擎屏蔽，改搜海外时尚媒体
            insta_alt = TavilySiteSource("instagram", "vogue.com elle.com cosmopolitan.com", tavily_instance)
            source_manager.register(insta_alt)

            logger.info(
                f"[sources] Tavily site search platforms registered: "
                f"zhihu, weibo, bilibili, xiaohongshu_web(alt), douyin(alt), pinterest, instagram(alt)"
            )
        except Exception as e:
            logger.error(f"[sources] init TavilySiteSource platforms failed: {e}")

    # 2. Reddit（需 client_id + client_secret）
    if settings.reddit_client_id and settings.reddit_client_secret:
        try:
            from app.tools.sources.reddit_source import RedditSource

            reddit = RedditSource(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                username=settings.reddit_username or "",
                password=settings.reddit_password or "",
            )
            source_manager.register(reddit)
        except Exception as e:
            logger.error(f"[sources] init RedditSource failed: {e}")
    else:
        logger.info("[sources] Reddit disabled (REDDIT_CLIENT_ID/SECRET not set)")

    # 3. HackerNews（零认证，默认启用）
    try:
        from app.tools.sources.hackernews_source import HackerNewsSource

        hn = HackerNewsSource()
        source_manager.register(hn)
    except Exception as e:
        logger.error(f"[sources] init HackerNewsSource failed: {e}")

    # 4. GitHub（开源项目/技术工具热点，无 token 也可用，配 token 提升限速）
    try:
        from app.tools.sources.github_source import GitHubSource

        gh = GitHubSource(token=settings.github_token)
        source_manager.register(gh)
    except Exception as e:
        logger.error(f"[sources] init GitHubSource failed: {e}")

    # 5. 内置中文话题库（零网络依赖，覆盖小红书常见类目）
    #    作为兜底数据源，确保中文生活方式关键词总能搜到内容
    try:
        from app.tools.sources.builtin_source import BuiltinSource

        builtin = BuiltinSource()
        source_manager.register(builtin)
    except Exception as e:
        logger.error(f"[sources] init BuiltinSource failed: {e}")

    # 6. 小红书（保留，默认不启用，需显式配置）
    if settings.xhs_source_enabled:
        try:
            from app.tools.sources.xhs_source import XhsSource

            xhs = XhsSource()
            source_manager.register(xhs)
        except Exception as e:
            logger.error(f"[sources] init XhsSource failed: {e}")

    # 设置默认平台
    # 优先用配置的 default_source_platform
    # 没配置时优先 tavily（全网搜索覆盖面最广）→ builtin（中文话题）
    default = settings.default_source_platform or "tavily"
    if source_manager.is_available(default):
        source_manager.set_default(default)
    elif source_manager.is_available("tavily"):
        source_manager.set_default("tavily")
    elif source_manager.is_available("builtin"):
        source_manager.set_default("builtin")
    elif source_manager.is_available("hackernews"):
        source_manager.set_default("hackernews")
    elif source_manager.list_platforms():
        # 退化到第一个可用平台
        first = source_manager.list_platforms()[0]
        source_manager.set_default(first)

    logger.info(
        f"[sources] init complete. "
        f"platforms={source_manager.list_platforms()}, "
        f"default={source_manager._default_platform}"
    )