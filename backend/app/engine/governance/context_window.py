"""Context window: precise tracking of context window token status.

Ref: Codex context_window.rs — the key insight is:
  Context window has TWO separate limits:
    1. auto_compact_scope: the token count that triggers auto-compaction
       (can be scoped to "total" or "body_after_prefix")
    2. full_context_window: the model's hard context window limit

  These are INDEPENDENT:
    - auto_compact_scope might be 80% of full window (trigger compaction early)
    - full_context_window is the hard ceiling (model will truncate)

  Codex also tracks:
    - base_window_tokens_remaining: how much room before compaction
    - prefill_input_tokens: tokens used by the initial system prompt
    - token_limit_reached: boolean flag for immediate compaction

Our adaptation:
  - ContextWindowStatus tracks both limits
  - Two scopes: TOTAL (count all tokens) and BODY_AFTER_PREFIX (exclude system prompt)
  - get_status() returns a snapshot for decision-making
  - Integrated with TokenBudget for compaction triggers
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CompactScope(str, Enum):
    TOTAL = "total"
    BODY_AFTER_PREFIX = "body_after_prefix"


class ContextWindowStatus(BaseModel):
    """Snapshot of context window token status.

    Ref: Codex ContextWindowTokenStatus — tracks:
      - active_context_tokens: total tokens in the active context
      - auto_compact_scope_tokens: tokens counted against the auto-compact limit
      - auto_compact_scope_limit: the configured auto-compact threshold
      - full_context_window_limit: the model's hard context window
      - base_window_tokens_remaining: room before compaction triggers
      - token_limit_reached: whether compaction should fire NOW
    """

    active_context_tokens: int = 0
    auto_compact_scope_tokens: int = 0
    auto_compact_scope_limit: int | None = None
    full_context_window_limit: int | None = None
    base_window_tokens_remaining: int | None = None
    auto_compact_window_prefill_tokens: int | None = None
    full_context_window_limit_reached: bool = False
    token_limit_reached: bool = False


class ContextWindowTracker:
    """Tracks context window token usage with dual-scope awareness.

    Ref: Codex context_window.rs::context_window_token_status():
      - Counts tokens against the configured scope
      - Reports remaining tokens against both limits
      - Detects when compaction is needed

    Usage:
        tracker = ContextWindowTracker(
            full_context_window=64000,
            auto_compact_limit=56000,
            scope=CompactScope.BODY_AFTER_PREFIX,
        )
        tracker.set_prefill_tokens(2000)  # system prompt
        tracker.record_tokens(1500)       # user + assistant turn
        status = tracker.get_status()
        if status.token_limit_reached:
            # trigger compaction
    """

    def __init__(
        self,
        full_context_window: int = 64000,
        auto_compact_limit: int | None = None,
        scope: CompactScope = CompactScope.BODY_AFTER_PREFIX,
        fallback_buffer_tokens: int = 2000,
    ) -> None:
        self._full_context_window = full_context_window
        self._auto_compact_limit = auto_compact_limit or int(full_context_window * 0.875)
        self._scope = scope
        self._fallback_buffer_tokens = fallback_buffer_tokens

        self._active_context_tokens = 0
        self._prefill_tokens: int | None = None

    def set_prefill_tokens(self, tokens: int) -> None:
        """Set the token count of the initial system prompt.

        Ref: Codex auto_compact_window_snapshot().prefill_input_tokens —
        this is the baseline for BODY_AFTER_PREFIX scope.
        """
        self._prefill_tokens = tokens

    def record_tokens(self, token_count: int) -> ContextWindowStatus:
        """Record token usage and return current status.

        Ref: Codex context_window_token_status() — called after each
        LLM response to check if compaction is needed.
        """
        self._active_context_tokens += token_count
        return self.get_status()

    def get_status(self) -> ContextWindowStatus:
        """Get current context window status.

        Ref: Codex context_window_token_status() — computes:
          - auto_compact_scope_tokens based on scope
          - remaining tokens against both limits
          - whether token_limit_reached
        """
        if self._scope == CompactScope.BODY_AFTER_PREFIX:
            baseline = self._prefill_tokens or 0
            scope_tokens = max(0, self._active_context_tokens - baseline)
        else:
            scope_tokens = self._active_context_tokens

        scope_limit = self._auto_compact_limit
        full_limit = self._full_context_window

        remaining_against_scope = (
            scope_limit - scope_tokens if scope_limit is not None else None
        )
        remaining_against_full = full_limit - self._active_context_tokens

        base_remaining = None
        if remaining_against_scope is not None and remaining_against_full is not None:
            base_remaining = min(remaining_against_scope, remaining_against_full)
        elif remaining_against_scope is not None:
            base_remaining = remaining_against_scope
        elif remaining_against_full is not None:
            base_remaining = remaining_against_full

        buffered_scope_limit = (
            scope_limit + self._fallback_buffer_tokens
            if scope_limit is not None
            else None
        )

        full_limit_reached = (
            self._active_context_tokens >= full_limit
        )

        token_limit_reached = (
            (buffered_scope_limit is not None and scope_tokens >= buffered_scope_limit)
            or full_limit_reached
        )

        return ContextWindowStatus(
            active_context_tokens=self._active_context_tokens,
            auto_compact_scope_tokens=scope_tokens,
            auto_compact_scope_limit=scope_limit,
            full_context_window_limit=full_limit,
            base_window_tokens_remaining=base_remaining,
            auto_compact_window_prefill_tokens=self._prefill_tokens,
            full_context_window_limit_reached=full_limit_reached,
            token_limit_reached=token_limit_reached,
        )

    def reset_after_compaction(self) -> None:
        """Reset scope tokens after compaction.

        Ref: Codex auto_compact_window_snapshot — after compaction,
        the window is advanced, so scope tokens reset.
        The prefill tokens are updated to reflect the compacted prefix.
        """
        self._prefill_tokens = self._active_context_tokens
        self._active_context_tokens = 0

    @property
    def active_tokens(self) -> int:
        return self._active_context_tokens

    def to_dict(self) -> dict[str, Any]:
        status = self.get_status()
        return {
            "active_context_tokens": status.active_context_tokens,
            "scope_tokens": status.auto_compact_scope_tokens,
            "scope_limit": status.auto_compact_scope_limit,
            "full_limit": status.full_context_window_limit,
            "remaining": status.base_window_tokens_remaining,
            "limit_reached": status.token_limit_reached,
        }