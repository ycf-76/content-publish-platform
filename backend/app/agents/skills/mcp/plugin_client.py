"""Plugin MCP client - 通过浏览器扩展调用小红书。

架构：
  后端 PluginMCPClient
    → bridge_state.call_extension(action, payload)   # 内存队列
    → SSE 推送给前端 McpBridgePage
    → chrome.runtime.sendMessage(extensionId, ...)    # 转发给浏览器扩展
    → 扩展 background.js 调小红书页面/接口
    → 扩展返回结果
    → 桥接页面 POST /api/mcp/bridge/result/{call_id}  # 回传结果
    → 后端 future.set_result(...)
    → PluginMCPClient 拿到结果

复用浏览器已登录的小红书会话，零自动化特征，规避服务端 Playwright 风控。

依赖：
1. 用户已安装浏览器扩展（browser_extension/）
2. 用户保持前端 McpBridgePage 标签页打开
3. 用户已在浏览器中登录小红书
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.skills.mcp.base import MCPClient, MCPConfig

logger = logging.getLogger(__name__)


class PluginMCPClient(MCPClient):
    """通过浏览器扩展调小红书的 MCP client。

    与 XhsMCPClient（服务端 Playwright）相比：
    - 优势：复用真实浏览器登录态，无自动化特征，规避风控
    - 劣势：依赖用户保持浏览器和桥接页面打开
    """

    def __init__(self, config: MCPConfig) -> None:
        self.config = config
        self._connected = False

    async def connect(self) -> bool:
        """检测桥接页面是否在线。

        桥接页面通过 /api/mcp/bridge/register 心跳上报自己在线状态。
        """
        try:
            from app.api.routers.mcp_bridge import bridge_state
            self._connected = bridge_state.online
            if self._connected:
                logger.info("PluginMCPClient connected (bridge page online)")
            else:
                logger.warning(
                    "PluginMCPClient connect: 桥接页面未在线。"
                    "请打开 http://localhost:3001/mcp-bridge 页面"
                )
            return self._connected
        except Exception as e:
            logger.warning(f"Plugin MCP connect failed: {e}")
            self._connected = False
            return False

    async def _ensure_connected(self) -> None:
        if not self._connected:
            success = await self.connect()
            if not success:
                raise RuntimeError(
                    "Plugin MCP 桥接页面未在线。"
                    "请在浏览器打开 http://localhost:3001/mcp-bridge 页面"
                    "（需保持该标签页打开 + 安装浏览器扩展 + 已登录小红书）"
                )

    async def _call(self, action: str, payload: dict) -> dict[str, Any]:
        """调用桥接页面 → 扩展。"""
        await self._ensure_connected()
        from app.api.routers.mcp_bridge import bridge_state
        # 桥接页面在线但扩展可能没响应，每次调用都尝试
        result = await bridge_state.call_extension(action, payload)
        if not result.get("success"):
            raise RuntimeError(
                f"Plugin MCP {action} failed: {result.get('message', 'unknown error')}"
            )
        return result.get("data", {})

    async def search_notes(
        self, keyword: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """搜索笔记。失败抛 RuntimeError（让上层 MCPClientManager 的 fallback 逻辑生效）。

        注意：不返回空列表作为失败兜底，否则上层 try/except 永远 catch 不到，
        不会 fallback 到 QR Worker session。
        """
        result = await self._call("search_notes", {"keyword": keyword, "limit": limit})
        if not isinstance(result, list):
            raise RuntimeError(
                f"Plugin MCP search_notes 返回类型错误: 期望 list, 实际 {type(result).__name__}"
            )
        return result

    async def publish_note(
        self, title: str, content: str, images_b64: list[str]
    ) -> dict[str, Any]:
        """通过浏览器扩展在用户真实浏览器里发布小红书笔记。

        扩展会在用户浏览器里打开发布页 tab，操作 DOM 完成发布：
        点"发布笔记"入口 → popover 点"图片上传" → 上传图片 → 填标题/正文 → 点发布。

        与 XhsMCPClient（Playwright headless）相比：
        - 真实浏览器环境，无 webdriver 痕迹，规避风控
        - 复用用户已登录的小红书会话，不需要注入 cookies
        - 符合项目"browser plugin as primary"架构原则

        Args:
            title: 笔记标题（小红书限制 20 字）
            content: 笔记正文
            images_b64: base64 编码的图片列表

        Returns:
            {"success": bool, "message": str, "url": str}
        """
        logger.info(
            f"[Plugin MCP] publish_note: title={title!r}, images={len(images_b64 or [])}"
        )
        try:
            await self._ensure_connected()
            # 直接调扩展，publish_note 返回 {success, message, url?}
            # 注意：不走 _call（_call 要求 success=True 且取 data 字段），
            # publish_note 的结果直接在顶层，透传即可
            from app.api.routers.mcp_bridge import bridge_state
            _subs = len(bridge_state._subscribers)
            logger.info(f"[Plugin MCP] publish_note: bridge subscribers={_subs}, calling call_extension...")
            result = await bridge_state.call_extension(
                "publish_note",
                {
                    "title": title,
                    "content": content,
                    "images_b64": images_b64 or [],
                },
            )
            logger.info(
                f"[Plugin MCP] publish_note result: success={result.get('success')}, "
                f"message={result.get('message', '')}"
            )
            # bridge.js 在 success 时回传 {success: true, data: {success, message, url}}
            # 在 fail 时回传 {success: false, message}
            if result.get("success"):
                data = result.get("data", {})
                return {
                    "success": True,
                    "post_id": "",
                    "message": data.get("message", ""),
                    "url": data.get("url", ""),
                }
            return {
                "success": False,
                "post_id": "",
                "message": result.get("message", ""),
            }
        except Exception as e:
            logger.error(f"[Plugin MCP] publish_note failed: {e}")
            return {
                "success": False,
                "post_id": "",
                "message": str(e),
            }

    async def get_account_info(self, account_id: str) -> dict[str, Any]:
        return await self.get_current_user_info()

    async def get_current_user_info(self) -> dict[str, Any]:
        result = await self._call("get_user_info", {})
        # 校验真实数据（不允许假默认）
        xhs_user_id = (result.get("xhs_user_id") or "").strip()
        nickname = (result.get("nickname") or "").strip()
        if not xhs_user_id or not nickname:
            raise RuntimeError(
                f"Plugin MCP 返回的用户信息不完整: user_id={xhs_user_id!r}, nickname={nickname!r}"
            )
        fake_nicknames = {"xiaohongshu_user", "未命名用户", "小红书用户"}
        if nickname in fake_nicknames:
            raise RuntimeError(f"Plugin MCP 返回假昵称: {nickname!r}")
        return {
            "xhs_user_id": xhs_user_id,
            "nickname": nickname,
            "avatar_url": (result.get("avatar_url") or "").strip(),
            "red_id": (result.get("red_id") or "").strip(),
        }

    async def close(self) -> None:
        self._connected = False
        logger.info("PluginMCPClient connection closed")