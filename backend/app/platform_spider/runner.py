"""Spider 运行器：subprocess.Popen 子进程 + async 桥接 + 通知总线进度推送。

Spider 继承 Scrapling Spider ABC，start() 自动调度
start_requests() → parse() → on_scraped_item()（实时入库）。
因 Scrapling 内部使用 Playwright sync API，必须在独立子进程中运行。

子进程通信方式：subprocess.Popen + stdout JSON 行协议，
彻底绕开 Windows multiprocessing spawn 模式的 import 问题。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.models import PlatformAccount
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

SPIDER_WORKER_SCRIPT = Path(__file__).resolve().parent / "spider_worker.py"

_last_sync_time: dict[str, float] = {}


async def start_sync(
    account_id: str, user_id: str, platform: str, force: bool = False
) -> None:
    """启动 Spider 同步任务（子进程运行）。"""
    from app.platform_spider.db_sink import update_sync_status

    await update_sync_status(user_id, platform, "running")

    try:
        account = await _get_account(account_id)
        if not account:
            await update_sync_status(user_id, platform, "idle", "账号不存在")
            return

        cookies = account.cookies_json or {}
        platform_uid = account.platform_uid or ""

        storage_path = Path(__file__).resolve().parent.parent / "storage_states" / f"{platform}.json"
        if not storage_path.exists():
            logger.warning(f"Spider: no storageState for {platform}, login may not persist. User should re-login.")

        cookies_json = json.dumps(cookies, ensure_ascii=False)

        backend_dir = str(Path(__file__).resolve().parent.parent.parent)
        env = os.environ.copy()
        pythonpath = env.get("PYTHONPATH", "")
        if backend_dir not in pythonpath.split(os.pathsep):
            env["PYTHONPATH"] = f"{backend_dir}{os.pathsep}{pythonpath}" if pythonpath else backend_dir

        try:
            proc = subprocess.Popen(
                [sys.executable, str(SPIDER_WORKER_SCRIPT), platform, platform_uid, cookies_json, user_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        except Exception as e:
            logger.error(f"Spider: failed to start spider_worker subprocess: {e}", exc_info=True)
            await update_sync_status(user_id, platform, "idle", f"启动子进程失败: {e}")
            return

        logger.info(f"Spider subprocess started for {platform}, pid={proc.pid}")

        try:
            result_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, proc.stdout.readline),
                timeout=300,
            )
        except asyncio.TimeoutError:
            result_line = None
            if proc.poll() is None:
                proc.terminate()
                logger.warning(f"Spider subprocess timed out, terminated: {platform}")

        try:
            proc.wait(timeout=10)
        except Exception:
            pass

        stderr_output = ""
        try:
            stderr_bytes = proc.stderr.read()
            if stderr_bytes:
                stderr_output = stderr_bytes.decode("utf-8", errors="replace")[:2000]
        except Exception:
            pass

        if stderr_output:
            logger.debug(f"Spider worker stderr: {stderr_output[:500]}")

        if not result_line:
            await update_sync_status(user_id, platform, "idle", "Spider 超时或无结果")
            return

        raw = result_line.strip()
        if not raw:
            await update_sync_status(user_id, platform, "idle", "Spider 无输出")
            return

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Spider result JSON decode error: {e}, raw[:200]={raw[:200]}")
            await update_sync_status(user_id, platform, "idle", f"Spider 结果解析失败: {e}")
            return

        if result.get("error"):
            await update_sync_status(user_id, platform, "idle", result["error"])
            return

        items = result.get("items", [])
        saved_count = 0
        for item in items:
            try:
                from app.platform_spider.db_sink import save_scraped_item
                saved = await save_scraped_item(item, platform, user_id)
                if saved:
                    saved_count += 1

                    if saved_count % 10 == 0:
                        try:
                            from app.services.notification_bus import notification_bus
                            await notification_bus.publish("spider_sync_progress", {
                                "platform": platform,
                                "saved": saved_count,
                                "total": len(items),
                                "title": item.get("title", "")[:50],
                            })
                        except Exception:
                            pass

            except Exception as e:
                logger.warning(f"save_scraped_item failed: {e}")

        from app.platform_spider.db_sink import update_works_count
        await update_works_count(user_id, platform, saved_count)

        await update_sync_status(user_id, platform, "idle")

        try:
            from app.services.notification_bus import notification_bus
            await notification_bus.publish("spider_sync_completed", {
                "platform": platform,
                "total": len(items),
                "saved": saved_count,
                "user_id": user_id,
            })
        except Exception:
            pass

        logger.info(f"Spider sync completed: platform={platform}, total={len(items)}, saved={saved_count}")

    except Exception as e:
        logger.error(f"Spider sync failed: platform={platform}, error={e}", exc_info=True)
        await update_sync_status(user_id, platform, "idle", str(e)[:500])

        try:
            from app.services.notification_bus import notification_bus
            await notification_bus.publish("spider_sync_failed", {
                "platform": platform,
                "error": str(e)[:200],
                "user_id": user_id,
            })
        except Exception:
            pass


async def _get_account(account_id: str) -> PlatformAccount | None:
    """获取 PlatformAccount。"""
    async with AsyncSessionLocal() as db:
        return await db.scalar(
            select(PlatformAccount).where(PlatformAccount.id == account_id)
        )