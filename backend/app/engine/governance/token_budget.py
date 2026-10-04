"""Token Budget — track and enforce token usage per session/workflow.

Codex core insight (ref: codex-rs/core/src/session/token_budget.rs + rollout_budget.rs):
  - TokenBudget tracks remaining tokens in the context window
  - When remaining <= reminder_threshold, inject a reminder into the conversation
  - When remaining == 0, trigger auto-compact as a fallback
  - RolloutBudget tracks total token usage across a session and enforces a hard cap
  - Key: budget is checked AFTER each LLM response, not before
  - The budget state is per-session (per "window" in Codex terms)

Codex's two-level budget system:
  1. TokenBudget (context window level):
     - Tracks how many tokens remain in the current context window
     - reminder_threshold: when to warn the model
     - auto_compact_fallback: when to force a compaction
  2. RolloutBudget (session level):
     - Tracks total tokens consumed across the entire session
     - Hard cap: if exceeded, abort the session
     - This prevents runaway agents from burning infinite tokens

Our adaptation:
  - TokenBudgetConfig mirrors Codex's TokenBudgetConfig
  - TokenBudget tracks per-workflow token usage
  - Two thresholds: warn (reminder) and hard_stop (abort)
  - Auto-compact trigger when context window is full
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BudgetAction(str, Enum):
    """Action to take when budget threshold is crossed.

    Ref: Codex's token_budget.rs — maybe_record() returns either
    a reminder or triggers auto-compact-fallback.
    """

    OK = "ok"
    WARN = "warn"
    COMPACT = "compact"
    HARD_STOP = "hard_stop"


@dataclass
class TokenBudgetConfig:
    """Token budget configuration.

    Ref: Codex's TokenBudgetConfig (codex-rs/core/src/config.rs):
      - reminder_threshold_tokens: when remaining tokens <= this, warn
      - auto_compact_fallback_buffer_tokens: when remaining <= this, compact
      - The config is per-model, with model-specific defaults

    Our defaults are calibrated for DeepSeek's 64K context window.
    """

    context_window_tokens: int = 64000
    reminder_threshold_tokens: int = 8000
    compact_threshold_tokens: int = 2000
    hard_stop_total_tokens: int = 200000
    warn_total_tokens: int = 100000

    def validate(self) -> None:
        if self.reminder_threshold_tokens >= self.context_window_tokens:
            raise ValueError("reminder_threshold must be less than context_window")
        if self.compact_threshold_tokens >= self.reminder_threshold_tokens:
            raise ValueError("compact_threshold must be less than reminder_threshold")


@dataclass
class _WindowBudget:
    """Per-context-window budget tracking.

    Ref: Codex's AutoCompactWindow (codex-rs/core/src/state/auto_compact_window.rs):
      - Tracks prefill_input_tokens (tokens used by the prompt/context)
      - Tracks window_number (how many compactions have happened)
      - Has claim_token_budget_reminder() — one-shot flag for reminder
      - Has claim_auto_compact_fallback() — one-shot flag for compact

    Key insight from Codex: the reminder and compact flags are ONE-SHOT.
    They fire once per window, then reset on the next window.
    This prevents spamming the model with repeated warnings.
    """

    window_number: int = 0
    tokens_used: int = 0
    _reminder_fired: bool = False
    _compact_fired: bool = False

    def remaining(self, context_window: int) -> int:
        return max(0, context_window - self.tokens_used)

    def check(self, config: TokenBudgetConfig) -> BudgetAction:
        """Check budget and return action, using one-shot flags.

        Ref: Codex's maybe_record() — checks remaining tokens against
        thresholds, fires one-shot reminders.
        """
        remaining = self.remaining(config.context_window_tokens)

        if remaining <= config.compact_threshold_tokens:
            if not self._compact_fired:
                self._compact_fired = True
                return BudgetAction.COMPACT
            return BudgetAction.OK

        if remaining <= config.reminder_threshold_tokens:
            if not self._reminder_fired:
                self._reminder_fired = True
                return BudgetAction.WARN
            return BudgetAction.OK

        return BudgetAction.OK

    def advance(self) -> "_WindowBudget":
        """Advance to a new context window (after compaction).

        Ref: Codex's AutoCompactWindow::advance() — increments window_number,
        generates new window_id, resets one-shot flags.
        """
        return _WindowBudget(
            window_number=self.window_number + 1,
            tokens_used=0,
        )


class TokenBudget:
    """Token budget tracker for a workflow/session.

    Ref: Codex's Session + TokenBudget integration:
      - Session holds a TokenBudget per context window
      - After each LLM response, maybe_record() is called
      - If budget is low, a contextual user fragment is injected
      - If budget is exhausted, auto-compact is triggered

    Usage:
        budget = TokenBudget(config)
        budget.record_usage(token_count=1500)
        action = budget.check()
        if action == BudgetAction.WARN:
            # inject reminder into conversation
        elif action == BudgetAction.COMPACT:
            # trigger context compaction
    """

    def __init__(self, config: TokenBudgetConfig | None = None) -> None:
        self._config = config or TokenBudgetConfig()
        self._config.validate()
        self._window = _WindowBudget()
        self._total_tokens = 0
        self._total_reminder_fired = False

    @property
    def config(self) -> TokenBudgetConfig:
        return self._config

    @property
    def window_number(self) -> int:
        return self._window.window_number

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def window_tokens_used(self) -> int:
        return self._window.tokens_used

    def remaining_in_window(self) -> int:
        return self._window.remaining(self._config.context_window_tokens)

    def record_usage(self, token_count: int) -> BudgetAction:
        """Record token usage after an LLM call.

        Ref: Codex's Session::record_rollout_budget_usage() +
        token_budget::maybe_record() — called after each LLM response,
        returns the action to take.

        Returns:
            BudgetAction indicating what (if anything) should happen.
        """
        token_count = max(0, int(token_count))
        self._window.tokens_used += token_count
        self._total_tokens += token_count

        if self._total_tokens >= self._config.hard_stop_total_tokens:
            logger.error(
                f"[token-budget] HARD STOP: total={self._total_tokens} >= "
                f"cap={self._config.hard_stop_total_tokens}"
            )
            return BudgetAction.HARD_STOP

        if (
            self._total_tokens >= self._config.warn_total_tokens
            and not self._total_reminder_fired
        ):
            self._total_reminder_fired = True
            logger.warning(
                f"[token-budget] total usage warning: {self._total_tokens} / "
                f"{self._config.hard_stop_total_tokens}"
            )

        action = self._window.check(self._config)
        if action in (BudgetAction.WARN, BudgetAction.COMPACT):
            logger.info(
                f"[token-budget] action={action.value}, "
                f"window_remaining={self.remaining_in_window()}, "
                f"window_used={self._window.tokens_used}, "
                f"total={self._total_tokens}"
            )
        return action

    def advance_window(self) -> None:
        """Advance to a new context window after compaction.

        Ref: Codex's AutoCompactWindow::advance() — called after
        a successful compaction, resets per-window counters.
        """
        self._window = self._window.advance()
        logger.info(
            f"[token-budget] advanced to window #{self._window.window_number}, "
            f"total_tokens={self._total_tokens}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_number": self._window.window_number,
            "window_tokens_used": self._window.tokens_used,
            "window_remaining": self.remaining_in_window(),
            "total_tokens": self._total_tokens,
            "context_window": self._config.context_window_tokens,
            "hard_stop": self._config.hard_stop_total_tokens,
        }