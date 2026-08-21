"""XHS MCP client implementation.

Implements MCPClient interface using plugin or local mode.
D17: 双模式架构 - 插件 MCP（生产首选） + 本地 MCP（开发/兜底）
"""

from __future__ import annotations

import logging
from datetime import UTC
from typing import Any

from app.tools.mcp.base import MCPClient, MCPConfig

logger = logging.getLogger(__name__)


class XhsMCPClient(MCPClient):
    """XHS MCP client implementation.

    Supports plugin mode (production) and local mode (dev fallback).
    """

    def __init__(self, config: MCPConfig) -> None:
        self.config = config
        self._client = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to MCP server."""
        try:
            if self.config.mode == "plugin":
                return await self._connect_plugin()
            elif self.config.mode == "local":
                return await self._connect_local()
            else:
                raise ValueError(f"Unknown MCP mode: {self.config.mode}")
        except Exception as e:
            logger.error(f"MCP connection failed: {e}")
            return False

    async def _connect_plugin(self) -> bool:
        """Connect to browser plugin MCP.

        浏览器插件通过 WebSocket 连接，复用用户登录态。
        MVP 阶段返回 False，等待插件集成。
        """
        logger.info("Attempting to connect to browser plugin MCP...")
        # TODO: 实现 WebSocket 连接到浏览器插件
        # 插件会暴露一个 WebSocket 服务，端口可通过配置指定
        # 连接后可以调用小红书的搜索、发布等 API

        # MVP: 返回 False，表示插件未就绪
        logger.warning("Plugin MCP not implemented yet, will fall back to local mode")
        return False

    async def _connect_local(self) -> bool:
        """Connect to local MCP server (uv run).

        本地模式使用社区项目 xiaohongshu-mcp-py，
        通过 uv run 启动 MCP server。
        """
        logger.info("Attempting to connect to local MCP server...")

        # TODO: 实现 uv run 启动本地 MCP server
        # 需要安装 xiaohongshu-mcp-py 并配置环境变量

        # MVP: 模拟连接成功
        self._connected = True
        logger.info("Local MCP connected (mock)")
        return True

    async def _ensure_connected(self) -> None:
        """Ensure MCP client is connected."""
        if not self._connected:
            success = await self.connect()
            if not success:
                raise RuntimeError("MCP client not connected")

    async def search_notes(
        self, keyword: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Search notes with rate limiting."""
        await self._ensure_connected()

        logger.info(f"Searching notes: keyword={keyword}, limit={limit}")

        # MVP: 返回模拟数据
        # TODO: 调用真实 MCP 服务
        mock_results = []
        for i in range(min(limit, 5)):
            mock_results.append({
                "note_id": f"note_{i}_{hash(keyword) % 10000}",
                "title": f"关于 {keyword} 的爆款笔记 #{i+1}",
                "desc": f"这是一篇关于 {keyword} 的高质量内容...",
                "author": f"博主_{i+1}",
                "likes": 1000 + i * 200,
                "comments": 50 + i * 10,
                "url": f"https://www.xiaohongshu.com/explore/note_{i}",
            })

        return mock_results

    async def get_note_detail(self, note_id: str) -> dict[str, Any]:
        """Get note detail."""
        await self._ensure_connected()

        logger.info(f"Getting note detail: {note_id}")

        # MVP: 返回模拟数据
        return {
            "note_id": note_id,
            "title": "爆款笔记标题",
            "content": "详细的笔记内容...",
            "images": ["https://via.placeholder.com/400x300"],
            "tags": ["#话题标签"],
        }

    async def publish_note(
        self, title: str, content: str, images_b64: list[str]
    ) -> dict[str, Any]:
        """Publish note to Xiaohongshu."""
        await self._ensure_connected()

        logger.info(f"Publishing note: title={title}, images={len(images_b64)}")

        # MVP: 模拟发布成功
        # TODO: 调用真实 MCP 发布 API
        return {
            "success": True,
            "post_id": f"post_{hash(title) % 10000}",
            "url": "https://www.xiaohongshu.com/explore/mock_post",
        }

    async def get_account_info(self, account_id: str) -> dict[str, Any]:
        """Get account info."""
        await self._ensure_connected()

        logger.info(f"Getting account info: {account_id}")

        # MVP: 返回模拟数据
        return {
            "account_id": account_id,
            "nickname": "测试账号",
            "avatar": "https://via.placeholder.com/100",
            "fans_count": 10000,
            "notes_count": 50,
        }

    async def generate_qrcode(self) -> dict[str, Any]:
        """Generate QR code for login.

        Returns:
            {
                "qr_id": str,
                "qr_url": str,
                "expires_at": str
            }
        """
        await self._ensure_connected()

        logger.info("Generating QR code for login")

        # MVP: 返回模拟二维码
        # TODO: 调用真实 MCP 登录 API
        import secrets
        from datetime import datetime, timedelta

        qr_id = f"qr_{secrets.token_urlsafe(16)}"
        return {
            "qr_id": qr_id,
            "qr_url": f"xhs://login?qr_id={qr_id}",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }

    async def check_login_status(self, qr_id: str) -> dict[str, Any]:
        """Check login status for QR code.

        Returns:
            {
                "status": "pending" | "scanned" | "confirmed" | "expired",
                "user_info": dict | None
            }
        """
        await self._ensure_connected()

        # MVP: 返回 pending 状态
        # TODO: 调用真实 MCP 状态查询 API
        return {
            "status": "pending",
            "user_info": None,
        }

    async def close(self) -> None:
        """Close MCP connection."""
        self._connected = False
        logger.info("MCP connection closed")


