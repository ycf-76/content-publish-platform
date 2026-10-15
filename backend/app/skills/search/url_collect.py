"""URL 内容采集 Skill：将 work_collector 的 Scrapling 降级链能力桥接到 Agent 工具链。

职责：
- 让 Agent 能通过 Skill 采集任意 URL 的内容详情
- 复用 app.services.work_collector.collect_from_url() 的完整降级链
- 支持小红书 / 抖音 / B站 / 微信公众号 / Instagram / Threads

降级链（按优先级）：
  0. scrapling_fetcher：Scrapling StealthyFetcher（反检测浏览器渲染 JS，需 pip install scrapling）
  1. page_ssr_parse：直接 HTTP GET 解析 __INITIAL_STATE__（最轻量）
  2. link_grabber：link-grabber MCP server（需 uv + link-grabber）
  3. xhs_web_api：小红书 Web API（需 cookies）
  4. mcp_note_detail：MCP 浏览器 get_note_detail（最重，兜底）
  5. creator_center_csv：创作者中心 CSV 导出（需手动导出）

调用方式：
  Agent 在对话中判断用户意图（如"帮我采集这个链接的内容"）→ 调用 url_collect skill
  → collect_from_url() 按降级链采集 → 返回结构化数据给 Agent

红线：
- 采集是同步阻塞调用（最长约 30s），但降级链各环节有独立超时
- 不自动入库（与 spider_sync 不同），只返回采集结果，由 Agent 决定是否保存
- 频率保护：同一 URL 60 秒内不重复采集
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.skill_base import Skill
from app.engine.schemas import Permission
from app.core.skill_registry import register

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "bilibili": "B站",
    "wechat_mp": "微信公众号",
    "instagram": "Instagram",
    "threads": "Threads",
}

_recent_collects: dict[str, float] = {}
_COLLECT_COOLDOWN = 60.0


class UrlCollectInput(BaseModel):
    url: str = Field(
        ...,
        description=(
            "要采集内容的 URL 链接。"
            "支持小红书/抖音/B站/微信公众号/Instagram/Threads 的笔记/视频/文章链接，"
            "也支持短链接（xhslink.com / v.douyin.com / b23.tv）"
        ),
    )
    platform: str = Field(
        default="auto",
        description=(
            "平台标识，留空或 auto 则自动检测。"
            "可选：xiaohongshu / douyin / bilibili / wechat_mp / instagram / threads"
        ),
    )


@register
class UrlCollectSkill(Skill):
    """URL 内容采集（Scrapling 降级链）。

    让 Agent 能采集任意 URL 的内容详情，走 Scrapling → SSR → link-grabber → API 降级链。
    采集结果不入库，只返回结构化数据，由 Agent 决定后续操作。
    """

    node_type = "search"
    name = "url_collect"
    display_name = "链接内容采集"
    description = (
        "采集指定链接的内容详情（标题/正文/互动数据/图片等）。"
        "当用户提供链接并要求采集/读取/分析该链接内容时调用。"
        "不要在同步自己账号作品时调用（用 spider_sync）。"
        "输入 url，返回采集到的结构化内容数据"
    )
    input_schema = UrlCollectInput
    required_permissions = [Permission.XHS_SEARCH]
    trigger_words = [
        "采集链接", "读取链接", "抓取链接", "分析链接",
        "采集内容", "读取内容", "抓取内容",
        "看看这个链接", "这个链接说了什么",
        "采集这个", "抓取这个",
    ]

    prompt_guidance: str = (
        "【url_collect 使用指引】\n"
        "- 用途：采集用户提供的单个链接的内容详情，返回标题/正文/互动数据/图片等。\n"
        "- 触发场景：用户粘贴链接并说「采集这个链接」「看看这个链接说了什么」「分析这个内容」等。\n"
        "- url 参数：要采集的完整 URL（支持短链接自动重定向）。\n"
        "- platform 参数：一般留空自动检测，仅在自动检测失败时手动指定。\n"
        "- 降级链：Scrapling浏览器渲染 → SSR解析 → link-grabber → 平台API → MCP兜底。\n"
        "- 采集结果不入库，只返回数据，由你决定是否保存或基于此生成内容。\n"
        "- 频率保护：同一链接60秒内不重复采集。\n"
        "- B站动态页（t.bilibili.com）是前端JS渲染，curl拿不到内容，本工具会走浏览器渲染降级。"
    )

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = UrlCollectInput.model_validate(inputs)
        url = in_.url.strip()

        if not url:
            return {"ok": False, "error": "URL 不能为空"}

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        now = time.monotonic()
        last_time = _recent_collects.get(url, 0)
        if now - last_time < _COLLECT_COOLDOWN:
            remaining = int(_COLLECT_COOLDOWN - (now - last_time))
            return {
                "ok": False,
                "error": f"该链接 {remaining} 秒前刚采集过，请稍后再试或使用缓存结果",
            }

        from app.services.work_collector import (
            collect_from_url,
            detect_platform,
            get_last_collect_errors,
        )

        platform = in_.platform if in_.platform and in_.platform != "auto" else None
        detected = detect_platform(url) if not platform else platform

        platform_label = SUPPORTED_PLATFORMS.get(detected, detected)

        logger.info(f"[UrlCollectSkill] collecting url={url}, platform={detected}")

        try:
            result = await collect_from_url(url, platform=platform)
        except Exception as e:
            logger.error(f"[UrlCollectSkill] collect_from_url failed: {e}", exc_info=True)
            return {
                "ok": False,
                "error": f"采集失败：{e}",
                "platform": detected,
                "platform_label": platform_label,
            }

        _recent_collects[url] = time.monotonic()

        if not result:
            errors = get_last_collect_errors()
            return {
                "ok": False,
                "error": "所有采集方式均失败",
                "fallback_errors": errors,
                "platform": detected,
                "platform_label": platform_label,
                "hint": (
                    "可尝试：1) 确认链接是否正确 2) 如为B站动态页，需安装 scrapling (pip install scrapling) "
                    "3) 如需登录态，请先在设置中绑定平台账号"
                ),
            }

        return {
            "ok": True,
            "platform": detected,
            "platform_label": platform_label,
            "source": result.get("source", "unknown"),
            "data": result,
        }