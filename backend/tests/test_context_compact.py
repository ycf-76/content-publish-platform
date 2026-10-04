"""Tests for ContextCompactor — conversation history compaction.

Covers:
1. TRUNCATE strategy: keep system + recent N messages, drop the rest
2. SUMMARIZE strategy: requires LLM (fallback to truncate when no LLM)
3. CompactConfig defaults
4. advance_window() integration with TokenBudget
5. Edge cases: empty messages, all system messages, single message
6. Compaction notice insertion
"""

import pytest

from app.engine.governance.context_compact import (
    CompactConfig,
    CompactStrategy,
    ContextCompactor,
)
from app.engine.governance.token_budget import (
    BudgetAction,
    TokenBudget,
    TokenBudgetConfig,
)


def _make_messages(n_system=1, n_conversation=10):
    messages = []
    for i in range(n_system):
        messages.append({"role": "system", "content": f"System prompt {i}"})
    for i in range(n_conversation):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": f"Message {i}"})
    return messages


class TestCompactConfig:
    def test_default_strategy_is_truncate(self):
        config = CompactConfig()
        assert config.strategy == CompactStrategy.TRUNCATE

    def test_default_keep_recent(self):
        config = CompactConfig()
        assert config.keep_recent_messages == 4

    def test_custom_config(self):
        config = CompactConfig(
            strategy=CompactStrategy.SUMMARIZE,
            keep_recent_messages=6,
            max_summary_tokens=3000,
        )
        assert config.strategy == CompactStrategy.SUMMARIZE
        assert config.keep_recent_messages == 6


class TestContextCompactorTruncate:
    @pytest.mark.asyncio
    async def test_truncate_keeps_system_messages(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE, keep_recent_messages=2)
        compactor = ContextCompactor(config)
        messages = _make_messages(n_system=2, n_conversation=10)
        result = await compactor.compact(messages)
        system_msgs = [m for m in result if m["role"] == "system" and "System prompt" in m.get("content", "")]
        assert len(system_msgs) == 2

    @pytest.mark.asyncio
    async def test_truncate_keeps_recent_messages(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE, keep_recent_messages=3)
        compactor = ContextCompactor(config)
        messages = _make_messages(n_system=1, n_conversation=10)
        result = await compactor.compact(messages)
        non_system = [m for m in result if m["role"] != "system" or "上下文压缩" not in m.get("content", "")]
        conversation_msgs = [m for m in non_system if m["role"] in ("user", "assistant")]
        assert len(conversation_msgs) <= 3

    @pytest.mark.asyncio
    async def test_truncate_inserts_compaction_notice(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE, keep_recent_messages=2)
        compactor = ContextCompactor(config)
        messages = _make_messages(n_system=1, n_conversation=10)
        result = await compactor.compact(messages)
        notice = [m for m in result if "上下文压缩" in m.get("content", "")]
        assert len(notice) == 1
        assert "省略" in notice[0]["content"]

    @pytest.mark.asyncio
    async def test_truncate_empty_messages(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE)
        compactor = ContextCompactor(config)
        result = await compactor.compact([])
        assert result == []

    @pytest.mark.asyncio
    async def test_truncate_all_system_messages(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE, keep_recent_messages=2)
        compactor = ContextCompactor(config)
        messages = [
            {"role": "system", "content": "System 1"},
            {"role": "system", "content": "System 2"},
        ]
        result = await compactor.compact(messages)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_truncate_fewer_messages_than_keep(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE, keep_recent_messages=10)
        compactor = ContextCompactor(config)
        messages = _make_messages(n_system=1, n_conversation=3)
        result = await compactor.compact(messages)
        assert len(result) == len(messages)

    @pytest.mark.asyncio
    async def test_truncate_keep_zero(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE, keep_recent_messages=0)
        compactor = ContextCompactor(config)
        messages = _make_messages(n_system=1, n_conversation=5)
        result = await compactor.compact(messages)
        system_msgs = [m for m in result if m["role"] == "system" and "System prompt" in m.get("content", "")]
        assert len(system_msgs) == 1


class TestContextCompactorWithBudget:
    @pytest.mark.asyncio
    async def test_compact_advances_token_budget_window(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE, keep_recent_messages=2)
        budget_config = TokenBudgetConfig(
            context_window_tokens=64000,
            reminder_threshold_tokens=8000,
            compact_threshold_tokens=2000,
        )
        budget = TokenBudget(budget_config)
        budget.record_usage(62000)

        compactor = ContextCompactor(config, token_budget=budget)
        messages = _make_messages(n_system=1, n_conversation=10)
        await compactor.compact(messages)

        assert budget.window_number == 1
        assert budget.window_tokens_used == 0

    @pytest.mark.asyncio
    async def test_compact_count_increments(self):
        config = CompactConfig(strategy=CompactStrategy.TRUNCATE)
        compactor = ContextCompactor(config)
        messages = _make_messages(n_system=1, n_conversation=10)

        await compactor.compact(messages)
        assert compactor.compact_count == 1

        await compactor.compact(messages)
        assert compactor.compact_count == 2


class TestContextCompactorSummarize:
    @pytest.mark.asyncio
    async def test_summarize_without_llm_falls_back_to_truncate(self):
        config = CompactConfig(strategy=CompactStrategy.SUMMARIZE, keep_recent_messages=2)
        compactor = ContextCompactor(config)
        messages = _make_messages(n_system=1, n_conversation=10)
        result = await compactor.compact(messages, llm=None)
        assert len(result) < len(messages)
        system_msgs = [m for m in result if m["role"] == "system" and "System prompt" in m.get("content", "")]
        assert len(system_msgs) == 1