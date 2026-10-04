"""B站 Spider：爬取用户主页全部投稿数据。

B站 API 相对公开，使用 Scrapling FetcherSession（轻量 HTTP）即可。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.platform_spider.base import BasePlatformSpider

logger = logging.getLogger(__name__)

BILIBILI_API_SPACE = "https://api.bilibili.com/x/space/wbi/arc/search"
BILIBILI_API_VIDEO_INFO = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_USER_HOME = "https://space.bilibili.com/{uid}"


class BilibiliSpider(BasePlatformSpider):
    """B站用户投稿 Spider。

    优先使用 B站公开 API（无需登录），API 失败时降级为页面爬取。
    """

    platform = "bilibili"

    concurrent_requests = 4
    request_delay = 1.0

    def start(self) -> list[dict[str, Any]]:
        """爬取B站用户主页全部投稿。"""
        if not self.platform_uid:
            logger.warning("BilibiliSpider: platform_uid is empty, cannot crawl")
            return []

        items = self._crawl_via_api()
        if items:
            return items

        logger.info("BilibiliSpider: API crawl returned empty, falling back to page crawl")
        return self._crawl_via_page()

    def _crawl_via_api(self) -> list[dict[str, Any]]:
        """通过 B站公开 API 爬取。"""
        items: list[dict[str, Any]] = []
        pn = 1
        ps = 30

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Referer": f"https://space.bilibili.com/{self.platform_uid}",
        }

        cookie_str = ""
        if self.cookies:
            parts = []
            for name, val in self.cookies.items():
                if isinstance(val, dict):
                    parts.append(f"{name}={val.get('value', '')}")
                else:
                    parts.append(f"{name}={val}")
            cookie_str = "; ".join(parts)
            headers["Cookie"] = cookie_str

        while True:
            params = {
                "mid": self.platform_uid,
                "pn": pn,
                "ps": ps,
                "order": "pubdate",
            }

            try:
                resp = httpx.get(
                    BILIBILI_API_SPACE,
                    params=params,
                    headers=headers,
                    timeout=30.0,
                )
                data = resp.json()
            except Exception as e:
                logger.warning(f"BilibiliSpider: API request failed (pn={pn}): {e}")
                break

            vlist = data.get("data", {}).get("list", {}).get("vlist", [])
            if not vlist:
                break

            for v in vlist:
                item = {
                    "note_id": v.get("bvid", ""),
                    "title": v.get("title", ""),
                    "cover_img_url": v.get("pic", ""),
                    "platform": "bilibili",
                    "likes": v.get("like", 0),
                    "collects": v.get("favorite", 0),
                    "comments": v.get("comment", 0),
                    "shares": 0,
                    "tags": [],
                    "content_text": v.get("description", ""),
                    "image_urls": [],
                    "published_at": v.get("created", 0),
                }

                tag_str = v.get("tag", "")
                if tag_str:
                    item["tags"] = [t.strip() for t in tag_str.split(",") if t.strip()]

                items.append(item)

            if len(vlist) < ps:
                break

            pn += 1
            time.sleep(self.request_delay)

        logger.info(f"BilibiliSpider: API crawled {len(items)} videos")

        for i, item in enumerate(items):
            if i > 0 and i % 10 == 0:
                time.sleep(self.request_delay)
            try:
                detail = self._fetch_video_detail_api(item["note_id"], headers)
                if detail:
                    item.update(detail)
            except Exception as e:
                logger.warning(f"BilibiliSpider: detail fetch failed for {item['note_id']}: {e}")

        return items

    def _fetch_video_detail_api(self, bvid: str, headers: dict) -> dict[str, Any] | None:
        """通过 API 获取视频详情。"""
        try:
            resp = httpx.get(
                BILIBILI_API_VIDEO_INFO,
                params={"bvid": bvid},
                headers=headers,
                timeout=15.0,
            )
            data = resp.json()
        except Exception:
            return None

        stat = data.get("data", {}).get("stat", {})
        if not stat:
            return None

        return {
            "likes": stat.get("like", 0),
            "collects": stat.get("favorite", 0),
            "comments": stat.get("reply", 0),
            "shares": stat.get("share", 0),
        }

    def _crawl_via_page(self) -> list[dict[str, Any]]:
        """降级：通过页面爬取。"""
        try:
            from scrapling.fetchers import Fetcher
        except ImportError:
            logger.error("Scrapling not installed")
            return []

        home_url = BILIBILI_USER_HOME.format(uid=self.platform_uid)
        logger.info(f"BilibiliSpider: page crawl {home_url}")

        try:
            page = Fetcher.fetch(home_url, headless=True, timeout=30000)
        except Exception as e:
            logger.error(f"BilibiliSpider: page fetch failed: {e}")
            return []

        items: list[dict[str, Any]] = []
        cards = page.css("[class*='video-card'], [class*='small-item'], a[href*='/video/']")

        for card in cards:
            try:
                video_links = card.css("a[href*='/video/']")
                link = video_links[0] if video_links else card
                href = link.attrib.get("href", "") if hasattr(link, "attrib") else ""
                if not href and hasattr(card, "attrib"):
                    href = card.attrib.get("href", "")

                bvid = ""
                m = re.search(r'/video/(BV[\w]+)/?', href)
                if m:
                    bvid = m.group(1)
                if not bvid:
                    continue

                item = {
                    "note_id": bvid,
                    "title": self._safe_text(card, "[class*='title'], a[title]", attr="title") or self._safe_text(card, "[class*='title']"),
                    "cover_img_url": self._safe_text(card, "img", attr="src"),
                    "platform": "bilibili",
                    "likes": 0,
                    "collects": 0,
                    "comments": 0,
                    "shares": 0,
                    "tags": [],
                    "content_text": "",
                    "image_urls": [],
                }
                items.append(item)
            except Exception as e:
                logger.warning(f"BilibiliSpider: card parse error: {e}")

        logger.info(f"BilibiliSpider: page crawl found {len(items)} videos")
        return items