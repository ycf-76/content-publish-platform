"""Tests for codex_session.py — Step 3 validation.

Verifies:
1. Session construction and info
2. Message building
3. Step parsing (JSON, code fences, free text)
4. Dispatch (unknown tool, permission denied, successful call)
5. Full ReAct loop with mock LLM
6. Message truncation
7. Factory function
"""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.engine.schemas import Permission


class _MockLLM:
    """Controllable mock LLM for testing."""

    def __init__(self, responses: list[dict[str, Any]] | None = None):
        self.responses = responses or []
        self._index = 0

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        if self._index < len(self.responses):
            resp = self.responses[self._index]
            self._index += 1
            return resp
        return {"content": '{"final": true, "output": {"done": true}}', "token_usage": 10}


class _MockObserver:
    """Mock observer that records calls."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    async def emit_progress(self, node_id: str, **kwargs: Any) -> None:
        self.calls.append(("progress", node_id, kwargs))

    async def emit_decision(self, node_id: str, thought: str) -> None:
        self.calls.append(("decision", node_id, {"thought": thought}))


class TestCodexSessionConstruction:
    def test_default_construction(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        assert session.llm is None
        assert len(session.primitives) == 13
        assert session.max_iterations == 12

    def test_custom_max_iterations(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(max_iterations=5)
        assert session.max_iterations == 5

    def test_custom_primitives(self):
        from app.engine.codex.session import CodexSession
        from app.engine.codex.primitives import FileReadPrimitive, FileWritePrimitive
        session = CodexSession(primitives=[FileReadPrimitive(), FileWritePrimitive()])
        assert len(session.primitives) == 2
        assert "file_read" in session.primitives
        assert "file_write" in session.primitives

    def test_info(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(allowed_permissions={Permission.FILE_READ, Permission.BASH_EXEC})
        info = session.info()
        assert "file_read" in info["primitives"]
        assert len(info["allowed_permissions"]) == 2
        assert info["max_iterations"] == 12


class TestMessageBuilding:
    def test_basic_intent(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        msgs = session._build_initial_messages("帮我做咖啡内容", None)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "咖啡" in msgs[1]["content"]

    def test_with_context(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        msgs = session._build_initial_messages("test", {"account_id": "acc_123"})
        assert len(msgs) == 3
        assert msgs[1]["role"] == "system"
        assert "acc_123" in msgs[1]["content"]


class TestStepParsing:
    def test_valid_json(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        parsed = session._parse_step('{"thought": "test", "tool_calls": [], "final": false}')
        assert parsed["thought"] == "test"
        assert parsed["final"] is False

    def test_json_with_tool_calls(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        text = json.dumps({
            "thought": "search first",
            "tool_calls": [{"name": "xhs_search", "arguments": {"keyword": "咖啡"}}],
            "final": False,
        })
        parsed = session._parse_step(text)
        assert len(parsed["tool_calls"]) == 1
        assert parsed["tool_calls"][0]["name"] == "xhs_search"

    def test_final_output(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        text = json.dumps({"thought": "done", "final": True, "output": {"title": "test"}})
        parsed = session._parse_step(text)
        assert parsed["final"] is True
        assert parsed["output"]["title"] == "test"

    def test_code_fence_json(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        text = '```json\n{"thought": "fenced", "final": true, "output": {}}\n```'
        parsed = session._parse_step(text)
        assert parsed["thought"] == "fenced"

    def test_free_text_fallback(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        parsed = session._parse_step("I need to search for coffee content")
        assert parsed["thought"] == "I need to search for coffee content"
        assert parsed["final"] is False
        assert parsed["tool_calls"] == []

    def test_json_embedded_in_text(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        text = 'Here is my plan:\n{"thought": "embedded", "final": false, "tool_calls": []}\nThat should work.'
        parsed = session._parse_step(text)
        assert parsed["thought"] == "embedded"


class TestDispatch:
    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        result = await session._dispatch({"name": "nonexistent_tool", "arguments": {}})
        assert result["ok"] is False
        assert "unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(allowed_permissions=set())
        result = await session._dispatch({"name": "bash", "arguments": {"command": "ls"}})
        assert result["ok"] is False
        assert "permission denied" in result["error"]

    @pytest.mark.asyncio
    async def test_permission_granted(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(allowed_permissions={Permission.FILE_READ})
        result = await session._dispatch({"name": "file_read", "arguments": {"path": "nonexistent.txt"}})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_permission_needed(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(allowed_permissions=set())
        result = await session._dispatch({"name": "content_check", "arguments": {"text": "hello"}})
        assert result["ok"] is True
        assert result["passed"] is True


class TestReActLoop:
    @pytest.mark.asyncio
    async def test_immediate_final(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([{
            "content": json.dumps({"thought": "done", "final": True, "output": {"title": "咖啡指南"}}),
            "token_usage": 50,
        }])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("做咖啡内容")
        assert result["title"] == "咖啡指南"
        assert result["_iterations"] == 1
        assert result["_token_usage"] == 50

    @pytest.mark.asyncio
    async def test_two_step_loop(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "check content first",
                    "tool_calls": [{"name": "content_check", "arguments": {"text": "咖啡好喝"}}],
                    "final": False,
                }),
                "token_usage": 30,
            },
            {
                "content": json.dumps({"thought": "all good", "final": True, "output": {"status": "ok"}}),
                "token_usage": 20,
            },
        ])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("检查内容")
        assert result["status"] == "ok"
        assert result["_iterations"] == 2
        assert result["_token_usage"] == 50

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "keep going",
                    "tool_calls": [{"name": "content_check", "arguments": {"text": "test"}}],
                    "final": False,
                }),
                "token_usage": 10,
            },
        ] * 10)
        session = CodexSession(llm=llm, max_iterations=3)
        result = await session.run("infinite loop test")
        assert result.get("_loop_truncated") is True
        assert result["_iterations"] == 3

    @pytest.mark.asyncio
    async def test_no_tool_calls_terminates(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([{
            "content": json.dumps({"thought": "no tools needed", "tool_calls": [], "final": False}),
            "token_usage": 10,
        }])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("simple task")
        assert "thought" in result or "raw_text" in result

    @pytest.mark.asyncio
    async def test_observer_called(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([{
            "content": json.dumps({"thought": "done", "final": True, "output": {"ok": True}}),
            "token_usage": 10,
        }])
        observer = _MockObserver()
        session = CodexSession(llm=llm, max_iterations=5, observer=observer)
        await session.run("test")
        assert len(observer.calls) >= 1

    @pytest.mark.asyncio
    async def test_no_llm_returns_error(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(llm=None, max_iterations=5)
        result = await session.run("test")
        assert "error" in result


class TestMessageTruncation:
    def test_no_truncation_needed(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        msgs = [{"role": "system", "content": "sys"}] + [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        result = session._maybe_truncate_messages(msgs)
        assert len(result) == 11

    def test_truncation_applied(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        msgs = [{"role": "system", "content": "sys"}] + [{"role": "user", "content": f"msg {i}"} for i in range(100)]
        result = session._maybe_truncate_messages(msgs)
        assert len(result) <= 60
        assert result[0]["role"] == "system"


class TestCodeFenceStripping:
    def test_strip_json_fence(self):
        from app.engine.codex.session import CodexSession
        text = "```json\n{\"key\": \"value\"}\n```"
        result = CodexSession._strip_code_fence(text)
        assert result == '{"key": "value"}'

    def test_strip_plain_fence(self):
        from app.engine.codex.session import CodexSession
        text = "```\n{\"key\": \"value\"}\n```"
        result = CodexSession._strip_code_fence(text)
        assert result == '{"key": "value"}'

    def test_no_fence(self):
        from app.engine.codex.session import CodexSession
        text = '{"key": "value"}'
        result = CodexSession._strip_code_fence(text)
        assert result == text