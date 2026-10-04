"""飞书用户 OAuth 绑定接口。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.db.models import FeishuOAuthState
from app.db.session import get_db
from app.services.feishu_oauth import (
    build_authorize_url,
    build_pkce,
    disconnect,
    exchange_code,
    fetch_user_info,
    get_connection_status,
    save_connection,
)

router = APIRouter(prefix="/api/feishu/oauth", tags=["Feishu OAuth"])


def _frontend_redirect(status: str, detail: str = "") -> RedirectResponse:
    settings = get_settings()
    query = urlencode({"feishu_oauth": status, **({"detail": detail} if detail else {})})
    return RedirectResponse(f"{settings.feishu_oauth_frontend_url.rstrip('/')}?{query}", status_code=303)


@router.get("/authorize")
async def authorize(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise HTTPException(status_code=503, detail="尚未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
    if not settings.feishu_oauth_redirect_uri:
        raise HTTPException(status_code=503, detail="尚未配置 FEISHU_OAUTH_REDIRECT_URI")

    state = secrets.token_urlsafe(32)
    verifier, challenge = build_pkce()
    db.add(
        FeishuOAuthState(
            state=state,
            user_id=user_id,
            code_verifier=verifier,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
    )
    await db.commit()
    return {"success": True, "authorize_url": build_authorize_url(state, challenge)}


@router.get("/callback")
async def callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    if error:
        return _frontend_redirect("error", error)
    if not code or not state:
        return _frontend_redirect("error", "飞书授权回调缺少 code 或 state")

    result = await db.execute(select(FeishuOAuthState).where(FeishuOAuthState.state == state))
    oauth_state = result.scalar_one_or_none()
    if oauth_state is None or oauth_state.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return _frontend_redirect("error", "授权状态已失效，请重新点击绑定")

    try:
        token_data = await exchange_code(code, oauth_state.code_verifier)
        user_info = await fetch_user_info(token_data["access_token"])
        await save_connection(db, oauth_state.user_id, token_data, user_info)
        await db.delete(oauth_state)
        await db.commit()
        return _frontend_redirect("success")
    except Exception as exc:
        await db.delete(oauth_state)
        await db.commit()
        return _frontend_redirect("error", str(exc)[:180])


@router.get("/status")
async def status(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"success": True, "data": await get_connection_status(db, user_id)}


@router.delete("/connection")
async def remove_connection(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await disconnect(db, user_id)
    return {"success": True, "message": "飞书账号已解绑"}
