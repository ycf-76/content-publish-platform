"""JWT 认证工具。

负责签发与校验 JWT 令牌，实现无状态用户身份验证。
- create_jwt(user_id)：为指定用户签发 token
- verify_jwt(token)：校验 token 并返回 payload
- decode_user_id(token)：校验 token 并返回 user_id（校验失败抛 401）

密钥与算法从 app.config.Settings 读取（jwt_secret_key / jwt_algorithm / jwt_expire_minutes）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from app.config import get_settings


def create_jwt(user_id: str, extra_claims: dict[str, Any] | None = None) -> str:
    """签发 JWT。

    Args:
        user_id: 用户唯一 ID（写入 sub claim）
        extra_claims: 额外 claims（如 xhs_user_id / nickname），可选

    Returns:
        编码后的 JWT 字符串
    """
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise RuntimeError("jwt_secret_key 未配置，请在 .env 中设置 JWT_SECRET_KEY")

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_jwt(token: str) -> dict[str, Any]:
    """校验 JWT 并返回 payload。

    Raises:
        HTTPException 401: token 无效/过期/未配置密钥
    """
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="jwt_secret_key 未配置",
        )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"无效的登录凭证: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录凭证缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def decode_user_id(token: str) -> str:
    """校验 JWT 并返回 user_id。"""
    return str(verify_jwt(token)["sub"])
