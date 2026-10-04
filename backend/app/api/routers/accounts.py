"""平台账号管理 API。

提供端点：
- GET  /api/accounts：列出所有平台的绑定状态
- POST /api/accounts/bind：触发扫码绑定
- GET  /api/accounts/qr-status/{task_id}：轮询扫码状态
- DELETE /api/accounts/{account_id}：解绑
- POST /api/accounts/{account_id}/sync：同步作品数据
- POST /api/accounts/sync-all：同步所有已绑定账号
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete as sa_delete

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.models import PlatformAccount
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

SUPPORTED_PLATFORMS = ["xiaohongshu", "douyin", "bilibili"]

PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "bilibili": "B站",
}


class BindRequest(BaseModel):
    platform: str = Field(description="平台标识：xiaohongshu / douyin / bilibili")


class SyncRequest(BaseModel):
    force: bool = Field(default=False, description="true=全量同步，false=增量同步")


@router.get("")
async def list_accounts(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list[dict[str, Any]]]:
    """列出所有平台的绑定状态，未绑定的也列出（bound: false）。"""
    async with AsyncSessionLocal() as db:
        result = await db.scalars(
            select(PlatformAccount).where(PlatformAccount.user_id == user_id)
        )
        bound_map: dict[str, PlatformAccount] = {
            acc.platform: acc for acc in result.all()
        }

    items = []
    for plat in SUPPORTED_PLATFORMS:
        acc = bound_map.get(plat)
        if acc:
            items.append({
                "id": acc.id,
                "platform": acc.platform,
                "platform_label": PLATFORM_LABELS.get(acc.platform, acc.platform),
                "platform_uid": acc.platform_uid,
                "platform_nickname": acc.platform_nickname,
                "platform_avatar_url": acc.platform_avatar_url,
                "platform_home_url": acc.platform_home_url,
                "last_synced_at": acc.last_synced_at.isoformat() if acc.last_synced_at else None,
                "sync_status": acc.sync_status,
                "sync_error": acc.sync_error,
                "works_count": acc.works_count,
                "fans_count": acc.fans_count,
                "bound": True,
            })
        else:
            items.append({
                "id": None,
                "platform": plat,
                "platform_label": PLATFORM_LABELS.get(plat, plat),
                "platform_uid": None,
                "platform_nickname": None,
                "platform_avatar_url": None,
                "platform_home_url": None,
                "last_synced_at": None,
                "sync_status": "idle",
                "sync_error": None,
                "works_count": 0,
                "fans_count": None,
                "bound": False,
            })

    return StandardResponse(data=items)


@router.post("/bind")
async def bind_account(
    req: BindRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """触发扫码绑定：启动浏览器，等待用户扫码登录。"""
    if req.platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"不支持的平台：{req.platform}")

    from app.services.platform_login import start_qr_login
    task_id, qr_data = await start_qr_login(req.platform, user_id)

    return StandardResponse(data={
        "task_id": task_id,
        "platform": req.platform,
        "status": "scanned",
        "qr_code": qr_data,
        "message": "请扫描二维码登录",
    })


@router.get("/qr-status/{task_id}")
async def qr_status(
    task_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """轮询扫码状态。"""
    from app.services.platform_login import get_bind_task_status
    status_info = get_bind_task_status(task_id)
    if not status_info:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    return StandardResponse(data=status_info)


@router.delete("/{account_id}")
async def unbind_account(
    account_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """解绑平台账号。"""
    async with AsyncSessionLocal() as db:
        acc = await db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.id == account_id,
                PlatformAccount.user_id == user_id,
            )
        )
        if not acc:
            raise HTTPException(status_code=404, detail="账号不存在")
        await db.execute(
            sa_delete(PlatformAccount).where(PlatformAccount.id == account_id)
        )
        await db.commit()

    return StandardResponse(data={"unbound": True, "account_id": account_id})


@router.post("/{account_id}/sync")
async def sync_account(
    account_id: str,
    req: SyncRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """同步指定账号的作品数据。"""
    async with AsyncSessionLocal() as db:
        acc = await db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.id == account_id,
                PlatformAccount.user_id == user_id,
            )
        )
        if not acc:
            raise HTTPException(status_code=404, detail="账号不存在")
        if acc.sync_status == "running":
            return StandardResponse(
                success=False,
                message="该账号正在同步中，请稍后再试",
                data={"account_id": account_id, "status": "running"},
            )

    from app.platform_spider.runner import start_sync
    await start_sync(account_id, user_id, acc.platform, force=req.force)

    return StandardResponse(data={
        "account_id": account_id,
        "platform": acc.platform,
        "status": "started",
        "message": "同步已启动，通过通知总线推送进度",
    })


@router.post("/sync-all")
async def sync_all_accounts(
    req: SyncRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """同步所有已绑定账号的作品数据。"""
    async with AsyncSessionLocal() as db:
        result = await db.scalars(
            select(PlatformAccount).where(
                PlatformAccount.user_id == user_id,
                PlatformAccount.sync_status != "running",
            )
        )
        accounts = list(result.all())

    if not accounts:
        return StandardResponse(data={"synced": 0, "message": "没有可同步的账号"})

    from app.platform_spider.runner import start_sync
    for acc in accounts:
        try:
            await start_sync(acc.id, user_id, acc.platform, force=req.force)
        except Exception as e:
            logger.warning(f"sync_all: {acc.platform} start failed: {e}")

    return StandardResponse(data={
        "synced": len(accounts),
        "platforms": [acc.platform for acc in accounts],
        "message": f"已启动 {len(accounts)} 个平台的同步",
    })