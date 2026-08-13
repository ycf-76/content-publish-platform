"""GitHub 内容数据源。

用 GitHub Search API 抓热门仓库作为 trending 内容：
- get_trending: 拿当日推送的 stars 最多的仓库（sort=stars, order=desc）
- search_trending: 按关键词搜索仓库（sort=stars）

认证：无 token 时限速 60次/小时（监控10分钟一次足够）；配 token 提升到 5000次/小时
官方文档：https://docs.github.com/en/rest/search

特点：开源项目/技术工具/编程语言热点
局限：偏技术，不适合美妆/穿搭话题
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.agents.skills.sources.base import ContentSource, TrendingContent
from app.agents.skills.sources.translator import translate_batch

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"

# 真实浏览器 UA（GitHub API 要求 User-Agent）
_DEFAULT_UA = "multi-agent-xhs-platform/1.0"


class GitHubSource(ContentSource):
    """GitHub 热门仓库内容源。

    用 Search API 按-stars 排序抓热门项目：
    - get_trending: 当日推送的 stars 最多仓库
    - search_trending: 按关键词搜索 stars 最多仓库
    """

    @property
    def name(self) -> str:
        return "github"

    def __init__(self, token: str = "") -> None:
        """初始化 GitHub 数据源。

        Args:
            token: GitHub Personal Access Token（可选，无 token 时限速 60次/小时）
        """
        self._token = token.strip()
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "User-Agent": _DEFAULT_UA,
                "Accept": "application/vnd.github+json",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers=headers,
            )
        return self._client

    async def _translate_results(self, results: list[TrendingContent]) -> list[TrendingContent]:
        """批量翻译结果（title + summary），原文保留在 *_original 字段。"""
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
        logger.info(f"[github] translated {len(results)} items (zh-CN)")
        return results

    def _normalize_repo(self, repo: dict[str, Any]) -> TrendingContent | None:
        """归一化 GitHub 仓库 JSON 为 TrendingContent。"""
        try:
            repo_id = repo.get("id")
            if repo_id is None:
                return None

            full_name = repo.get("full_name") or ""
            name = repo.get("name") or ""
            html_url = repo.get("html_url") or ""
            if not html_url and full_name:
                html_url = f"https://github.com/{full_name}"

            description = repo.get("description") or ""
            # 摘要用 description，正文用 description + topics
            topics = repo.get("topics") or []
            content_parts = [description]
            if topics:
                content_parts.append("Topics: " + ", ".join(topics))
            content = " | ".join(p for p in content_parts if p)

            summary = description[:200] if description else name[:200]

            owner = repo.get("owner") or {}
            author = owner.get("login") or ""

            stars = int(repo.get("stargazers_count") or 0)
            forks = int(repo.get("forks_count") or 0)
            watchers = int(repo.get("watchers_count") or 0)
            open_issues = int(repo.get("open_issues_count") or 0)

            # 发布时间用 pushed_at（最近推送时间，反映项目活跃度）
            pushed_at = repo.get("pushed_at") or ""
            published_at = ""
            if pushed_at:
                try:
                    # GitHub 返回 ISO8601 带Z
                    published_at = pushed_at.replace("Z", "+00:00")
                except Exception:
                    published_at = ""

            language = repo.get("language") or ""

            return TrendingContent(
                platform="github",
                content_id=str(repo_id),
                title=name if not description else f"{name}: {description[:80]}",
                summary=summary,
                content=content,
                author=author,
                url=html_url,
                likes=stars,           # stars 作为点赞数
                comments=open_issues,  # open issues 作为评论数
                shares=forks,          # forks 作为分享数
                views=watchers,        # watchers 作为浏览量
                cover_img="",          # GitHub 仓库无封面图
                published_at=published_at,
                tags=topics + ([language] if language else []),
                title_original=name,
                summary_original=summary,
                content_original=content,
                raw={
                    "full_name": full_name,
                    "language": language,
                    "topics": topics,
                },
            )
        except Exception as e:
            logger.warning(f"[github] normalize repo failed: {e}")
            return None

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """按关键词搜索 stars 最多的仓库。

        Args:
            keyword: 搜索关键词
            limit: 返回条数
            time_range: 时间范围（created:>YYYY-MM-DD 过滤）
        """
        if not keyword.strip():
            return await self.get_trending(limit=limit)

        client = await self._ensure_client()

        # 时间范围转 GitHub created 过滤
        now = datetime.now(timezone.utc)
        time_map = {
            "day": timedelta(days=1),
            "week": timedelta(days=7),
            "month": timedelta(days=30),
            "year": timedelta(days=365),
            "all": None,
        }
        delta = time_map.get(time_range)
        date_filter = ""
        if delta is not None:
            since = (now - delta).strftime("%Y-%m-%d")
            date_filter = f" created:>={since}"

        # q 语法：关键词 in:name,description + 时间过滤
        query = f"{keyword} in:name,description,readme{date_filter}"

        params: dict[str, Any] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(limit, 30),
        }

        try:
            resp = await client.get(f"{_GITHUB_API_BASE}/search/repositories", params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])

            results: list[TrendingContent] = []
            for repo in items:
                content = self._normalize_repo(repo)
                if content:
                    results.append(content)

            logger.info(
                f"[github] search '{keyword}' t={time_range}: "
                f"got {len(items)} items, {len(results)} normalized"
            )
            sliced = results[:limit]
            return await self._translate_results(sliced)
        except Exception as e:
            logger.error(f"[github] search_trending failed: {e}")
            return []

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """获取当日热门仓库（按 stars 排序，只取当日 pushed 的）。

        Args:
            category: 可选语言过滤（如 "python" / "javascript"）
            limit: 返回条数上限
        """
        client = await self._ensure_client()

        # 当日推送的仓库（pushed:>=YYYY-MM-DD）
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        # category 作为语言过滤
        lang_filter = f" language:{category}" if category else ""
        query = f"stars:>50 pushed:>={today}{lang_filter}"

        params: dict[str, Any] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(limit, 30),
        }

        try:
            resp = await client.get(f"{_GITHUB_API_BASE}/search/repositories", params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])

            results: list[TrendingContent] = []
            for repo in items:
                content = self._normalize_repo(repo)
                if content:
                    results.append(content)

            logger.info(
                f"[github] get_trending lang={category or 'all'}: "
                f"got {len(items)} items, {len(results)} normalized"
            )
            sliced = results[:limit]
            return await self._translate_results(sliced)
        except Exception as e:
            logger.error(f"[github] get_trending failed: {e}")
            return []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("[github] closed")
