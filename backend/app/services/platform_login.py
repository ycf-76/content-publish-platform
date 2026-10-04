"""平台扫码登录服务。

使用 Playwright 同步 API 在独立子进程中打开平台登录页，
截图二维码发送到前端弹窗展示，用户扫码后轮询检测登录状态。
子进程运行避免阻塞 uvicorn event loop。
登录成功后保存 storageState（含 httpOnly cookies）到磁盘，
Spider 通过加载 storageState 恢复登录态。

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.models import PlatformAccount
from app.db.session import AsyncSessionLocal

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage_states"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

_bind_tasks: dict[str, dict[str, Any]] = {}

QR_WORKER_SCRIPT = Path(__file__).resolve().parent / "qr_worker.py"


async def start_qr_login(platform: str, user_id: str) -> tuple[str, dict]:
    """启动扫码登录子进程，返回 (task_id, qr_data)。"""
    from app.db.models import generate_ulid

    task_id = f"bind_{generate_ulid()}"
    _bind_tasks[task_id] = {
        "status": "pending",
        "platform": platform,
        "user_id": user_id,
        "created_at": time.time(),
    }

    backend_dir = str(Path(__file__).resolve().parent.parent.parent)
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    if backend_dir not in pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = f"{backend_dir}{os.pathsep}{pythonpath}" if pythonpath else backend_dir

    try:
        proc = subprocess.Popen(
            [sys.executable, str(QR_WORKER_SCRIPT), platform],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except Exception as e:
        logger.error(f"[platform_login] Failed to start qr_worker subprocess: {e}", exc_info=True)
        _bind_tasks[task_id]["status"] = "failed"
        _bind_tasks[task_id]["error"] = f"启动子进程失败: {e}"
        return task_id, {"error": f"启动子进程失败: {e}"}

    logger.info(f"[platform_login] qr_worker subprocess started, pid={proc.pid}, platform={platform}")

    qr_data: dict = {}
    try:
        qr_line = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, proc.stdout.readline),
            timeout=45,
        )
        if qr_line:
            raw = qr_line.strip()
            if raw:
                qr_data = json.loads(raw)
        else:
            qr_data = {"error": "子进程无输出"}
    except asyncio.TimeoutError:
        qr_data = {"error": "获取二维码超时（45秒）"}
        logger.warning(f"[platform_login] QR code timeout for {platform}")
    except json.JSONDecodeError as e:
        qr_data = {"error": f"二维码数据解析失败: {e}"}
        logger.warning(f"[platform_login] QR data JSON decode error: {e}")
    except Exception as e:
        qr_data = {"error": f"获取二维码失败: {e}"}
        logger.warning(f"[platform_login] QR fetch error: {e}")

    if qr_data.get("error"):
        _bind_tasks[task_id]["status"] = "failed"
        _bind_tasks[task_id]["error"] = qr_data["error"]
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        return task_id, qr_data

    _bind_tasks[task_id]["status"] = "scanned"

    asyncio.create_task(_poll_login_result(task_id, proc))

    return task_id, qr_data


async def _poll_login_result(
    task_id: str,
    proc: subprocess.Popen,
) -> None:
    """轮询子进程的登录结果行。"""
    try:
        try:
            result_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, proc.stdout.readline),
                timeout=300,
            )
        except asyncio.TimeoutError:
            result_line = None
            logger.warning(f"[platform_login] login result timeout: {task_id}")

        if result_line:
            raw = result_line.strip()
            if raw:
                result = json.loads(raw)
            else:
                result = None
        else:
            result = None

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
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
            logger.debug(f"[platform_login] qr_worker stderr: {stderr_output[:500]}")

        if result is None or not result.get("ok"):
            error_msg = (result or {}).get("error", "登录超时或失败")
            _bind_tasks[task_id]["status"] = "failed"
            _bind_tasks[task_id]["error"] = error_msg
            return

        cookies = result["cookies"]
        user_info = result["user_info"]
        user_id = _bind_tasks[task_id]["user_id"]
        platform = _bind_tasks[task_id]["platform"]

        storage_path = STORAGE_DIR / f"{platform}.json"
        if not storage_path.exists():
            logger.warning(f"[platform_login] storageState file not found at {storage_path}, login state may not persist for Spider")
        else:
            logger.info(f"[platform_login] storageState verified at {storage_path} (size={storage_path.stat().st_size})")

        account = await _save_account(user_id, platform, user_info, cookies)

        _bind_tasks[task_id]["status"] = "confirmed"
        _bind_tasks[task_id]["account"] = {
            "id": account.id,
            "platform_nickname": account.platform_nickname,
            "platform_avatar_url": account.platform_avatar_url,
            "fans_count": account.fans_count,
            "works_count": account.works_count,
        }

    except Exception as e:
        logger.error(f"poll_login_result error: {e}", exc_info=True)
        if task_id in _bind_tasks:
            _bind_tasks[task_id]["status"] = "failed"
            _bind_tasks[task_id]["error"] = str(e)[:500]
    finally:
        _cleanup_expired_tasks()


def get_bind_task_status(task_id: str) -> dict[str, Any] | None:
    info = _bind_tasks.get(task_id)
    if not info:
        return None

    result: dict[str, Any] = {
        "task_id": task_id,
        "status": info["status"],
        "platform": info["platform"],
    }
    if info.get("error"):
        result["error"] = info["error"]
    if info["status"] == "confirmed" and "account" in info:
        result["account"] = info["account"]
    return result


async def _save_account(
    user_id: str,
    platform: str,
    user_info: dict,
    cookies: list[dict],
) -> PlatformAccount:
    from app.db.models import generate_ulid

    cookies_dict = {}
    for c in cookies:
        if isinstance(c, dict):
            name = c.get("name", "")
            if name:
                cookies_dict[name] = {
                    "value": c.get("value", ""),
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                }

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.user_id == user_id,
                PlatformAccount.platform == platform,
            )
        )

        if existing:
            existing.cookies_json = cookies_dict
            existing.platform_nickname = user_info.get("nickname") or existing.platform_nickname
            uid = user_info.get("uid") or existing.platform_uid
            if uid:
                existing.platform_uid = uid
            existing.platform_avatar_url = user_info.get("avatar_url") or existing.platform_avatar_url
            existing.sync_status = "idle"
            existing.sync_error = None
            existing.updated_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(existing)
            return existing

        account = PlatformAccount(
            id=generate_ulid(),
            user_id=user_id,
            platform=platform,
            platform_uid=user_info.get("uid"),
            platform_nickname=user_info.get("nickname"),
            platform_avatar_url=user_info.get("avatar_url"),
            cookies_json=cookies_dict,
            sync_status="idle",
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
        return account


def _cleanup_expired_tasks() -> None:
    now = time.time()
    expired = [
        tid for tid, info in _bind_tasks.items()
        if now - info.get("created_at", 0) > 600
    ]
    for tid in expired:
        if _bind_tasks[tid]["status"] in ("pending", "scanned"):
            _bind_tasks[tid]["status"] = "expired"
            _bind_tasks[tid]["error"] = "任务超时"
        if now - _bind_tasks[tid].get("created_at", 0) > 1800:
            del _bind_tasks[tid]