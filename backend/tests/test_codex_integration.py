"""Integration test: Codex mode end-to-end with mock LLM.

Demonstrates the full ReAct loop solving a content creation task
using thin primitives, without LangGraph or AgentHarness.
"""

import json
from typing import Any

import pytest

from app.engine.schemas import Permission


class _StepByStepMockLLM:
    """Mock LLM that follows a realistic content creation ReAct sequence."""

    def __init__(self):
        self._steps = [
            {
                "thought": "用户想做手冲咖啡内容，先搜小红书看看什么火",
                "tool_calls": [{"name": "xhs_search", "arguments": {"keyword": "手冲咖啡", "limit": 5}}],
                "final": False,
            },
            {
                "thought": "搜到了结果，用爆款评分分析一下",
                "tool_calls": [{"name": "viral_score", "arguments": {"results": [{"title": "3个手冲技巧", "likes": 5000, "comments": 200, "author_fans": 10000}]}}],
                "final": False,
            },
            {
                "thought": "爆款因子不错，写文案",
                "tool_calls": [{"name": "llm_generate", "arguments": {"prompt": "写一篇小红书手冲咖啡文案"}}],
                "final": False,
            },
            {
                "thought": "文案写好了，做合规检查",
                "tool_calls": [{"name": "content_check", "arguments": {"text": "3个让你手冲咖啡更好喝的小技巧"}}],
                "final": False,
            },
            {
                "thought": "合规通过，存到本地文件",
                "tool_calls": [{"name": "file_write", "arguments": {"path": "output/手冲咖啡.md", "content": "# 3个让你手冲咖啡更好喝的小技巧\n\n1. 控制水温\n2. 预热滤杯\n3. 缓慢注水"}}],
                "final": False,
            },
            {
                "thought": "文件已保存，任务完成",
                "final": True,
                "output": {
                    "title": "3个让你手冲咖啡更好喝的小技巧",
                    "status": "draft_saved",
                    "file": "output/手冲咖啡.md",
                },
            },
        ]
        self._index = 0

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        if self._index < len(self._steps):
            step = self._steps[self._index]
            self._index += 1
            return {"content": json.dumps(step, ensure_ascii=False), "token_usage": 50}
        return {"content": json.dumps({"final": True, "output": {"status": "done"}}), "token_usage": 10}


class TestCodexIntegration:
    """End-to-end integration test for Codex mode."""

    @pytest.mark.asyncio
    async def test_full_content_creation_flow(self, tmp_path, monkeypatch):
        """Simulate a complete content creation flow:
        search → viral_score → llm_generate → content_check → file_write → final
        """
        from app.engine.codex.session import CodexSession

        monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

        llm = _StepByStepMockLLM()
        session = CodexSession(
            llm=llm,
            allowed_permissions={
                Permission.XHS_SEARCH,
                Permission.FILE_WRITE,
                Permission.FILE_READ,
            },
            max_iterations=10,
        )

        result = await session.run("帮我做一期手冲咖啡的内容")

        assert result["title"] == "3个让你手冲咖啡更好喝的小技巧"
        assert result["status"] == "draft_saved"
        assert result["_iterations"] == 6
        assert result["_token_usage"] > 0

    @pytest.mark.asyncio
    async def test_file_operation_flow(self, tmp_path, monkeypatch):
        """Simulate a file operation flow:
        file_write → file_read → file_edit → final
        """
        from app.engine.codex.session import CodexSession

        monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

        steps = [
            {
                "thought": "先写一个文件",
                "tool_calls": [{"name": "file_write", "arguments": {"path": "test.txt", "content": "hello world"}}],
                "final": False,
            },
            {
                "thought": "读回来确认",
                "tool_calls": [{"name": "file_read", "arguments": {"path": "test.txt"}}],
                "final": False,
            },
            {
                "thought": "修改内容",
                "tool_calls": [{"name": "file_edit", "arguments": {"path": "test.txt", "old_string": "world", "new_string": "codex"}}],
                "final": False,
            },
            {
                "thought": "完成",
                "final": True,
                "output": {"status": "file_modified", "path": "test.txt"},
            },
        ]

        class _LocalMockLLM:
            def __init__(self):
                self._index = 0
            async def chat(self, messages, **kwargs):
                if self._index < len(steps):
                    step = steps[self._index]
                    self._index += 1
                    return {"content": json.dumps(step), "token_usage": 20}
                return {"content": '{"final": true, "output": {}}', "token_usage": 5}

        session = CodexSession(
            llm=_LocalMockLLM(),
            allowed_permissions={Permission.FILE_READ, Permission.FILE_WRITE},
            max_iterations=10,
        )

        result = await session.run("修改 test.txt 文件")
        assert result["status"] == "file_modified"
        assert result["_iterations"] == 4

    @pytest.mark.asyncio
    async def test_permission_denied_recovery(self):
        """LLM tries bash without permission, observes error, tries alternative."""
        from app.engine.codex.session import CodexSession

        steps = [
            {
                "thought": "用 bash 看看目录",
                "tool_calls": [{"name": "bash", "arguments": {"command": "ls"}}],
                "final": False,
            },
            {
                "thought": "bash 被拒了，用 glob 代替",
                "tool_calls": [{"name": "glob", "arguments": {"pattern": "*"}}],
                "final": False,
            },
            {
                "thought": "glob 也需要权限，用 content_check 代替",
                "tool_calls": [{"name": "content_check", "arguments": {"text": "test"}}],
                "final": False,
            },
            {
                "thought": "完成",
                "final": True,
                "output": {"status": "ok", "method": "fallback"},
            },
        ]

        class _LocalMockLLM:
            def __init__(self):
                self._index = 0
            async def chat(self, messages, **kwargs):
                if self._index < len(steps):
                    step = steps[self._index]
                    self._index += 1
                    return {"content": json.dumps(step), "token_usage": 20}
                return {"content": '{"final": true, "output": {}}', "token_usage": 5}

        session = CodexSession(
            llm=_LocalMockLLM(),
            allowed_permissions=set(),
            max_iterations=10,
        )

        result = await session.run("看看目录")
        assert result["status"] == "ok"
        assert result["method"] == "fallback"