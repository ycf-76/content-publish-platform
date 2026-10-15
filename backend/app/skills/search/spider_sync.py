"""平台数据同步 Skill：将 Spider 爬虫能力桥接到 Agent 工具链。

职责：
- 让 Agent 能通过 Skill 调用爬虫，同步用户在平台账号上的已发布作品
- 复用 app.platform_spider.runner.start_sync() 的完整逻辑
- 支持单账号同步和全量同步

调用方式：
  Agent 在对话中判断用户意图（如"帮我同步小红书作品"）→ 调用 spider_sync skill
  → start_sync() 在后台线程运行 Spider → 结果写入 PublishedContentPerformance 表
  → 返回同步状态给 Agent → Agent 回复用户

红线：
- 同步是异步后台任务，execute() 启动后立即返回状态，不阻塞 Agent 循环
- 需要从 _context 获取 user_id，确保只能同步自己的账号
- 频率保护：距上次同步不足 1 小时时拒绝，避免触发平台风控
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.skill_base import Skill
from app.engine.schemas import Permission
from app.core.skill_registry import register

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = {"xiaohongshu", "douyin", "bilibili"}

PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "bilibili": "B站",
}


class SpiderSyncInput(BaseModel):
    platform: str = Field(
        default="",
        description=(
            "要同步的平台：xiaohongshu / douyin / bilibili。"
            "留空表示同步所有已绑定平台"
        ),
    )
    force: bool = Field(
        default=False,
        description="true=强制全量同步（忽略频率保护），false=增量同步",
    )


@register
class SpiderSyncSkill(Skill):
    """平台作品数据同步（爬虫）。

    让 Agent 能触发 Spider 同步用户在各平台的已发布作品数据。
    同步结果写入 PublishedContentPerformance 表（content_status='collected'），
    前端"已采集"列表自动展示。
    """

    node_type = "search"
    name = "spider_sync"
    display_name = "平台数据同步"
    description = (
        "同步用户在平台账号上的已发布作品数据（爬虫）。"
        "当用户要求同步、更新、拉取自己账号的作品/笔记/视频时调用。"
        "不要在搜索热点/竞品分析场景调用（用 trending_search）。"
        "输入 platform（可选，留空同步全部），返回同步启动状态"
    )
    input_schema = SpiderSyncInput
    required_permissions = [Permission.XHS_SEARCH]
    trigger_words = ["同步", "拉取作品", "更新作品", "同步数据", "抓取我的", "爬取我的"]

    prompt_guidance: str = (
        "【spider_sync 使用指引】\n"
        "- 用途：同步用户自己账号的已发布作品到系统数据库，不是搜索全网内容。\n"
        "- 触发场景：用户说「同步我的小红书作品」「拉取抖音数据」「更新所有平台作品」等。\n"
        "- platform 参数：xiaohongshu / douyin / bilibili，留空同步全部已绑定平台。\n"
        "- 同步是后台异步任务，调用后立即返回，不需要等待完成。\n"
        "- 频率保护：距上次同步不足1小时会拒绝（除非 force=true）。"
    )

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = SpiderSyncInput.model_validate(inputs)
        ctx = inputs.get("_context")
        user_id = ctx.user_id if ctx and hasattr(ctx, "user_id") else ""
        if not user_id:
            return {"ok": False, "error": "无法获取用户身份，请重新登录"}

        if in_.platform and in_.platform not in SUPPORTED_PLATFORMS:
            return {
                "ok": False,
                "error": f"不支持的平台：{in_.platform}，可选：{', '.join(SUPPORTED_PLATFORMS)}",
            }

        from app.db.session import AsyncSessionLocal
        from app.db.models import PlatformAccount

        async with AsyncSessionLocal() as db:
            query = select(PlatformAccount).where(
                PlatformAccount.user_id == user_id,
            )
            if in_.platform:
                query = query.where(PlatformAccount.platform == in_.platform)
            result = await db.scalars(query)
            accounts = list(result.all())

        if not accounts:
            platform_hint = f"「{PLATFORM_LABELS.get(in_.platform, in_.platform)}」" if in_.platform else "任何平台"
            return {
                "ok": False,
                "error": f"尚未绑定{platform_hint}账号，请先在设置中绑定平台账号",
            }

        syncable = []
        skipped_running = []
        skipped_frequency = []
        now = datetime.now(UTC)

        for acc in accounts:
            if acc.sync_status == "running":
                skipped_running.append(PLATFORM_LABELS.get(acc.platform, acc.platform))
                continue
            if not in_.force and acc.last_synced_at:
                elapsed = (now - acc.last_synced_at.replace(tzinfo=UTC)).total_seconds()
                if elapsed < 3600:
                    skipped_frequency.append(
                        f"{PLATFORM_LABELS.get(acc.platform, acc.platform)}（{int(elapsed / 60)}分钟前刚同步）"
                    )
                    continue
            syncable.append(acc)

        if not syncable:
            if skipped_running:
                return {
                    "ok": False,
                    "error": f"以下平台正在同步中：{'、'.join(skipped_running)}，请稍后再试",
                }
            if skipped_frequency:
                return {
                    "ok": False,
                    "error": f"同步过于频繁：{'、'.join(skipped_frequency)}。如需强制同步，请设置 force=true",
                }
            return {"ok": False, "error": "没有可同步的账号"}

        from app.platform_spider.db_sink import update_sync_status
        from app.platform_spider.runner import start_sync

        launched = []
        for acc in syncable:
            try:
                await update_sync_status(user_id, acc.platform, "running")
                asyncio.create_task(
                    start_sync(acc.id, user_id, acc.platform, force=in_.force)
                )
                launched.append(PLATFORM_LABELS.get(acc.platform, acc.platform))
            except Exception as e:
                logger.warning(f"[SpiderSyncSkill] failed to launch sync for {acc.platform}: {e}")

        if not launched:
            return {"ok": False, "error": "同步启动失败，请稍后再试"}

        summary_parts = []
        if launched:
            summary_parts.append(f"已启动同步：{'、'.join(launched)}")
        if skipped_running:
            summary_parts.append(f"正在同步中（跳过）：{'、'.join(skipped_running)}")
        if skipped_frequency:
            summary_parts.append(f"频率保护（跳过）：{'、'.join(skipped_frequency)}")

        return {
            "ok": True,
            "launched": launched,
            "skipped_running": skipped_running,
            "skipped_frequency": skipped_frequency,
            "message": "；".join(summary_parts),
        }