class MCPClientManager:
    """Manages MCP clients (plugin + local) with degradation.

    D17: 双模式自动降级
    """

    def __init__(self) -> None:
        self._plugin_client: XhsMCPClient | None = None
        self._local_client: XhsMCPClient | None = None
        self._fallback_to_local: bool = False

    def set_plugin_client(self, client: XhsMCPClient) -> None:
        """Set plugin MCP client (primary)."""
        self._plugin_client = client

    def set_local_client(self, client: XhsMCPClient) -> None:
        """Set local MCP client (fallback)."""
        self._local_client = client

    async def search_notes(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search notes with degradation."""
        if not self._fallback_to_local and self._plugin_client:
            try:
                return await self._plugin_client.search_notes(keyword, limit)
            except Exception as e:
                logger.warning(f"Plugin MCP failed: {e}, falling back to local")
                self._fallback_to_local = True

        if self._local_client:
            return await self._local_client.search_notes(keyword, limit)

        raise RuntimeError("No MCP client available")

    async def publish_note(
        self, title: str, content: str, images_b64: list[str]
    ) -> dict[str, Any]:
        """Publish note with degradation."""
        if not self._fallback_to_local and self._plugin_client:
            try:
                return await self._plugin_client.publish_note(title, content, images_b64)
            except Exception as e:
                logger.warning(f"Plugin MCP failed: {e}, falling back to local")
                self._fallback_to_local = True

        if self._local_client:
            return await self._local_client.publish_note(title, content, images_b64)

        raise RuntimeError("No MCP client available")


# 全局 MCP 客户端管理器
mcp_manager = MCPClientManager()


async def init_mcp_clients() -> None:
    """Initialize MCP clients on startup."""
    from app.config import get_settings

    settings = get_settings()

    # 初始化本地 MCP 客户端（兜底）
    local_config = MCPConfig(mode="local")
    local_client = XhsMCPClient(local_config)
    mcp_manager.set_local_client(local_client)

    # 初始化插件 MCP 客户端（首选）
    if settings.mcp_plugin_enabled:
        plugin_config = MCPConfig(mode="plugin")
        plugin_client = XhsMCPClient(plugin_config)
        mcp_manager.set_plugin_client(plugin_client)

    logger.info("MCP clients initialized")
