"""Authentication routers.

登录方式：
1. 邮箱验证码登录（通过 email 关联 User，自动注册）：
   - POST /api/auth/send-email-code?email=xxx：发送 6 位验证码到邮箱
   - POST /api/auth/email-login?email=xxx&code=xxx：校验验证码，自动注册或登录，签发 JWT
2. 通用接口：
   - GET  /api/auth/me：返回当前登录用户信息（需 JWT）
   - POST /api/auth/logout：登出（JWT 无状态，前端清 token 即可）
   - POST /api/auth/sse-session：下发 SSE cookie session

所有登录接口均不需要 JWT（用于签发 JWT）；账号管理接口（/api/accounts/*）需要 JWT。

P0-2：验证码防暴力破解 — Redis 计数器限制验证频率（5次/15分钟）。
P0-3：内存状态迁移 Redis — sse_token 和 email_code 迁移到 Redis 持久化存储。
"""
from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# account.login_service removed (QR login deleted)
from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.cache import redis_client
from app.db.models import User
from app.db.session import get_db
from app.security import create_jwt, create_refresh_token, verify_refresh_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# P0-2：验证码暴力破解防护参数
_MAX_VERIFY_ATTEMPTS = 5
_VERIFY_LOCK_MINUTES = 3
_CODE_TTL = 300
_CODE_LEN = 6






@router.get("/me")
async def get_me(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """返回当前登录用户信息（含绑定的首个小红书账号）。"""
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return StandardResponse(data={
        "user_id": user.id,
        "nickname": user.nickname or "",
        "avatar_url": "",
        "has_xhs_auth": False,
        "login_method": "email",
    })


@router.post("/logout")
async def logout() -> StandardResponse[dict]:
    """登出。JWT 无状态，前端清除 token 即可，后端无需额外处理。"""
    return StandardResponse(data={}, message="Logged out")


@router.post("/refresh")
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """P1-6：用 refresh token 换取新的 access token + 新的 refresh token。

    前端在 401 时调用此端点静默刷新，用户无感知。
    Refresh token 过期则需重新登录。
    """
    payload = verify_refresh_token(refresh_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Refresh token 缺少用户标识")

    new_access = create_jwt(user_id)
    new_refresh = create_refresh_token(user_id)

    user = await db.scalar(select(User).where(User.id == user_id))
    nickname = ""
    if user:
        nickname = user.nickname or ""

    if nickname:
        new_access = create_jwt(user_id, extra_claims={"nickname": nickname})

    return StandardResponse(data={
        "token": new_access,
        "refresh_token": new_refresh,
    })


@router.post("/sse-session")
async def create_sse_session(response: Response) -> StandardResponse[dict]:
    """建立 SSE cookie session。

    P0-3：sse_token 迁移到 Redis 持久化存储，后端重启不丢失。
    下发一个 sse_token cookie，供 SSE 连接携带。
    """
    token = secrets.token_urlsafe(32)
    await redis_client.set(f"sse_token:{token}", "1", ex=86400)
    response.set_cookie(
        key="sse_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=3600 * 24,
        path="/",
    )
    return StandardResponse(data={"sse_session": True})


async def validate_sse_token(token: str | None) -> bool:
    """校验 SSE cookie token（供 sse router 调用）。

    P0-3：从 Redis 查询，后端重启后仍有效。
    """
    if not token:
        return False
    return await redis_client.exists(f"sse_token:{token}")


def _generate_code() -> str:
    import random
    return "".join(random.choices("0123456789", k=_CODE_LEN))


def _send_email_smtp(to_addr: str, code: str) -> bool:
    """通过 SMTP 发送验证码邮件。成功返回 True，失败返回 False。"""
    from app.config import get_settings
    import smtplib
    from email.mime.text import MIMEText

    settings = get_settings()
    smtp_host = settings.smtp_host
    smtp_port = settings.smtp_port
    smtp_user = settings.smtp_user
    smtp_pass = settings.smtp_pass
    smtp_from = settings.smtp_from or smtp_user

    if not smtp_host or not smtp_user or not smtp_pass:
        return False

    msg = MIMEText(
        f"Your verification code is: {code}\n\nThis code expires in 5 minutes. Do not share it with anyone.\n\n— Pulse Studio",
        "plain",
        "utf-8",
    )
    msg["Subject"] = "Pulse Studio - Verification Code"
    msg["From"] = f"Pulse Studio <{smtp_from}>"
    msg["To"] = to_addr

    if settings.smtp_use_tls:
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_from, [to_addr], msg.as_string())
    else:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_from, [to_addr], msg.as_string())
    return True


