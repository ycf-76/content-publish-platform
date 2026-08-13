"""Authentication routers.

基于小红书扫码/插件登录实现系统登录（一人一账号，通过 xhs_user_id 关联 User）：
- POST /api/auth/qr-login?qr_id=xxx：扫码确认后自动获取用户信息，签发 JWT
- POST /api/auth/qr-login-manual：扫码确认但自动获取失败时，用前端提交的信息签发 JWT
- POST /api/auth/plugin-login：通过浏览器扩展获取用户信息，签发 JWT
- POST /api/auth/plugin-login-manual：插件已登录但扩展提取失败时，用前端提交的信息签发 JWT
- GET  /api/auth/me：返回当前登录用户信息（需 JWT）
- POST /api/auth/logout：登出（JWT 无状态，前端清 token 即可）
- POST /api/auth/sse-session：下发 SSE cookie session

所有登录接口均不需要 JWT（用于签发 JWT）；账号管理接口（/api/accounts/*）需要 JWT。
"""
from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.login_service import _active_sessions, get_login_service
from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.crypto.token_crypto import TokenCrypto
from app.db.models import AccountStatus, LoginMethod, User, XhsAccount, generate_ulid
from app.db.session import get_db
from app.security import create_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 内存存储已发放的 sse_token（MVP 阶段，单实例够用）
_sse_tokens: set[str] = set()

# 与 account.py._FAKE_NICKNAMES 保持同步的占位昵称黑名单
_FAKE_NICKNAMES = {"", "xiaohongshu_user", "未命名用户", "小红书用户"}


async def _login_and_issue_jwt(
    db: AsyncSession,
    xhs_user_id: str,
    nickname: str,
    avatar_url: str,
    session_data: dict[str, Any] | None = None,
    login_method: LoginMethod = LoginMethod.QRCODE,
) -> tuple[str, str]:
    """通过 xhs_user_id 反查/创建 User + 绑定/更新 XhsAccount，签发 JWT。

    - 命中已有 XhsAccount → 复用其 user_id，更新账号信息
    - 未命中 → 新建 User + 新建 XhsAccount

    Returns:
        (user_id, jwt_token)
    """
    crypto = TokenCrypto()
    now = datetime.now(UTC)

    stmt = select(XhsAccount).where(XhsAccount.xhs_user_id == xhs_user_id)
    account = await db.scalar(stmt)

    if account:
        # 老用户：复用 user_id，更新账号信息
        user_id = account.user_id
        account.xhs_nickname = nickname
        account.xhs_avatar_url = avatar_url
        account.status = AccountStatus.ACTIVE
        account.login_method = login_method
        account.last_used_at = now
        if session_data:
            account.session_data_encrypted = crypto.encrypt_dict(session_data)
        await db.commit()
        logger.info(f"auth: existing user {user_id} logged in ({nickname})")
    else:
        # 新用户：建 User + XhsAccount
        user = User(id=generate_ulid())
        db.add(user)
        await db.flush()  # 拿到 user.id

        account = XhsAccount(
            user_id=user.id,
            xhs_user_id=xhs_user_id,
            xhs_nickname=nickname,
            xhs_avatar_url=avatar_url,
            login_method=login_method,
            status=AccountStatus.ACTIVE,
            last_used_at=now,
        )
        if session_data:
            account.session_data_encrypted = crypto.encrypt_dict(session_data)
        db.add(account)
        await db.commit()
        user_id = user.id
        logger.info(f"auth: new user {user_id} created ({nickname})")

    token = create_jwt(
        user_id,
        extra_claims={"xhs_user_id": xhs_user_id, "nickname": nickname},
    )
    return user_id, token


def _build_login_response(
    user_id: str, token: str, xhs_user_id: str, nickname: str, avatar_url: str
) -> dict[str, Any]:
    return {
        "token": token,
        "user_id": user_id,
        "xhs_user_id": xhs_user_id,
        "nickname": nickname,
        "avatar_url": avatar_url,
    }


