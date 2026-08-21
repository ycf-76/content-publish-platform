"""Base LLM adapter protocol.

Phase 3 concrete adapters (DeepSeek, Qwen-VL, ImageGen) implement this.

P0 并发控制：全局 Semaphore 限制同时进行的 LLM API 调用数，
防止多工作流并发时触发 API 429 限速雪崩。
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

LLM_CONCURRENCY_LIMIT = 5
_llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY_LIMIT)


class BaseLLM(ABC):
    """Abstract base for all LLM model adapters.

    Red line: All LLM calls go through adapters (Phase 3).
    Harness layer must not call LLM directly.

    P0: chat / stream_chat 外层包 Semaphore，确保同时最多
    LLM_CONCURRENCY_LIMIT 个 LLM API 调用在飞。
    """

    model_name: str

    @abstractmethod
    async def _chat_impl(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """子类实现：实际 LLM 调用逻辑。"""
        raise NotImplementedError

    @abstractmethod
    async def _stream_chat_impl(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """子类实现：实际 LLM 流式调用逻辑。"""
        raise NotImplementedError

    async def chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat, wrapped with concurrency semaphore.

        Returns: {"content": str, "reasoning_content": str | None, "token_usage": int}
        """
        async with _llm_semaphore:
            logger.debug(
                f"[llm_semaphore] acquired ({LLM_CONCURRENCY_LIMIT - _llm_semaphore._value}/{LLM_CONCURRENCY_LIMIT}), "
                f"model={getattr(self, 'model_name', '?')}"
            )
            return await self._chat_impl(messages, response_format)

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming chat, wrapped with concurrency semaphore.

        Yields: {"content": str | None, "reasoning_content": str | None,
                "is_final": bool, "token_usage": int | None}
        """
        async with _llm_semaphore:
            logger.debug(
                f"[llm_semaphore] acquired ({LLM_CONCURRENCY_LIMIT - _llm_semaphore._value}/{LLM_CONCURRENCY_LIMIT}), "
                f"model={getattr(self, 'model_name', '?')}"
            )
            async for chunk in self._stream_chat_impl(messages, response_format):
                yield chunk


class ChatMessage(BaseModel):
    """Standardized chat message format."""

    role: str
    content: str | list[dict[str, Any]]  # Can be plain text or multimodal content


class LLMConfig(BaseModel):
    """Common LLM configuration."""

    model_name: str
    temperature: float = 0.7
    max_tokens: int = 2000
    top_p: float = 1.0