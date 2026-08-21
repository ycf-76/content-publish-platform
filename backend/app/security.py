"""JWT 认证工具。

负责签发与校验 JWT 令牌，实现无状态用户身份验证。
- create_jwt(user_id)：为指定用户签发 access token
- create_refresh_token(user_id)：签发 refresh token（P1-6：7天有效期）
- verify_jwt(token)：校验 access token 并返回 payload
- verify_refresh_token(token)：校验 refresh token 并返回 payload
- decode_user_id(token)：校验 token 并返回 user_id（校验失败抛 401）

P1-6：Access Token 30分钟过期 + Refresh Token 7天过期。
前端 401 时用 refresh_token 静默刷新，用户无感知。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from app.config import get_settings


def create_jwt(user_id: str, extra_claims: dict[str, Any] | None = None) -> str:
    """签发 Access Token（30分钟过期）。

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
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """签发 Refresh Token（7天过期，仅用于刷新 access token）。

    P1-6：Refresh Token 不包含业务 claims，仅用于换取新 access token。
    """
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise RuntimeError("jwt_secret_key 未配置")

    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days)
    payload: dict[str, Any] = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_jwt(token: str) -> dict[str, Any]:
    """校验 Access Token 并返回 payload。

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

    # P1-6：refresh token 不能当 access token 用
    if payload.get("type") == "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请使用 access token 访问接口，refresh token 仅用于刷新",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def verify_refresh_token(token: str) -> dict[str, Any]:
    """校验 Refresh Token 并返回 payload。

    Raises:
        HTTPException 401: token 无效/过期/类型错误
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
            detail=f"Refresh token 无效或已过期: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="该端点仅接受 refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def decode_user_id(token: str) -> str:
    """校验 JWT 并返回 user_id。"""
    return str(verify_jwt(token)["sub"])