@router.post("/qr-login")
async def qr_login(
    qr_id: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """扫码登录：扫码确认后，通过 xhs_user_id 反查/创建 User，签发 JWT。

    流程（全部通过 worker HTTP，不直接调 Playwright）：
    1. 校验 worker 端扫码状态是否 confirmed
    2. 从 worker 抓取真实用户信息（xhs_user_id / nickname / avatar）
    3. 从 worker 导出会话 cookies 持久化
    4. 登录并签发 JWT（_login_and_issue_jwt）
    5. 关闭 worker 会话

    前端调用顺序：
      POST /api/accounts/qrcode           → 拿 qr_id + 二维码
      POST /api/accounts/qrcode/{id}/poll → 轮询到 confirmed
      POST /api/auth/qr-login?qr_id=xxx   → 拿 token + 用户信息
    """
    login_svc = get_login_service()

    # 1. 校验 worker 端扫码状态
    if qr_id not in _active_sessions:
        raise HTTPException(status_code=400, detail="QR code session not found")

    status_result = await login_svc.check_login_status(qr_id)
    if status_result.get("status") != "confirmed":
        raise HTTPException(
            status_code=400,
            detail=f"QR code not confirmed (status: {status_result.get('status', 'unknown')})",
        )

    # 2. 抓取真实用户信息
    try:
        real_info = await login_svc.fetch_user_info(qr_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=f"无法获取真实用户信息: {e}")

    nickname = (real_info.get("nickname") or "").strip()
    xhs_user_id = (real_info.get("xhs_user_id") or "").strip()
    avatar_url = (real_info.get("avatar_url") or "").strip()

    if nickname in _FAKE_NICKNAMES or not xhs_user_id:
        raise HTTPException(
            status_code=400,
            detail="need_manual:无法获取真实小红书用户信息（昵称/小红书号缺失），请手动输入",
        )

    # 3. 导出会话 cookies 持久化
    try:
        cookies = await login_svc.fetch_cookies(qr_id)
    except RuntimeError as e:
        logger.warning(f"qr-login: failed to fetch cookies: {e}")
        cookies = []

    # 校验 cookies 完整性：缺失关键登录态 cookie 会导致后续搜索被风控
    if cookies:
        cookie_names = [c.get("name", "") for c in cookies]
        has_a1 = any("a1" == n for n in cookie_names)
        has_web_session = any("web_session" == n for n in cookie_names)
        if len(cookies) < 5 or not has_a1 or not has_web_session:
            logger.warning(
                f"qr-login: cookies INCOMPLETE - {len(cookies)} cookies, "
                f"a1={has_a1}, web_session={has_web_session}, "
                f"names={cookie_names}. "
                f"后续搜索可能被风控，建议重新扫码登录"
            )
        else:
            logger.info(
                f"qr-login: cookies OK - {len(cookies)} cookies, "
                f"has a1+web_session"
            )

    session_data = {"cookies": cookies} if cookies else None

    # 4. 关闭 worker 会话，释放浏览器 ctx
    await login_svc.close_session(qr_id)

    # 5. 登录并签发 JWT
    try:
        user_id, token = await _login_and_issue_jwt(
            db, xhs_user_id, nickname, avatar_url, session_data, LoginMethod.QRCODE
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"签发登录令牌失败：{e}（请在 .env 配置 JWT_SECRET_KEY）",
        )

    return StandardResponse(data=_build_login_response(
        user_id, token, xhs_user_id, nickname, avatar_url
    ))


@router.post("/qr-login-manual")
async def qr_login_manual(
    qr_id: str,
    nickname: str,
    red_id: str = "",
    avatar_url: str = "",
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """扫码登录的手动兜底：扫码成功但无法自动获取用户信息时使用。

    不调用 worker 的 fetch_user_info（规避风控），用前端提交的 nickname/red_id 完成登录。
    xhs_user_id 优先用 red_id（小红书号），无 red_id 时用 manual_{qr_id}。
    """
    login_svc = get_login_service()

    # 1. 校验扫码状态
    if qr_id not in _active_sessions:
        raise HTTPException(status_code=400, detail="QR code session not found")

    status_result = await login_svc.check_login_status(qr_id)
    if status_result.get("status") != "confirmed":
        raise HTTPException(
            status_code=400,
            detail=f"QR code not confirmed (status: {status_result.get('status', 'unknown')})",
        )

    nick = (nickname or "").strip()
    if not nick:
        raise HTTPException(status_code=400, detail="昵称不能为空")
    if nick in _FAKE_NICKNAMES:
        raise HTTPException(status_code=400, detail="昵称不合法，请填写真实昵称")

    red = (red_id or "").strip()
    avatar_clean = (avatar_url or "").strip()
    xhs_user_id = red if red else f"manual_{qr_id}"

    # 2. 导出会话 cookies
    try:
        cookies = await login_svc.fetch_cookies(qr_id)
    except RuntimeError as e:
        logger.warning(f"qr-login-manual: failed to fetch cookies: {e}")
        cookies = []

    # 校验 cookies 完整性
    if cookies:
        cookie_names = [c.get("name", "") for c in cookies]
        has_a1 = any("a1" == n for n in cookie_names)
        has_web_session = any("web_session" == n for n in cookie_names)
        if len(cookies) < 5 or not has_a1 or not has_web_session:
            logger.warning(
                f"qr-login-manual: cookies INCOMPLETE - {len(cookies)} cookies, "
                f"a1={has_a1}, web_session={has_web_session}, "
                f"names={cookie_names}"
            )

    session_data = {"cookies": cookies} if cookies else None

    # 3. 关闭 worker 会话
    await login_svc.close_session(qr_id)

    # 4. 登录并签发 JWT
    try:
        user_id, token = await _login_and_issue_jwt(
            db, xhs_user_id, nick, avatar_clean, session_data, LoginMethod.QRCODE
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"签发登录令牌失败：{e}")

    logger.info(f"qr-login-manual: {nick} (uid={xhs_user_id})")
    return StandardResponse(data=_build_login_response(
        user_id, token, xhs_user_id, nick, avatar_clean
    ))


@router.get("/me")
async def get_me(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """返回当前登录用户信息（含绑定的首个小红书账号）。"""
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 取最近使用的小红书账号
    acc_stmt = (
        select(XhsAccount)
        .where(XhsAccount.user_id == user_id)
        .order_by(XhsAccount.last_used_at.desc())
        .limit(1)
    )
    account = await db.scalar(acc_stmt)

    return StandardResponse(data={
        "user_id": user.id,
        "xhs_user_id": account.xhs_user_id if account else "",
        "nickname": account.xhs_nickname if account else "",
        "avatar_url": account.xhs_avatar_url if account else "",
    })


@router.post("/logout")
async def logout() -> StandardResponse[dict]:
    """登出。JWT 无状态，前端清除 token 即可，后端无需额外处理。"""
    return StandardResponse(data={}, message="Logged out")


@router.post("/sse-session")
async def create_sse_session(response: Response) -> StandardResponse[dict]:
    """建立 SSE cookie session。

    下发一个 sse_token cookie，供 EventSource withCredentials 携带。
    SSE 端点（/api/sse/workflow/{id}）会校验此 cookie。
    """
    token = secrets.token_urlsafe(32)
    _sse_tokens.add(token)
    response.set_cookie(
        key="sse_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=3600 * 24,  # 1 天
        path="/",
    )
    return StandardResponse(data={"sse_session": True})


def validate_sse_token(token: str | None) -> bool:
    """校验 SSE cookie token（供 sse router 调用）。"""
    return bool(token and token in _sse_tokens)
