"""平台 Spider 基类。

基于 Scrapling Spider ABC，提供通用配置和入库回调。
子类只需实现 parse() 和平台特定选择器。
"""
from __future__ import annotations

import logging
from typing import Any

from scrapling.spiders import Spider
from scrapling.spiders.session import SessionManager

logger = logging.getLogger(__name__)


class BasePlatformSpider(Spider):
    """平台 Spider 基类，继承 Scrapling Spider ABC。

    子类需实现：
      - configure_sessions(): 配置 StealthySession / FetcherSession
      - parse(): 解析列表页，yield Request 或 dict
      - parse_note_detail(): 解析详情页（可选）

    通用能力：
      - adaptive=True: 自适应选择器，网站改版自动容错
      - autothrottle: 自动限速
      - on_scraped_item(): 每条结果实时入库 + 推送进度
      - on_close(): 爬取完成后更新同步状态
    """

    platform: str = ""
    user_id: str = ""
    platform_uid: str = ""
    cookies: dict | None = None

    adaptive = True
    autothrottle_enabled = True
    autothrottle_start_delay = 2.0
    autothrottle_max_delay = 10.0
    concurrent_requests = 2
    max_blocked_retries = 3

    def __init__(self, user_id: str = "", platform_uid: str = "", cookies: dict | None = None, **kwargs):
        self.user_id = user_id
        self.platform_uid = platform_uid
        self.cookies = cookies
        super().__init__(**kwargs)

    async def on_scraped_item(self, item: dict) -> dict | None:
        """每条结果实时入库 + 推送进度。"""
        from app.platform_spider.db_sink import save_scraped_item
        saved = await save_scraped_item(item, self.platform, self.user_id)
        if saved:
            try:
                from app.services.notification_bus import notification_bus
                await notification_bus.publish("spider_item_scraped", {
                    "platform": self.platform,
                    "title": item.get("title", "")[:50],
                    "spider_name": self.name,
                })
            except Exception:
                pass
        return item

    async def on_close(self) -> None:
        """爬取完成后更新 PlatformAccount 同步状态。"""
        from app.platform_spider.db_sink import update_sync_status
        await update_sync_status(self.user_id, self.platform, "idle")

    @staticmethod
    def _parse_count(text: str) -> int:
        """解析 '1.2w' '3.5k' '1.2万' 等中文计数格式。"""
        text = text.strip().replace(",", "")
        if not text:
            return 0
        try:
            if "w" in text or "万" in text:
                return int(float(text.replace("w", "").replace("万", "")) * 10000)
            if "k" in text:
                return int(float(text.replace("k", "")) * 1000)
            return int(float(text))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _safe_text(el: Any, selectors: str, attr: str = "text") -> str:
        """Scrapling 自适应选择器提取文本或属性，支持逗号分隔的多 selector。"""
        for sel in selectors.split(", "):
            try:
                sel = sel.strip()
                if not sel:
                    found = el
                else:
                    els = el.css(sel)
                    found = els[0] if els else None
                if not found:
                    continue
                if attr == "text":
                    return found.text.strip() if hasattr(found, "text") else ""
                return found.attrib.get(attr, "") if hasattr(found, "attrib") else ""
            except Exception:
                continue
        return ""