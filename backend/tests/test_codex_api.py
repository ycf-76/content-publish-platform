"""Tests for codex API endpoint — Step 4 validation."""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.engine.schemas import Permission


class _MockLLM:
    def __init__(self, response: dict[str, Any]):
        self._response = response

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return self._response


class TestCodexRouterInfo:
    @pytest.mark.asyncio
    async def test_info_response_structure(self):
        from app.engine.codex.primitives import ALL_PRIMITIVES
        from app.api.routers.codex import CodexInfoResponse

        primitives = [p.info() for p in ALL_PRIMITIVES]
        permissions = [p.value for p in Permission]
        resp = CodexInfoResponse(primitives=primitives, permissions_available=permissions)

        assert len(resp.primitives) == 14
        assert "file:read" in resp.permissions_available
        assert "bash:exec" in resp.permissions_available

    @pytest.mark.asyncio
    async def test_info_has_expected_primitives(self):
        from app.engine.codex.primitives import ALL_PRIMITIVES
        names = [p.name for p in ALL_PRIMITIVES]
        assert "file_read" in names
        assert "file_write" in names
        assert "bash" in names
        assert "xhs_search" in names
        assert "image_read" in names
        assert "content_check" in names


class TestCodexRunEndpoint:
    @pytest.mark.asyncio
    async def test_run_with_mock_llm(self):
        from app.engine.codex.session import CodexSession

        llm = _MockLLM({
            "content": json.dumps({"thought": "done", "final": True, "output": {"title": "咖啡指南"}}),
            "token_usage": 50,
        })
        session = CodexSession(
            llm=llm,
            allowed_permissions={Permission.FILE_READ, Permission.BASH_EXEC},
            max_iterations=5,
        )
        result = await session.run("做咖啡内容")
        assert result["title"] == "咖啡指南"
        assert result["_iterations"] == 1

    @pytest.mark.asyncio
    async def test_run_permission_parsing(self):
        from app.api.routers.codex import _parse_permissions

        perms = _parse_permissions(["file:read", "file:write", "bash:exec"])
        assert Permission.FILE_READ in perms
        assert Permission.FILE_WRITE in perms
        assert Permission.BASH_EXEC in perms
        assert len(perms) == 3

    @pytest.mark.asyncio
    async def test_run_unknown_permission_ignored(self):
        from app.api.routers.codex import _parse_permissions
        perms = _parse_permissions(["file:read", "unknown:perm"])
        assert len(perms) == 1

    @pytest.mark.asyncio
    async def test_run_empty_permissions(self):
        from app.api.routers.codex import _parse_permissions
        perms = _parse_permissions([])
        assert len(perms) == 0

    @pytest.mark.asyncio
    async def test_codex_run_response_model(self):
        from app.api.routers.codex import CodexRunResponse
        resp = CodexRunResponse(
            ok=True,
            output={"title": "test"},
            iterations=3,
            token_usage=150,
            last_thought="done",
            steps=[],
            duration_ms=2000,
        )
        assert resp.ok is True
        assert resp.iterations == 3
        assert resp.duration_ms == 2000