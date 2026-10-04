"""Tests for codex_prompt.py — Step 2 validation."""

import pytest


class TestCodexPrompt:
    def test_tool_descriptions_generated(self):
        from app.engine.codex.prompt import build_tool_descriptions
        desc = build_tool_descriptions()
        assert "file_read" in desc
        assert "file_write" in desc
        assert "bash" in desc
        assert "xhs_search" in desc
        assert "llm_generate" in desc
        assert "viral_score" in desc
        assert "content_check" in desc

    def test_tool_descriptions_has_all_13(self):
        from app.engine.codex.prompt import build_tool_descriptions
        desc = build_tool_descriptions()
        lines = [l for l in desc.strip().splitlines() if l.startswith("- ")]
        assert len(lines) == 13

    def test_full_system_prompt(self):
        from app.engine.codex.prompt import get_codex_system_prompt
        prompt = get_codex_system_prompt()
        assert "可用工具" in prompt
        assert "工作方式" in prompt
        assert "领域知识" in prompt
        assert "输出格式" in prompt
        assert "file_read" in prompt
        assert "llm_generate" in prompt
        assert len(prompt) > 500

    def test_permissions_in_descriptions(self):
        from app.engine.codex.prompt import build_tool_descriptions
        desc = build_tool_descriptions()
        assert "bash:exec" in desc
        assert "xhs:search" in desc
        assert "file:write" in desc

    def test_prompt_is_deterministic(self):
        from app.engine.codex.prompt import get_codex_system_prompt
        p1 = get_codex_system_prompt()
        p2 = get_codex_system_prompt()
        assert p1 == p2