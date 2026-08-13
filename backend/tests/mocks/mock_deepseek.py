"""Mock DeepSeek adapter.

返回固定 LLM 响应（含 reasoning_content 模拟 R1）。
不连真实 DeepSeek API。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.adapters.llm_base import BaseLLM


# 固定的 LLM 响应模板（按节点 node_id / 角色匹配）
_MOCK_RESPONSES: dict[str, dict[str, Any]] = {
    "search": {
        "content": '{"final": true, "output": {"results": [{"note_id": "mock_1", "title": "mock 笔记", "likes": 1000}], "count": 1, "summary": "mock search result"}}',
        "reasoning_content": "搜索关键词已生成，准备调用 xhs_search 工具",
        "token_usage": 120,
    },
    "analyze": {
        "content": '{"factors": {"color": "暖色调", "composition": "俯拍", "topic": "手冲咖啡"}}',
        "reasoning_content": "分析爆款因子：颜色 + 构图 + 主题",
        "token_usage": 200,
    },
    "copywrite": {
        "content": '{"title": "今日分享", "content": "这是 mock 文案内容", "tags": ["#mock", "#test"]}',
        "reasoning_content": "思考标题吸引力，构造文案结构，挑选标签",
        "token_usage": 350,
    },
    "audit": {
        "content": '{"passed": true, "issues": []}',
        "reasoning_content": "审核：无敏感词，无违规内容",
        "token_usage": 80,
    },
    "publish": {
        "content": '{"final": true, "output": {"post_id": "mock_post_001", "status": "published", "message": "发布成功"}}',
        "reasoning_content": "调用 xhs_publish 工具完成发布",
        "token_usage": 50,
    },
    "default": {
        "content": '{"result": "mock"}',
        "reasoning_content": None,
        "token_usage": 100,
    },
}


class MockDeepSeekAdapter(BaseLLM):
    """Mock DeepSeek adapter（支持 V3 / R1 模式）。

    用法：
        adapter = MockDeepSeekAdapter(model="deepseek-chat")
        # 或 R1 模式
        adapter = MockDeepSeekAdapter(model="deepseek-reasoner")
    """

    def __init__(self, model: str = "deepseek-chat") -> None:
        self.model = model
        self._call_count = 0

    @property
    def model_name(self) -> str:
        return self.model

    def _pick_response(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """根据 messages 内容选合适的 mock 响应。"""
        self._call_count += 1
        # 扫描 messages 找 node_id / 主题词
        text = ""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                text += content + "\n"
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text += str(item.get("text", "")) + "\n"

        text_lower = text.lower()
        for keyword in ("search", "analyze", "copywrite", "audit", "publish"):
            if keyword in text_lower:
                resp = _MOCK_RESPONSES[keyword]
                break
        else:
            resp = _MOCK_RESPONSES["default"]

        # R1 模式下保留 reasoning_content，V3 模式下置 None
        if "r1" in self.model.lower() or "reasoner" in self.model.lower():
            return dict(resp)
        return {**resp, "reasoning_content": None}

    async def chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """非流式 chat，返回固定响应。"""
        return self._pick_response(messages)

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式 chat，分两段 yield（content + reasoning_content + final）。"""
        resp = self._pick_response(messages)
        # 第一段：reasoning_content（R1 模式才有）
        if resp.get("reasoning_content"):
            yield {
                "content": None,
                "reasoning_content": resp["reasoning_content"],
                "is_final": False,
                "token_usage": None,
            }
        # 第二段：content
        yield {
            "content": resp["content"],
            "reasoning_content": None,
            "is_final": False,
            "token_usage": None,
        }
        # 终止帧
        yield {
            "content": None,
            "reasoning_content": None,
            "is_final": True,
            "token_usage": resp["token_usage"],
        }


def install_mock_deepseek() -> MockDeepSeekAdapter:
    """构造 MockDeepSeekAdapter 实例。

    用法：
        from tests.mocks.mock_deepseek import install_mock_deepseek
        adapter = install_mock_deepseek()
        # 然后 monkeypatch factory.get_deepseek_llm 返回 adapter
    """
    return MockDeepSeekAdapter(model="deepseek-chat")
