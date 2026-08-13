"""账号服务（D1 分层登录）。

管理小红书账号绑定、登录态分层、Token 加密存储。

红线 3.3：登录态优先级——插件优先 → Session 刷新 → 扫码兜底。
红线 7.1：User:Account = 1:N，DB 层面支持多账号。
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto.token_crypto import TokenCrypto
from app.db.models import AccountStatus, LoginMethod, XhsAccount
from app.account.login_service import get_login_service

logger = logging.getLogger(__name__)


class AccountService:
    """小红书账号管理服务。

    实现分层登录：
    1. 浏览器插件登录态（首选，无需扫码）
    2. 已存储Session自动刷新（次选）
    3. 扫码登录（兜底）
    """

    def __init__(self, db: AsyncSession, token_crypto: TokenCrypto | None = None) -> None:
        self.db = db
        self.crypto = token_crypto or TokenCrypto()

    async def check_plugin_status(self) -> dict[str, Any]:
        """检查浏览器插件 MCP 是否在线。

        判断逻辑（轻量级，不调扩展 get_user_info，避免 content script 链路失败导致一直卡二维码）：
        1. 桥接页面在线（bridge_state.online）→ bridge_online
        2. 桥接能调通扩展 health（含 cookie 登录态）→ online + logged_in
        详细用户信息在 bind-plugin 时再去拿，失败就报错给前端。
        """
        try:
            from app.api.routers.mcp_bridge import bridge_state

            bridge_online = bridge_state.online
            if not bridge_online:
                return {
                    "online": False,
                    "bridge_online": False,
                    "message": "桥接页面未打开，请访问 http://localhost:3001/mcp-bridge 并保持标签页打开",
                }

            # 通过桥接页面调扩展 health（不依赖 content script）
            try:
                result = await bridge_state.call_extension("health", {})
            except Exception as e:
                return {
                    "online": False,
                    "bridge_online": True,
                    "message": f"调扩展 health 失败：{e}",
                }

            if not result.get("success"):
                return {
                    "online": False,
                    "bridge_online": True,
                    "message": f"扩展未响应：{result.get('message', 'unknown')}",
                }

            data = result.get("data", {})
            logged_in = bool(data.get("logged_in"))
            return {
                "online": True,
                "bridge_online": True,
                "logged_in": logged_in,
                "cookies_count": data.get("cookies_count", 0),
                "message": "插件在线" + ("，已登录" if logged_in else "，未登录小红书"),
            }
        except Exception as e:
            return {
                "online": False,
                "message": f"检测插件状态失败：{e}",
            }

    async def generate_qrcode(self) -> dict[str, Any]:
        """生成登录二维码（通过 worker HTTP 调 Playwright）"""
        login_service = get_login_service()
        result = await login_service.generate_qrcode()
        if not result.get("qrcode_base64"):
            raise RuntimeError("Worker 返回空二维码")
        logger.info(f"Generated QR code: {result['qr_id']}, has_base64=True")
        return result

    async def poll_qr_status(self, qr_id: str) -> dict[str, Any]:
        """轮询二维码状态（通过 worker HTTP）"""
        login_service = get_login_service()
        result = await login_service.check_login_status(qr_id)
        return result

    async def confirm_login(self, qr_id: str) -> dict[str, Any]:
        """确认登录（通过 worker HTTP 检测真实状态）"""
        login_service = get_login_service()
        result = await login_service.confirm_login(qr_id)
        return result

    async def bind_account(
        self,
        user_id: str,
        xhs_user_id: str,
        nickname: str,
        avatar_url: str | None,
        session_data: dict[str, Any] | None = None,
        refresh_token: str | None = None,
        login_method: LoginMethod = LoginMethod.QRCODE,
    ) -> XhsAccount:
        """绑定小红书账号。"""
        stmt = select(XhsAccount).where(
            XhsAccount.user_id == user_id,
            XhsAccount.xhs_user_id == xhs_user_id,
        )
        existing = await self.db.scalar(stmt)

        if existing:
            existing.xhs_nickname = nickname
            existing.xhs_avatar_url = avatar_url
            existing.status = AccountStatus.ACTIVE
            existing.login_method = login_method
            existing.last_used_at = datetime.now(UTC)

            if session_data:
                existing.session_data_encrypted = self.crypto.encrypt_dict(session_data)
            if refresh_token:
                existing.refresh_token_encrypted = self.crypto.encrypt(refresh_token)

            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        account = XhsAccount(
            user_id=user_id,
            xhs_user_id=xhs_user_id,
            xhs_nickname=nickname,
            xhs_avatar_url=avatar_url,
            login_method=login_method,
            status=AccountStatus.ACTIVE,
            last_used_at=datetime.now(UTC),
        )

        if session_data:
            account.session_data_encrypted = self.crypto.encrypt_dict(session_data)
        if refresh_token:
            account.refresh_token_encrypted = self.crypto.encrypt(refresh_token)

        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        
        logger.info(f"Account bound: {account.id} for user {user_id}")
        return account

    async def list_accounts(self, user_id: str) -> list[XhsAccount]:
        """列出用户的所有账号。"""
        stmt = (
            select(XhsAccount)
            .where(XhsAccount.user_id == user_id)
            .order_by(XhsAccount.last_used_at.desc())
        )
        result = await self.db.scalars(stmt)
        accounts = list(result.all())
        logger.info(f"List accounts for user {user_id}: {len(accounts)} accounts")
        return accounts

    async def refresh_session(self, account_id: str, user_id: str) -> dict[str, Any]:
        """刷新账号Session：用已存储的 cookies 调 MCP 验证有效性并更新用户信息。"""
        stmt = select(XhsAccount).where(
            XhsAccount.id == account_id,
            XhsAccount.user_id == user_id,
        )
        account = await self.db.scalar(stmt)

        if not account:
            return {"success": False, "message": "账号不存在"}

        # Decrypt stored session cookies
        if not account.session_data_encrypted:
            account.status = AccountStatus.EXPIRED
            await self.db.commit()
            return {"success": False, "message": "无已存储的会话数据，账号已标记为过期"}

        try:
            session_data = self.crypto.decrypt_dict(account.session_data_encrypted)
        except Exception as e:
            logger.warning(f"Failed to decrypt session for account {account_id}: {e}")
            account.status = AccountStatus.EXPIRED
            await self.db.commit()
            return {"success": False, "message": "会话数据解密失败，账号已标记为过期"}

        # session_data 是 {"cookies": [list[dict]]}（Playwright export 格式）
        cookies = (
            session_data.get("cookies", [])
            if isinstance(session_data, dict)
            else session_data
        )
        if not cookies:
            account.status = AccountStatus.EXPIRED
            await self.db.commit()
            return {"success": False, "message": "会话数据为空，账号已标记为过期"}

        # Sync cookies to MCP client and verify by fetching real user info
        from app.agents.skills.mcp.xhs_client import sync_cookies_to_local_client

        sync_cookies_to_local_client(cookies)

        try:
            from app.agents.skills.mcp.xhs_client import mcp_manager
            real_info = await mcp_manager.get_current_user_info()
            account.xhs_user_id = real_info["xhs_user_id"]
            account.xhs_nickname = real_info["nickname"]
            account.xhs_avatar_url = real_info.get("avatar_url", "") or account.xhs_avatar_url
            account.status = AccountStatus.ACTIVE
            account.last_used_at = datetime.now(UTC)
            await self.db.commit()
            logger.info(f"Session refreshed for account {account_id}: {real_info['nickname']}")
            return {
                "success": True,
                "message": "会话刷新成功",
                "nickname": real_info["nickname"],
                "avatar_url": real_info.get("avatar_url", ""),
            }
        except Exception as e:
            logger.warning(f"Session refresh failed for account {account_id}: {e}")
            account.status = AccountStatus.EXPIRED
            await self.db.commit()
            return {"success": False, "message": f"会话已失效，账号已标记为过期: {e}"}

    async def unbind_account(self, account_id: str, user_id: str) -> dict[str, Any]:
        """解绑账号。"""
        stmt = select(XhsAccount).where(
            XhsAccount.id == account_id,
            XhsAccount.user_id == user_id,
        )
        account = await self.db.scalar(stmt)

        if not account:
            return {"success": False, "message": "账号不存在"}

        await self.db.delete(account)
        await self.db.commit()

        logger.info(f"Account unbound: {account_id}")
        return {"success": True, "message": "解绑成功"}


def get_account_service(db: AsyncSession) -> AccountService:
    """获取账号服务实例。"""
    return AccountService(db)