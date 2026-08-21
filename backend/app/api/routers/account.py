import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.service import get_account_service
from app.account.login_service import _active_sessions, get_login_service
from app.agents.skills.mcp.xhs_client import mcp_manager, update_mcp_cookies_from_session
from app.api.deps import get_current_user
from app.api.schemas.account import AccountResponse
from app.api.schemas.common import StandardResponse
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["account"])

# Nicknames that are known to be fake/placeholder; reject binding when matched.
_FAKE_NICKNAMES = {"", "xiaohongshu_user", "未命名用户", "小红书用户"}


@router.get("")
async def list_accounts(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[list[AccountResponse]]:
    service = get_account_service(db)
    accounts = await service.list_accounts(user_id)
    return StandardResponse(data=[
        AccountResponse(
            account_id=acc.id,
            xhs_user_id=acc.xhs_user_id,
            xhs_nickname=acc.xhs_nickname or "",
            xhs_avatar_url=acc.xhs_avatar_url or "",
            status=acc.status.value,
            login_method=acc.login_method.value,
        )
        for acc in accounts
    ])


@router.get("/worker-health")
async def worker_health() -> StandardResponse[dict]:
    login_svc = get_login_service()
    ok = await login_svc.health_check()
    return StandardResponse(data={"online": ok})


@router.post("/qrcode")
async def get_qrcode(
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    login_svc = get_login_service()
    if not await login_svc.health_check():
        raise HTTPException(
            status_code=503,
            detail="QR_WORKER_OFFLINE:扫码服务未启动，请先启动 QR Worker 进程",
        )
    service = get_account_service(db)
    try:
        result = await service.generate_qrcode()
        return StandardResponse(data=result)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=f"生成二维码失败：{e}")


@router.post("/qrcode/{qr_id}/poll")
async def poll_qrcode(
    qr_id: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    service = get_account_service(db)
    try:
        result = await service.poll_qr_status(qr_id)
        return StandardResponse(data=result)
    except RuntimeError as e:
        err_msg = str(e)
        if "无法连接 QR worker" in err_msg:
            raise HTTPException(status_code=503, detail=f"QR_WORKER_OFFLINE:{err_msg}")
        raise HTTPException(status_code=400, detail=f"查询扫码状态失败：{e}")


@router.post("/qrcode/{qr_id}/confirm")
async def confirm_qrcode(
    qr_id: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    service = get_account_service(db)
    try:
        result = await service.confirm_login(qr_id)
        return StandardResponse(data=result)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=f"确认登录失败：{e}")


@router.post("/bind")
async def bind_account(
    qr_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[AccountResponse]:
    """扫码登录后绑定账号。

    流程（全部通过 worker HTTP，不直接调 Playwright）：
    1. 检查 worker 端扫码状态是否 confirmed
    2. 从 worker 抓取真实用户信息（user_id / nickname / avatar）
    3. 从 worker 导出会话 cookies 持久化
    4. 绑定账号 + 关闭 worker 会话

    注意：主登录入口已迁移至 /api/auth/qr-login（扫码即登录并签发 JWT）。
    本接口保留供已登录用户重新扫码绑定/刷新账号信息使用。
    """
    service = get_account_service(db)
    login_svc = get_login_service()

    # 1. 确认 worker 端已扫码登录
    session = _active_sessions.get(qr_id)
    if not session:
        raise HTTPException(status_code=400, detail="QR code session not found")

    status_result = await login_svc.check_login_status(qr_id)
    if status_result.get("status") != "confirmed":
        raise HTTPException(
            status_code=400,
            detail=f"QR code not confirmed (status: {status_result.get('status', 'unknown')})",
        )

    # 2. 从 worker 抓取真实用户信息（worker 已验证非假数据）
    try:
        real_info = await login_svc.fetch_user_info(qr_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=f"无法获取真实用户信息: {e}")

    nickname = (real_info.get("nickname") or "").strip()
    xhs_user_id = (real_info.get("xhs_user_id") or "").strip()
    avatar_url = (real_info.get("avatar_url") or "").strip()

    # 3. 业务端二次校验（防御）
    if nickname in _FAKE_NICKNAMES or not xhs_user_id:
        raise HTTPException(
            status_code=400,
            detail="无法获取真实小红书用户信息（昵称/小红书号缺失）。请重新扫码登录。",
        )

    # 4. 导出会话 cookies 持久化（供后续 MCP 会话刷新使用）
    try:
        cookies = await login_svc.fetch_cookies(qr_id)
    except RuntimeError as e:
        logger.warning(f"bind: failed to fetch cookies: {e}")
        cookies = []
    session_data = {"cookies": cookies} if cookies else None

    # 5. 绑定账号
    account = await service.bind_account(
        user_id=user_id,
        xhs_user_id=xhs_user_id,
        nickname=nickname,
        avatar_url=avatar_url,
        session_data=session_data,
    )
    logger.info(f"bind: account bound: {account.id} ({nickname})")

    # 6. 关闭 worker 会话，释放浏览器 ctx
    await login_svc.close_session(qr_id)

    return StandardResponse(data=AccountResponse(
        account_id=account.id,
        xhs_user_id=account.xhs_user_id,
        xhs_nickname=account.xhs_nickname or "",
        xhs_avatar_url=account.xhs_avatar_url or "",
        status=account.status.value,
        login_method=account.login_method.value,
    ))


@router.post("/bind-manual")
async def bind_account_manual(
    qr_id: str,
    nickname: str,
    red_id: str = "",
    avatar_url: str = "",
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[AccountResponse]:
    """扫码登录后用前端手动提交的用户信息绑定账号。

    流程（不调用 worker 的 fetch_user_info，规避风控）：
    1. 检查 worker 端扫码状态是否 confirmed
    2. 从 worker 导出会话 cookies 持久化
    3. 用前端提交的 nickname/red_id 创建账号
    4. 关闭 worker 会话
    """
    service = get_account_service(db)
    login_svc = get_login_service()

    # 1. 确认 worker 端已扫码登录
    session = _active_sessions.get(qr_id)
    if not session:
        raise HTTPException(status_code=400, detail="QR code session not found")

    status_result = await login_svc.check_login_status(qr_id)
    if status_result.get("status") != "confirmed":
        raise HTTPException(
            status_code=400,
            detail=f"QR code not confirmed (status: {status_result.get('status', 'unknown')})",
        )

    nickname_clean = (nickname or "").strip()
    red_id_clean = (red_id or "").strip()
    avatar_clean = (avatar_url or "").strip()

    if not nickname_clean:
        raise HTTPException(status_code=400, detail="昵称不能为空")
    if nickname_clean in _FAKE_NICKNAMES:
        raise HTTPException(status_code=400, detail="昵称不合法，请填写真实昵称")

    # 2. 导出会话 cookies 持久化
    try:
        cookies = await login_svc.fetch_cookies(qr_id)
    except RuntimeError as e:
        logger.warning(f"bind-manual: failed to fetch cookies: {e}")
        cookies = []
    session_data = {"cookies": cookies} if cookies else None

    # 3. 生成 xhs_user_id：优先用 red_id，否则用 manual_ 前缀 + qr_id
    xhs_user_id = red_id_clean if red_id_clean else f"manual_{qr_id}"

    # 4. 绑定账号
    account = await service.bind_account(
        user_id=user_id,
        xhs_user_id=xhs_user_id,
        nickname=nickname_clean,
        avatar_url=avatar_clean,
        session_data=session_data,
    )
    logger.info(
        f"bind-manual: account bound: {account.id} ({nickname_clean}, uid={xhs_user_id})"
    )

    # 5. 关闭 worker 会话，释放浏览器 ctx
    await login_svc.close_session(qr_id)

    return StandardResponse(data=AccountResponse(
        account_id=account.id,
        xhs_user_id=account.xhs_user_id,
        xhs_nickname=account.xhs_nickname or "",
        xhs_avatar_url=account.xhs_avatar_url or "",
        status=account.status.value,
        login_method=account.login_method.value,
    ))


@router.post("/refresh-session")
async def refresh_session(
    account_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    service = get_account_service(db)
    result = await service.refresh_session(account_id, user_id)
    return StandardResponse(data=result)


@router.delete("/{account_id}")
async def delete_account(
    account_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    service = get_account_service(db)
    result = await service.unbind_account(account_id, user_id)
    return StandardResponse(data=result)