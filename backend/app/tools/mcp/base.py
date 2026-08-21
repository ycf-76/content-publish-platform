"""MCP (Model Context Protocol) base class.

Plugin mode: browser plugin (D17 primary).
Local mode: uv run MCP server (fallback).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPConfig:
    """MCP client configuration."""

    mode: str = "local"  # "plugin" | "local"
    plugin_port: int = 8765  # WebSocket port for browser plugin
    local_command: str = "uv run xiaohongshu-mcp"  # Local MCP server command


class MCPClient(ABC):
    """Abstract MCP client.

    Plugin mode: browser plugin (D17).
    Local mode: uv run MCP server.
    """

    @abstractmethod
    async def search_notes(
        self, keyword: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Search Xiaohongshu notes."""
        raise NotImplementedError

    @abstractmethod
    async def publish_note(
        self, title: str, content: str, images_b64: list[str]
    ) -> dict[str, Any]:
        """Publish note to Xiaohongshu."""
        raise NotImplementedError

    @abstractmethod
    async def get_account_info(self, account_id: str) -> dict[str, Any]:
        """Get account info."""
        raise NotImplementedError

    @abstractmethod
    async def get_current_user_info(self) -> dict[str, Any]:
        """Get current logged-in user info using active cookies.

        Must return real user_id / nickname / avatar_url from Xiaohongshu.
        Raise RuntimeError when real info cannot be fetched (do NOT return fake defaults).
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close MCP connection."""
        raise NotImplementedError
