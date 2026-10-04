"""Context Compactor — auto-compact conversation history when context window is full.

Codex core insight (ref: codex-rs/core/src/compact.rs + compact_token_budget.rs):
  - When token budget signals COMPACT, the system compacts conversation history
  - Two compaction strategies:
    1. Local compaction: use the LLM to summarize history into a compact summary
    2. Token-budget compaction: skip summarization, just start a fresh context window
  - Compaction is modeled as a "turn" with its own lifecycle events
  - Pre/post compact hooks are fired (hook system)
  - The compaction summary replaces the old history
  - After compaction, a new context window starts (window_number increments)

Codex's compaction flow (ref: compact.rs::run_compact_task_inner):
  1. Fire pre-compact hooks
  2. Emit ContextCompaction turn item (UI shows "compacting...")
  3. Start new context window (advance window_number)
  4. Fire post-compact hooks

Codex's summarization approach (ref: compact.rs::run_inline_auto_compact_task):
  - Uses a SUMMARIZATION_PROMPT to ask the LLM to summarize the conversation
  - The summary replaces the full history
  - This costs one LLM call but saves thousands of tokens

Our adaptation:
  - Two strategies: SUMMARIZE (LLM-based) and TRUNCATE (cheap)
  - SUMMARIZE: ask LLM to summarize old messages, keep summary + recent messages
  - TRUNCATE: keep system prompt + last N messages, drop the rest
  - Compaction is triggered by TokenBudget when remaining <= compact_threshold
  - After compaction, TokenBudget.advance_window() is called
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.engine.governance.token_budget import TokenBudget, BudgetAction

logger = logging.getLogger(__name__)


class CompactStrategy(str, Enum):
    """Compaction strategy.

    Ref: Codex's CompactionStrategy enum:
      - Local: use LLM to summarize (costs tokens but preserves info)
      - TokenBudget: skip summarization, just start fresh (cheap but loses info)
    """

    SUMMARIZE = "summarize"
    TRUNCATE = "truncate"


@dataclass
class CompactConfig:
    """Compaction configuration.

    Ref: Codex's compact.rs — SUMMARIZATION_PROMPT is the default prompt
    used for local compaction. compact_user_message_max_tokens limits
    the size of the compaction input.
    """

    strategy: CompactStrategy = CompactStrategy.TRUNCATE
    keep_recent_messages: int = 4
    max_summary_tokens: int = 2000
    summarization_prompt: str = (
        "请将以下对话历史压缩为简洁的摘要，保留关键决策、结论和上下文信息。"
        "不要丢失任何重要的用户需求、工具调用结果或最终结论。"
        "摘要应该足够详细，让后续对话能无缝继续。"
    )


class ContextCompactor:
    """Context compactor that compresses conversation history.

    Ref: Codex's compact.rs — the compactor is called when token budget
    signals that compaction is needed. It replaces the old history with
    a compacted version.

    Usage:
        compactor = ContextCompactor(config, token_budget)
        if token_budget.check() == BudgetAction.COMPACT:
            new_messages = compactor.compact(messages, llm=llm)
    """

    def __init__(
        self,
        config: CompactConfig | None = None,
        token_budget: TokenBudget | None = None,
    ) -> None:
        self._config = config or CompactConfig()
        self._budget = token_budget
        self._compact_count = 0

    @property
    def compact_count(self) -> int:
        return self._compact_count

    async def compact(
        self,
        messages: list[dict[str, Any]],
        llm: Any = None,
    ) -> list[dict[str, Any]]:
        """Compact conversation history.

        Ref: Codex's compact.rs::run_compact_task_inner():
          1. Pre-compact hooks (we skip for now, will add in hooks module)
          2. Perform compaction (summarize or truncate)
          3. Post-compact hooks
          4. Advance token budget window

        Args:
            messages: Current conversation history
            llm: LLM instance for summarization (required for SUMMARIZE strategy)

        Returns:
            Compacted conversation history
        """
        self._compact_count += 1
        logger.info(
            f"[compactor] starting compaction #{self._compact_count}, "
            f"strategy={self._config.strategy.value}, "
            f"messages={len(messages)}"
        )

        if self._config.strategy == CompactStrategy.SUMMARIZE and llm is not None:
            result = await self._compact_summarize(messages, llm)
        else:
            result = self._compact_truncate(messages)

        if self._budget is not None:
            self._budget.advance_window()

        logger.info(
            f"[compactor] compaction #{self._compact_count} complete, "
            f"messages: {len(messages)} -> {len(result)}"
        )

        return result

    def _compact_truncate(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Truncate strategy: keep system + recent messages.

        Ref: Codex's token-budget compaction (compact_token_budget.rs):
          - Skips LLM summarization entirely
          - Starts a fresh context window
          - Initial context (system prompt, world state) is re-injected

        Our adaptation:
          - Keep system messages (role=system)
          - Keep last N user/assistant messages
          - Insert a compaction notice where old messages were removed
        """
        system_msgs: list[dict[str, Any]] = []
        conversation_msgs: list[dict[str, Any]] = []

        for msg in messages:
            if msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                conversation_msgs.append(msg)

        keep = self._config.keep_recent_messages
        if keep <= 0:
            kept = []
        else:
            kept = conversation_msgs[-keep:] if len(conversation_msgs) > keep else conversation_msgs
        dropped = len(conversation_msgs) - len(kept)

        result = list(system_msgs)

        if dropped > 0:
            result.append({
                "role": "system",
                "content": (
                    f"[上下文压缩] 为节省 Token 空间，已省略 {dropped} 条历史消息。"
                    "以下是最近的对话内容，请继续。"
                ),
            })

        result.extend(kept)
        return result

    async def _compact_summarize(
        self,
        messages: list[dict[str, Any]],
        llm: Any,
    ) -> list[dict[str, Any]]:
        """Summarize strategy: use LLM to compress old messages.

        Ref: Codex's compact.rs::run_inline_auto_compact_task():
          - Takes the conversation history
          - Sends a SUMMARIZATION_PROMPT to the LLM
          - The LLM produces a summary
          - The summary replaces the old history
          - Recent messages are kept after the summary

        Our adaptation:
          - Split messages into "old" (to summarize) and "recent" (to keep)
          - Ask LLM to summarize old messages
          - Build new history: system + summary + recent
        """
        system_msgs: list[dict[str, Any]] = []
        conversation_msgs: list[dict[str, Any]] = []

        for msg in messages:
            if msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                conversation_msgs.append(msg)

        keep = self._config.keep_recent_messages
        if len(conversation_msgs) <= keep:
            return messages

        old_msgs = conversation_msgs[:-keep]
        recent_msgs = conversation_msgs[-keep:]

        history_text = self._format_messages_for_summary(old_msgs)

        try:
            summary_result = await llm.chat(
                messages=[
                    {"role": "system", "content": self._config.summarization_prompt},
                    {"role": "user", "content": f"对话历史：\n{history_text}"},
                ],
                response_format=None,
            )
            summary_text = summary_result.get("content", "")
        except Exception as e:
            logger.warning(f"[compactor] summarization failed, falling back to truncate: {e}")
            return self._compact_truncate(messages)

        result = list(system_msgs)
        result.append({
            "role": "system",
            "content": f"[对话摘要]\n{summary_text}",
        })
        result.extend(recent_msgs)

        return result

    def _format_messages_for_summary(
        self, messages: list[dict[str, Any]]
    ) -> str:
        """Format messages for the summarization prompt.

        Ref: Codex's compact.rs — builds a user message from the
        conversation history that the LLM can summarize.
        """
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            lines.append(f"[{role}]: {content[:500]}")
        return "\n".join(lines)

    def should_compact(
        self, messages: list[dict[str, Any]], estimate_tokens_per_msg: int = 200
    ) -> bool:
        """Quick check if compaction is needed based on message count.

        This is a heuristic — the real check is TokenBudget.record_usage().
        Use this for proactive compaction before sending to LLM.
        """
        if self._budget is None:
            return False
        return self._budget.remaining_in_window() < len(messages) * estimate_tokens_per_msg