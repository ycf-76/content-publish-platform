"""飞书用户 OAuth 绑定与 user_access_token 管理。"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.feishu import FeishuAPIError
from app.config import get_settings
from app.crypto.token_crypto import TokenCrypto
from app.db.models import FeishuOAuthConnection, FeishuOAuthState

FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def build_pkce() -> tuple[str, str]:
    """返回 code_verifier、S256 code_challenge。"""
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(state: str, code_challenge: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.feishu_app_id,
        "redirect_uri": settings.feishu_oauth_redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": settings.feishu_oauth_scopes,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{FEISHU_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str, code_verifier: str) -> dict:
    settings = get_settings()
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.feishu_app_id,
        "client_secret": settings.feishu_app_secret,
        "code": code,
        "redirect_uri": settings.feishu_oauth_redirect_uri,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(FEISHU_TOKEN_URL, json=payload)
    data = response.json()
    if response.status_code >= 400 or data.get("code", 0) not in (0, None):
        raise FeishuAPIError(
            code=int(data.get("code", response.status_code)),
            msg=str(data.get("error_description") or data.get("msg") or "飞书 OAuth 换 token 失败"),
            api_name="authen.v2.oauth.token",
        )
    if not data.get("access_token"):
        raise FeishuAPIError(-1, "飞书 OAuth 未返回 access_token", "authen.v2.oauth.token")
    return data


async def refresh_user_token(refresh_token: str) -> dict:
    settings = get_settings()
    payload = {
        "grant_type": "refresh_token",
        "client_id": settings.feishu_app_id,
        "client_secret": settings.feishu_app_secret,
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(FEISHU_TOKEN_URL, json=payload)
    data = response.json()
    if response.status_code >= 400 or data.get("code", 0) not in (0, None):
        raise FeishuAPIError(
            code=int(data.get("code", response.status_code)),
            msg=str(data.get("error_description") or data.get("msg") or "飞书 user_access_token 刷新失败"),
            api_name="authen.v2.oauth.token(refresh)",
        )
    return data


async def fetch_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            FEISHU_USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    data = response.json()
    if response.status_code >= 400 or data.get("code", 0) not in (0, None):
        raise FeishuAPIError(
            code=int(data.get("code", response.status_code)),
            msg=str(data.get("msg") or "无法读取飞书用户信息"),
            api_name="authen.v1.user_info",
        )
    return data.get("data") or {}


async def save_connection(
    db: AsyncSession,
    user_id: str,
    token_data: dict,
    user_info: dict,
) -> FeishuOAuthConnection:
    crypto = TokenCrypto()
    now = _utcnow()
    expires_in = int(token_data.get("expires_in") or 7200)
    refresh_expires_in = token_data.get("refresh_token_expires_in")
    result = await db.execute(
        select(FeishuOAuthConnection).where(FeishuOAuthConnection.user_id == user_id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        connection = FeishuOAuthConnection(
            user_id=user_id,
            access_token_encrypted=crypto.encrypt(token_data["access_token"]),
        )
        db.add(connection)
    else:
        connection.access_token_encrypted = crypto.encrypt(token_data["access_token"])
    connection.refresh_token_encrypted = (
        crypto.encrypt(token_data["refresh_token"])
        if token_data.get("refresh_token")
        else connection.refresh_token_encrypted
    )
    connection.access_token_expires_at = now + timedelta(seconds=expires_in)
    if refresh_expires_in is not None:
        connection.refresh_token_expires_at = now + timedelta(seconds=int(refresh_expires_in))
    connection.open_id = user_info.get("open_id") or user_info.get("union_id")
    connection.user_name = user_info.get("name") or user_info.get("en_name") or "飞书用户"
    connection.scopes = token_data.get("scope") or connection.scopes
    connection.updated_at = now
    await db.commit()
    await db.refresh(connection)
    return connection


async def get_valid_user_access_token(db: AsyncSession, user_id: str) -> str | None:
    """取当前用户 token；接近过期时自动用 refresh_token 换新并持久化。"""
    result = await db.execute(
        select(FeishuOAuthConnection).where(FeishuOAuthConnection.user_id == user_id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        return None
    crypto = TokenCrypto()
    access_token = crypto.decrypt(connection.access_token_encrypted)
    expires_at = _as_aware(connection.access_token_expires_at)
    if expires_at is not None and expires_at > _utcnow() + timedelta(minutes=2):
        return access_token
    if not connection.refresh_token_encrypted:
        return None
    refresh_expires_at = _as_aware(connection.refresh_token_expires_at)
    if refresh_expires_at is not None and refresh_expires_at <= _utcnow():
        return None
    token_data = await refresh_user_token(crypto.decrypt(connection.refresh_token_encrypted))
    user_info = await fetch_user_info(token_data["access_token"])
    updated = await save_connection(db, user_id, token_data, user_info)
    return crypto.decrypt(updated.access_token_encrypted)


async def get_connection_status(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(
        select(FeishuOAuthConnection).where(FeishuOAuthConnection.user_id == user_id)
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        return {"connected": False}
    expires_at = _as_aware(connection.access_token_expires_at)
    refresh_expires_at = _as_aware(connection.refresh_token_expires_at)
    return {
        "connected": bool(
            (expires_at is not None and expires_at > _utcnow())
            or (connection.refresh_token_encrypted and (refresh_expires_at is None or refresh_expires_at > _utcnow()))
        ),
        "account": connection.user_name or connection.open_id or "已绑定飞书账号",
        "open_id": connection.open_id,
        "access_token_expires_at": expires_at.isoformat() if expires_at else None,
        "scopes": connection.scopes or "",
    }


async def disconnect(db: AsyncSession, user_id: str) -> None:
    await db.execute(delete(FeishuOAuthConnection).where(FeishuOAuthConnection.user_id == user_id))
    await db.commit()
