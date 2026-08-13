"""ContentSource 抽象基类 + 统一数据结构。

与 MCPClient 的关系：
- MCPClient 是小红书专用（含 publish/account_info 等发布能力）
- ContentSource 是只读数据源（只搜索，不发布）
- XhsSource 内部委托给 mcp_manager，保留小红书爬取能力
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrendingContent:
    """跨平台统一的爆款内容数据结构。

    所有平台的搜索结果都会归一化成这个结构，
    下游 analyze 节点不关心数据来自哪个平台。
    """

    platform: str          # "reddit" | "hackernews" | "xiaohongshu" | ...
    content_id: str        # 平台内容 ID
    title: str             # 标题（中文译文；原文在 title_original）
    summary: str           # 摘要（中文译文；原文在 summary_original）
    content: str           # 正文（中文译文；原文在 content_original）
    author: str            # 作者
    url: str               # 原文链接
    likes: int = 0         # 点赞/Upvote
    comments: int = 0      # 评论数
    shares: int = 0        # 转发/分享数
    views: int = 0         # 浏览量（部分平台有）
    collects: int = 0      # 收藏数（小红书有，其他平台默认0）
    author_fans: int = 0   # 作者粉丝数（小红书/GitHub有，其他平台默认0）
    cover_img: str = ""    # 封面图 URL（可选）
    published_at: str = "" # ISO8601 发布时间
    tags: list[str] = field(default_factory=list)  # 标签/版块
    title_original: str = ""    # 标题原文（英文）
    summary_original: str = ""  # 摘要原文（英文）
    content_original: str = ""  # 正文原文（英文）
    raw: dict[str, Any] = field(default_factory=dict)  # 原始数据（诊断用）

    def to_dict(self) -> dict[str, Any]:
        """转 dict（供 SSE 传输 / LLM 输入）。"""
        d = {
            "platform": self.platform,
            "content_id": self.content_id,
            "title": self.title,
            "summary": self.summary,
            "content": self.content,
            "author": self.author,
            "url": self.url,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "views": self.views,
            "collects": self.collects,
            "author_fans": self.author_fans,
            "cover_img": self.cover_img,
            "published_at": self.published_at,
            "tags": self.tags,
            "title_original": self.title_original,
            "summary_original": self.summary_original,
        }
        return d


class ContentSource(ABC):
    """多平台内容数据源抽象接口。

    实现类需提供：
    - name: 平台标识（"reddit" / "hackernews" / ...）
    - search_trending: 按关键词搜索热门内容
    - get_trending: 获取平台热门内容（无关键词，按热度）
    - close: 释放资源
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """平台唯一标识，如 "reddit" / "hackernews" / "xiaohongshu"。"""
        raise NotImplementedError

    @abstractmethod
    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """按关键词搜索热门内容。

        Args:
            keyword: 搜索关键词
            limit: 返回条数上限
            time_range: 时间范围 "day" / "week" / "month" / "year" / "all"

        Returns:
            按热度排序的爆款内容列表
        """
        raise NotImplementedError

    @abstractmethod
    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """获取平台热门内容（无关键词，按全局热度）。

        Args:
            category: 分类/subreddit（可选，如 "technology"）
            limit: 返回条数上限

        Returns:
            平台全局热门内容列表
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
        raise NotImplementedError
