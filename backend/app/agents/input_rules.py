"""Chat 输入守卫规则（守卫层）。

对 Chat 输入做 prompt injection 过滤、长度限制、敏感词校验。
红线：这是「守卫」，不是「理解」。意图解析由 `IntentParser` 负责。
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.core.schemas import HardRule, WorkflowContext

MAX_INPUT_LENGTH = 10000

_PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now",
    r"system\s*:",
    r"<\|im_start\|>",
]

# 敏感词列表：按业务补充，这里仅保留占位。
_SENSITIVE_WORDS: tuple[str, ...] = ()


class ChatInputRule(HardRule):
    """Chat 输入守卫：长度 + prompt injection + 敏感词。"""

    name = "chat_input_guard"

    async def check_pre(self, input: dict[str, Any], context: WorkflowContext) -> bool:
        message = str(input.get("message", "")).strip()
        if not message:
            return False
        if len(message) > MAX_INPUT_LENGTH:
            return False
        if self._contains_injection(message):
            return False
        if self._contains_sensitive(message):
            return False
        return True

    async def check_post(self, output: dict[str, Any], context: WorkflowContext) -> bool:
        return True

    def sanitize(self, message: str) -> str:
        """清洗 prompt injection 常见模式（只做替换，不做判定）。"""
        cleaned = message
        for pattern in _PROMPT_INJECTION_PATTERNS:
            cleaned = re.sub(pattern, "[filtered]", cleaned, flags=re.IGNORECASE)
        return cleaned

    @staticmethod
    def _contains_injection(message: str) -> bool:
        return any(
            re.search(pattern, message, flags=re.IGNORECASE)
            for pattern in _PROMPT_INJECTION_PATTERNS
        )

    @staticmethod
    def _contains_sensitive(message: str) -> bool:
        return any(word in message for word in _SENSITIVE_WORDS)
