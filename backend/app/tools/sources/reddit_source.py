"""Reddit 内容数据源。

Reddit API v2 认证方式（OAuth2 Client Credentials）：
- 个人脚本：用 script app 类型，username + password + client_id + client_secret
- 只读公开数据：用 client_credentials（不需要用户登录），但只能拿热门，搜索需要 user OAuth
- 推荐：用 personal use script，最简单

API 端点：
- 搜索：GET /search?q={keyword}&sort=top&t={time_range}&limit={limit}
- 版块热门：GET /r/{subreddit}/hot
- 全站热门：GET /r/all/top

频率限制：Reddit OAuth 每分钟 60 次请求（个人脚本足够）。
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.tools.sources.base import ContentSource, TrendingContent

logger = logging.getLogger(__name__)

_REDDIT_API_BASE = "https://oauth.reddit.com"
_REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_REDDIT_USER_AGENT = "multi-agent-xhs-platform/1.0 (research; +github.com/local)"


class RedditSource(ContentSource):
    """Reddit 内容源（OAuth2 personal use script）。

    认证流程：
    1. 用 client_id + client_secret + username + password 换 access_token
    2. 带 token 请求 /search 或 /r/{sub}/hot
    3. token 过期自动刷新
    """

    @property
    def name(self) -> str:
        return "reddit"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str = "",
        password: str = "",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": _REDDIT_USER_AGENT},
            )
        return self._client

    async def _ensure_token(self) -> None:
        """获取或刷新 access_token。"""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return  # 还没过期

        client = await self._ensure_client()

        if self._username and self._password:
            # script app：用户名密码模式（能搜索）
            data = {
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
            }
        else:
            # client_credentials 模式（只能拿热门，不能搜索）
            data = {"grant_type": "client_credentials"}

        try:
            resp = await client.post(
                _REDDIT_TOKEN_URL,
                data=data,
                auth=(self._client_id, self._client_secret),
            )
            resp.raise_for_status()
            token_data = resp.json()
            if "access_token" not in token_data:
                raise RuntimeError(f"Reddit token response missing access_token: {token_data}")

            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self._token_expires_at = time.time() + expires_in
            logger.info(
                f"[reddit] token acquired, expires in {expires_in}s, "
                f"scope={token_data.get('scope', '')}"
            )
        except Exception as e:
            logger.error(f"[reddit] failed to acquire token: {e}")
            raise RuntimeError(f"Reddit auth failed: {e}") from e

    async def _api_get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """带 token 的 GET 请求。"""
        await self._ensure_token()
        client = await self._ensure_client()

        headers = {"Authorization": f"Bearer {self._access_token}"}
        url = f"{_REDDIT_API_BASE}{path}"

        try:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 401:
                # token 过期，刷新后重试一次
                logger.warning("[reddit] 401, refreshing token")
                self._access_token = None
                await self._ensure_token()
                headers = {"Authorization": f"Bearer {self._access_token}"}
                resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"[reddit] API error {e.response.status_code}: {e.response.text[:200]}")
            raise
        except Exception as e:
            logger.error(f"[reddit] API request failed: {e}")
            raise

    def _normalize(self, child: dict[str, Any]) -> TrendingContent | None:
        """把 Reddit post 结构归一化成 TrendingContent。"""
        try:
            d = child["data"]
            post_id = d.get("id") or d.get("name") or ""
            if not post_id:
                return None

            title = (d.get("title") or "").strip()
            selftext = (d.get("selftext") or "").strip()
            subreddit = d.get("subreddit") or ""
            author = d.get("author") or ""
            permalink = d.get("permalink") or ""
            url = f"https://www.reddit.com{permalink}" if permalink else d.get("url", "")
            score = int(d.get("score") or 0)
            num_comments = int(d.get("num_comments") or 0)
            upvote_ratio = float(d.get("upvote_ratio") or 0)
            created_utc = float(d.get("created_utc") or 0)
            thumbnail = d.get("thumbnail") or ""
            # 只取真实图片 URL（非 "self"/"default"/"nsfw"/"spoiler"）
            if thumbnail in ("self", "default", "nsfw", "spoiler", ""):
                thumbnail = ""
            flair = d.get("link_flair_text") or ""

            # 摘要：优先 selftext 前 200 字，没有则用 title
            summary = selftext[:200] if selftext else title[:200]

            # 发布时间 ISO8601
            published_at = ""
            if created_utc:
                from datetime import datetime, timezone
                published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

            tags = [f"r/{subreddit}"] if subreddit else []
            if flair:
                tags.append(flair)

            return TrendingContent(
                platform="reddit",
                content_id=post_id,
                title=title,
                summary=summary,
                content=selftext,
                author=f"u/{author}",
                url=url,
                likes=score,
                comments=num_comments,
                shares=0,  # Reddit 没有"转发"概念
                views=0,
                cover_img=thumbnail,
                published_at=published_at,
                tags=tags,
                raw={
                    "subreddit": subreddit,
                    "upvote_ratio": upvote_ratio,
                    "over_18": d.get("over_18", False),
                    "is_video": d.get("is_video", False),
                },
            )
        except Exception as e:
            logger.warning(f"[reddit] normalize failed: {e}")
            return None

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """按关键词搜索 Reddit 热门帖子。

        Args:
            keyword: 搜索关键词
            limit: 返回条数（max 100）
            time_range: "hour" / "day" / "week" / "month" / "year" / "all"
        """
        if not self._username:
            logger.warning(
                "[reddit] search_trending requires username/password OAuth, "
                "client_credentials mode can only use get_trending"
            )
            return []

        params = {
            "q": keyword,
            "sort": "top",          # 按热度排序
            "t": time_range,        # 时间范围
            "limit": min(limit, 100),
            "type": "link",         # 只要链接帖（过滤纯文字讨论）
        }

        try:
            data = await self._api_get("/search", params=params)
            children = data.get("data", {}).get("children", [])
            results: list[TrendingContent] = []
            for child in children:
                content = self._normalize(child)
                if content:
                    results.append(content)

            logger.info(
                f"[reddit] search '{keyword}' t={time_range}: "
                f"got {len(children)} raw, {len(results)} normalized"
            )
            return results[:limit]
        except Exception as e:
            logger.error(f"[reddit] search_trending failed: {e}")
            return []

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """获取 Reddit 热门内容（无关键词）。

        Args:
            category: subreddit 名（空字符串表示全站热门）
            limit: 返回条数
        """
        path = f"/r/{category}/top" if category else "/r/all/top"
        params = {
            "t": "day",             # 今日热门
            "limit": min(limit, 100),
        }

        try:
            data = await self._api_get(path, params=params)
            children = data.get("data", {}).get("children", [])
            results: list[TrendingContent] = []
            for child in children:
                content = self._normalize(child)
                if content:
                    results.append(content)

            logger.info(
                f"[reddit] get_trending category='{category}': "
                f"got {len(children)} raw, {len(results)} normalized"
            )
            return results[:limit]
        except Exception as e:
            logger.error(f"[reddit] get_trending failed: {e}")
            return []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._access_token = None
        logger.info("[reddit] closed")
