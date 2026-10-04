"""抖音 Spider：爬取用户主页全部作品数据。

使用 Scrapling StealthySession（反检测浏览器）。
抖音页面高度动态化，需要等待 JS 渲染完成。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.platform_spider.base import BasePlatformSpider

logger = logging.getLogger(__name__)

DOUYIN_USER_HOME = "https://www.douyin.com/user/{uid}"


class DouyinSpider(BasePlatformSpider):
    """抖音用户作品 Spider。"""

    platform = "douyin"

    concurrent_requests = 2
    request_delay = 3.0

    def start(self) -> list[dict[str, Any]]:
        """爬取抖音用户主页全部作品。"""
        try:
            from scrapling.fetchers import StealthyFetcher
        except ImportError:
            logger.error("Scrapling not installed. Run: pip install scrapling")
            return []

        if not self.platform_uid:
            logger.warning("DouyinSpider: platform_uid is empty, cannot crawl")
            return []

        items: list[dict[str, Any]] = []
        home_url = DOUYIN_USER_HOME.format(uid=self.platform_uid)

        logger.info(f"DouyinSpider: fetching user home {home_url}")

        try:
            kwargs: dict[str, Any] = {
                "headless": True,
                "network_idle": True,
                "timeout": 60000,
            }
            if self.cookies:
                cookie_list = []
                for name, val in self.cookies.items():
                    if isinstance(val, dict):
                        cookie_list.append({"name": name, "value": val.get("value", "")})
                    else:
                        cookie_list.append({"name": name, "value": str(val)})
                if cookie_list:
                    kwargs["cookies"] = cookie_list

            page = StealthyFetcher.fetch(home_url, **kwargs)
        except Exception as e:
            logger.error(f"DouyinSpider: failed to fetch user home: {e}")
            return []

        video_cards = page.css(
            "[class*='video-card'], [class*='aweme-card'], "
            "a[href*='/video/'], a[href*='/note/']"
        )

        logger.info(f"DouyinSpider: found {len(video_cards)} video cards on user home")

        for card in video_cards:
            try:
                video_url = ""
                links = card.css("a[href]")
                link = links[0] if links else None
                if link:
                    video_url = link.attrib.get("href", "")
                if not video_url and hasattr(card, "attrib"):
                    href = card.attrib.get("href", "")
                    if href:
                        video_url = href

                if not video_url:
                    continue

                if video_url.startswith("/"):
                    video_url = f"https://www.douyin.com{video_url}"

                aweme_id = self._extract_aweme_id(video_url)
                if not aweme_id:
                    continue

                item = {
                    "note_id": aweme_id,
                    "title": self._safe_text(card, "[class*='title'], [class*='desc']"),
                    "cover_img_url": self._safe_text(card, "img", attr="src"),
                    "platform": "douyin",
                    "likes": 0,
                    "collects": 0,
                    "comments": 0,
                    "shares": 0,
                    "tags": [],
                    "content_text": "",
                    "image_urls": [],
                }

                like_text = self._safe_text(card, "[class*='like-count'], [class*='digg']")
                item["likes"] = self._parse_count(like_text)

                items.append(item)

            except Exception as e:
                logger.warning(f"DouyinSpider: error parsing video card: {e}")
                continue

        logger.info(f"DouyinSpider: total {len(items)} videos from user home")

        for i, item in enumerate(items):
            if i > 0:
                time.sleep(self.request_delay)
            try:
                detail = self._fetch_video_detail(item["note_id"], StealthyFetcher, kwargs)
                if detail:
                    item.update(detail)
            except Exception as e:
                logger.warning(f"DouyinSpider: detail fetch failed for {item['note_id']}: {e}")

        return items

    def _fetch_video_detail(
        self, aweme_id: str, fetcher_cls: Any, base_kwargs: dict
    ) -> dict[str, Any] | None:
        """爬取单条视频详情页。"""
        url = f"https://www.douyin.com/video/{aweme_id}"
        try:
            page = fetcher_cls.fetch(url, **base_kwargs)
        except Exception as e:
            logger.warning(f"DouyinSpider: detail page fetch failed: {e}")
            return None

        detail: dict[str, Any] = {}

        desc_text = self._safe_text(page, "[class*='desc'], [class*='description']")
        if desc_text:
            detail["content_text"] = desc_text

        title_text = self._safe_text(page, "[class*='title']")
        if title_text:
            detail["title"] = title_text

        like_text = self._safe_text(page, "[class*='like-count'], [class*='digg-count']")
        if like_text:
            detail["likes"] = self._parse_count(like_text)

        collect_text = self._safe_text(page, "[class*='collect-count'], [class*='collect']")
        if collect_text:
            detail["collects"] = self._parse_count(collect_text)

        comment_text = self._safe_text(page, "[class*='comment-count']")
        if comment_text:
            detail["comments"] = self._parse_count(comment_text)

        tags = []
        tag_els = page.css("[class*='tag'], [class*='hash-tag']")
        for t in tag_els:
            try:
                txt = t.text.strip() if hasattr(t, "text") else ""
                if txt:
                    tags.append(txt)
            except Exception:
                continue
        if tags:
            detail["tags"] = tags

        return detail

    @staticmethod
    def _extract_aweme_id(url: str) -> str:
        """从 URL 中提取 aweme_id。"""
        patterns = [
            r'douyin\.com/video/(\d+)',
            r'douyin\.com/note/(\d+)',
        ]
        for pat in patterns:
            m = re.search(pat, url)
            if m:
                return m.group(1)
        return ""