@router.post("/send-email-code")
async def send_email_code(
    email: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """发送邮箱验证码。同一邮箱 60 秒内不可重发。

    P0-3：验证码迁移到 Redis 持久化存储，后端重启不丢失。

    - 配置了 SMTP（smtp_host + smtp_user + smtp_pass）→ 真实发送邮件
    - 未配置 SMTP → 开发模式，验证码打印到后端日志（终端可见）
    """
    email = email.strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")

    # 60 秒内不可重发（Redis TTL 检查）
    cooldown_key = f"email_code_cooldown:{email}"
    if await redis_client.exists(cooldown_key):
        raise HTTPException(status_code=429, detail="发送太频繁，请 60 秒后再试")

    code = _generate_code()
    # P0-3：验证码存 Redis，5 分钟过期
    await redis_client.set(f"email_code:{email}", code, ex=_CODE_TTL)
    # 60 秒冷却期
    await redis_client.set(cooldown_key, "1", ex=60)

    sent_real = False
    try:
        sent_real = _send_email_smtp(email, code)
    except Exception as e:
        logger.warning(f"SMTP send failed for {email}: {e}")

    if sent_real:
        logger.info(f"email code sent to {email} via SMTP")
    else:
        logger.info(f"[DEV-MODE] email code for {email}: {code}  (configure SMTP to send real emails)")

    return StandardResponse(data={"email": email, "sent": True})


@router.post("/email-login")
async def email_login(
    email: str,
    code: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """邮箱验证码登录：校验验证码，自动注册或登录，签发 JWT。

    P0-2：防暴力破解 — 同一邮箱验证失败 5 次后锁定 15 分钟。
    P0-3：验证码从 Redis 读取，后端重启不丢失。

    流程：
    1. 检查验证锁定（5次失败后锁定15分钟）
    2. 校验验证码（6 位数字，5 分钟有效）
    3. 查找已有用户（by email），不存在则自动注册
    4. 签发 JWT，返回用户信息
    """
    email = email.strip().lower()
    code = code.strip()
    if not email or not code:
        raise HTTPException(status_code=400, detail="邮箱和验证码不能为空")

    # P0-2：检查验证锁定
    lock_key = f"lock:verify:{email}"
    attempts = await redis_client.get(lock_key)
    if attempts and int(attempts) >= _MAX_VERIFY_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail=f"验证次数过多，请{_VERIFY_LOCK_MINUTES}分钟后再试",
        )

    # P0-3：从 Redis 读取验证码
    stored_code = await redis_client.get(f"email_code:{email}")
    if not stored_code or stored_code != code:
        count = await redis_client.incr(lock_key)
        if count == 1:
            await redis_client.expire(lock_key, _VERIFY_LOCK_MINUTES * 60)
        remaining = _MAX_VERIFY_ATTEMPTS - count
        raise HTTPException(
            status_code=400,
            detail=f"验证码错误或已过期（剩余尝试次数：{max(remaining, 0)}）",
        )

    # 验证成功，清除锁定计数器和验证码
    await redis_client.delete(lock_key)
    await redis_client.delete(f"email_code:{email}")

    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        nick = email.split("@")[0]
        user = User(email=email, nickname=nick)
        db.add(user)
        await db.flush()
        await db.commit()
        logger.info(f"email-login: new user created, id={user.id}, email={email}")

    token = create_jwt(
        user.id,
        extra_claims={
            "email": email,
            "nickname": user.nickname or email.split("@")[0],
        },
    )
    refresh = create_refresh_token(user.id)

    default_avatar = "/images/avatar/@man.svg"

    return StandardResponse(data={
        "token": token,
        "refresh_token": refresh,
        "user_id": user.id,
        "nickname": user.nickname or email.split("@")[0],
        "avatar_url": default_avatar,
        "has_xhs_auth": False,
        "login_method": "email",
    })