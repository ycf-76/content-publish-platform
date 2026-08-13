"""Mock Qwen-VL adapter.

返回固定图片标签。
不连真实 DashScope API。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.adapters.llm_base import BaseLLM


# 固定图片标签（按输入 base64 头几个字节做轻微区分，保证可重复）
_DEFAULT_TAGS = ["暖色调", "俯拍", "手冲咖啡", "极简构图", "生活感"]


class MockQwenVLAdapter(BaseLLM):
    """Mock Qwen-VL adapter。

    用法：
        adapter = MockQwenVLAdapter()
    """

    def __init__(self, model: str = "qwen-vl-max") -> None:
        self.model = model
        self._call_count = 0

    @property
    def model_name(self) -> str:
        return self.model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """返回固定图片标签。"""
        self._call_count += 1
        import json

        content = json.dumps({"tags": _DEFAULT_TAGS, "confidence": 0.92})
        return {
            "content": content,
            "reasoning_content": None,
            "token_usage": 80,
        }

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Qwen-VL mock 不支持流式，fallback 到非流式。"""
        result = await self.chat(messages, response_format)
        yield {
            "content": result["content"],
            "reasoning_content": None,
            "is_final": True,
            "token_usage": result["token_usage"],
        }


def install_mock_qwen_vl() -> MockQwenVLAdapter:
    """构造 MockQwenVLAdapter 实例。"""
    return MockQwenVLAdapter()
