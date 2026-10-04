"""Tests for TokenBudget — Codex-style two-level budget system.

Covers:
1. TokenBudgetConfig validation (invalid threshold ordering)
2. _WindowBudget: remaining(), check(), advance(), one-shot flags
3. TokenBudget: record_usage(), advance_window(), to_dict()
4. Realistic scenarios: gradual usage -> WARN -> COMPACT -> HARD_STOP
5. Edge cases: zero usage, negative input, exact threshold boundary
"""

import pytest

from app.engine.governance.token_budget import (
    BudgetAction,
    TokenBudget,
    TokenBudgetConfig,
    _WindowBudget,
)


class TestTokenBudgetConfig:
    def test_default_config_is_valid(self):
        config = TokenBudgetConfig()
        config.validate()

    def test_custom_valid_config(self):
        config = TokenBudgetConfig(
            context_window_tokens=128000,
            reminder_threshold_tokens=16000,
            compact_threshold_tokens=4000,
            hard_stop_total_tokens=500000,
            warn_total_tokens=250000,
        )
        config.validate()

    def test_reminder_must_be_less_than_context_window(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=64000,
        )
        with pytest.raises(ValueError, match="reminder_threshold must be less than context_window"):
            config.validate()

    def test_compact_must_be_less_than_reminder(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=8000,
        )
        with pytest.raises(ValueError, match="compact_threshold must be less than reminder_threshold"):
            config.validate()


class TestWindowBudget:
    def test_remaining_with_zero_usage(self):
        w = _WindowBudget()
        assert w.remaining(64000) == 64000

    def test_remaining_with_some_usage(self):
        w = _WindowBudget(tokens_used=10000)
        assert w.remaining(64000) == 54000

    def test_remaining_never_negative(self):
        w = _WindowBudget(tokens_used=100000)
        assert w.remaining(64000) == 0

    def test_check_returns_ok_when_plenty_of_room(self):
        w = _WindowBudget(tokens_used=10000)
        config = TokenBudgetConfig()
        assert w.check(config) == BudgetAction.OK

    def test_check_returns_warn_near_limit(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        w = _WindowBudget(tokens_used=64000 - 8000)
        assert w.check(config) == BudgetAction.WARN

    def test_check_returns_compact_at_compact_threshold(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        w = _WindowBudget(tokens_used=64000 - 2000)
        assert w.check(config) == BudgetAction.COMPACT

    def test_check_warn_is_one_shot(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        w = _WindowBudget(tokens_used=64000 - 8000)
        assert w.check(config) == BudgetAction.WARN
        assert w.check(config) == BudgetAction.OK

    def test_check_compact_is_one_shot(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        w = _WindowBudget(tokens_used=64000 - 2000)
        assert w.check(config) == BudgetAction.COMPACT
        assert w.check(config) == BudgetAction.OK

    def test_advance_resets_tokens_and_flags(self):
        w = _WindowBudget(tokens_used=60000, _reminder_fired=True, _compact_fired=True)
        next_w = w.advance()
        assert next_w.window_number == 1
        assert next_w.tokens_used == 0
        assert next_w._reminder_fired is False
        assert next_w._compact_fired is False


class TestTokenBudget:
    def test_initial_state(self):
        budget = TokenBudget()
        assert budget.total_tokens == 0
        assert budget.window_tokens_used == 0
        assert budget.window_number == 0
        assert budget.remaining_in_window() == 64000

    def test_record_usage_returns_ok(self):
        budget = TokenBudget()
        action = budget.record_usage(1000)
        assert action == BudgetAction.OK
        assert budget.total_tokens == 1000
        assert budget.window_tokens_used == 1000

    def test_record_usage_negative_input_treated_as_zero(self):
        budget = TokenBudget()
        action = budget.record_usage(-100)
        assert action == BudgetAction.OK
        assert budget.total_tokens == 0

    def test_record_usage_triggers_warn_on_first_cross(self):
        """record_usage(56000) puts remaining at exactly 8000,
        which satisfies remaining <= reminder_threshold, so WARN fires."""
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        budget = TokenBudget(config)
        action = budget.record_usage(64000 - 8000)
        assert action == BudgetAction.WARN

    def test_record_usage_warn_is_one_shot(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        budget = TokenBudget(config)
        budget.record_usage(64000 - 8000)
        action = budget.record_usage(100)
        assert action == BudgetAction.OK

    def test_record_usage_triggers_compact_on_first_cross(self):
        """record_usage(62000) puts remaining at exactly 2000,
        which satisfies remaining <= compact_threshold, so COMPACT fires."""
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        budget = TokenBudget(config)
        action = budget.record_usage(64000 - 2000)
        assert action == BudgetAction.COMPACT

    def test_record_usage_compact_is_one_shot(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        budget = TokenBudget(config)
        budget.record_usage(64000 - 2000)
        action = budget.record_usage(100)
        assert action == BudgetAction.OK

    def test_record_usage_triggers_hard_stop(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
            hard_stop_total_tokens=100000,
        )
        budget = TokenBudget(config)
        budget.record_usage(99999)
        action = budget.record_usage(1)
        assert action == BudgetAction.HARD_STOP

    def test_hard_stop_takes_priority_over_compact(self):
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
            hard_stop_total_tokens=50000,
        )
        budget = TokenBudget(config)
        budget.record_usage(50000)
        action = budget.record_usage(1)
        assert action == BudgetAction.HARD_STOP

    def test_advance_window(self):
        budget = TokenBudget()
        budget.record_usage(30000)
        budget.advance_window()
        assert budget.window_number == 1
        assert budget.window_tokens_used == 0
        assert budget.total_tokens == 30000

    def test_to_dict(self):
        budget = TokenBudget()
        budget.record_usage(5000)
        d = budget.to_dict()
        assert d["window_number"] == 0
        assert d["window_tokens_used"] == 5000
        assert d["window_remaining"] == 59000
        assert d["total_tokens"] == 5000
        assert d["context_window"] == 64000

    def test_realistic_workflow_scenario(self):
        """Simulate a real workflow: 10 LLM calls, then WARN, then COMPACT,
        then advance window, then more calls until HARD_STOP."""
        config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
            hard_stop_total_tokens=200000,
        )
        budget = TokenBudget(config)

        for _ in range(10):
            budget.record_usage(5000)
        assert budget.total_tokens == 50000

        warn_action = budget.record_usage(6000)
        assert warn_action == BudgetAction.WARN

        compact_action = budget.record_usage(6000)
        assert compact_action == BudgetAction.COMPACT

        budget.advance_window()
        assert budget.window_number == 1
        assert budget.window_tokens_used == 0

        for _ in range(28):
            budget.record_usage(5000)
        action = budget.record_usage(1)
        assert action == BudgetAction.HARD_STOP