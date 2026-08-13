"""Mock MCP client.

返回固定的小红书笔记数据（10 条 mock）。
不连真实小红书 / 不启动 Playwright。
"""

from __future__ import annotations

from typing import Any

from app.agents.skills.mcp.base import MCPClient


# 10 条 mock 笔记数据
_MOCK_NOTES: list[dict[str, Any]] = [
    {
        "note_id": f"mock_note_{i:02d}",
        "title": f"科技分享 #{i}: AI 工具实测",
        "desc": f"这是第 {i} 篇 mock 笔记的描述内容，模拟小红书爆款内容。",
        "author": f"mock_user_{i}",
        "likes": 1000 + i * 150,
        "comments": 50 + i * 8,
        "url": f"https://www.xiaohongshu.com/explore/mock_note_{i:02d}",
        "cover_img": "",
    }
    for i in range(1, 11)
]


class MockMCPClient(MCPClient):
    """Mock MCP client，返回固定 mock 数据。

    用法：
        client = MockMCPClient()
        await client.connect()  # no-op
        notes = await client.search_notes("科技", 10)
    """

    def __init__(self) -> None:
        self._connected = False
        self._search_count = 0
        self._publish_count = 0

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def search_notes(
        self, keyword: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """返回 mock 笔记列表。"""
        self._search_count += 1
        # 按限截取
        return _MOCK_NOTES[:limit]

    async def get_note_detail(self, note_id: str) -> dict[str, Any]:
        """返回 mock 笔记详情。"""
        for n in _MOCK_NOTES:
            if n["note_id"] == note_id:
                return {
                    **n,
                    "content": f"{n['desc']} 详细内容扩充版。",
                    "images": [],
                    "tags": ["#科技", "#AI", "#工具"],
                }
        return {"note_id": note_id, "title": "", "content": "", "images": [], "tags": []}

    async def publish_note(
        self, title: str, content: str, images: list[bytes]
    ) -> dict[str, Any]:
        """模拟发布成功。"""
        self._publish_count += 1
        return {
            "success": True,
            "post_id": f"mock_post_{self._publish_count:04d}",
            "status": "published",
            "message": "mock 发布成功",
            "url": "https://www.xiaohongshu.com/explore/mock_post",
        }

    async def get_account_info(self, account_id: str) -> dict[str, Any]:
        """返回 mock 账号信息。"""
        return {
            "account_id": account_id,
            "nickname": "mock_user",
            "avatar": "",
            "fans_count": 1234,
            "notes_count": 56,
        }

    async def get_current_user_info(self) -> dict[str, Any]:
        """返回 mock 当前用户信息。"""
        return {
            "xhs_user_id": "mock_xhs_user_001",
            "nickname": "mock_nickname",
            "avatar_url": "",
            "red_id": "mock_red_001",
        }

    async def generate_qrcode(self) -> dict[str, Any]:
        """mock 二维码生成。"""
        return {
            "qr_id": "mock_qr_001",
            "qr_image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        }

    async def check_login_status(self, qr_id: str) -> dict[str, Any]:
        """mock 登录状态检查。"""
        return {"status": "confirmed", "qr_id": qr_id}

    async def close(self) -> None:
        self._connected = False


def install_mock_mcp() -> MockMCPClient:
    """构造 MockMCPClient 实例。"""
    return MockMCPClient()
