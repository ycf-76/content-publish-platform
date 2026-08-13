"""Base LLM adapter protocol.

Phase 3 concrete adapters (DeepSeek, Qwen-VL, ImageGen) implement this.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel


class BaseLLM(ABC):
    """Abstract base for all LLM model adapters.

    Red line: All LLM calls go through adapters (Phase 3).
    Harness layer must not call LLM directly.
    """

    model_name: str

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat.

        Returns: {"content": str, "reasoning_content": str | None, "token_usage": int}
        """
        raise NotImplementedError

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming chat.

        Yields: {"content": str | None, "reasoning_content": str | None,
                "is_final": bool, "token_usage": int | None}
        """
        raise NotImplementedError


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
