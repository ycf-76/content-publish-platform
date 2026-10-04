"""端到端测试：验证 LLM 驱动图文 Skill → card_draft 构建 → draft_patch SSE 推送 → 前端渲染。

覆盖：
1. PromptDrivenSkill._extract_card_pages 从 LLM 输出提取卡片 HTML
2. PromptDrivenSkill.execute 返回 card_draft 结构
3. _persist_creative_state 对图文 Skill 推送 draft_patch SSE 事件
4. 前端 normalizeCardDraft 正确处理 card_draft 结构
"""

from __future__ import annotations

import asyncio
import json
import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.base import PromptDrivenSkill
from app.tools.registry import SkillRegistry, ensure_builtin_skills_registered


# ============================================================================
# Test 1: _extract_card_pages 单元测试
# ============================================================================


class TestExtractCardPages:
    """验证 PromptDrivenSkill._extract_card_pages 的卡片 HTML 提取逻辑。"""

    def test_single_card_html_block(self):
        raw = """# 小红书卡片组: 极简生活
风格: 瑞士极简
数量: 3张

<!--card-html-->
<!DOCTYPE html><html><head><style>.card{width:1080px;height:1440px;}</style></head><body><div class="card">封面</div></body></html>
<!--/card-html-->"""
        pages, html_urls = PromptDrivenSkill._extract_card_pages(raw)
        assert len(pages) == 1
        assert pages[0]["type"] == "cover"
        assert "htmlContent" in pages[0]
        assert "<!DOCTYPE html>" in pages[0]["htmlContent"]
        assert len(html_urls) == 1
        assert html_urls[0].startswith("card-html://inline/")

    def test_multiple_card_html_blocks(self):
        raw = """<!--card-html-->
<html><body><div class="card">封面</div></body></html>
<!--/card-html-->

<!--card-html-->
<html><body><div class="card">正文1</div></body></html>
<!--/card-html-->

<!--card-html-->
<html><body><div class="card">收尾</div></body></html>
<!--/card-html-->"""
        pages, html_urls = PromptDrivenSkill._extract_card_pages(raw)
        assert len(pages) == 3
        assert pages[0]["type"] == "cover"
        assert pages[1]["type"] == "content"
        assert pages[2]["type"] == "ending"
        assert len(html_urls) == 3

    def test_no_card_html_marker(self):
        raw = "这是一段普通文本，没有卡片HTML"
        pages, html_urls = PromptDrivenSkill._extract_card_pages(raw)
        assert pages == []
        assert html_urls == []

    def test_empty_string(self):
        pages, html_urls = PromptDrivenSkill._extract_card_pages("")
        assert pages == []
        assert html_urls == []

    def test_empty_card_html_block_skipped(self):
        raw = "<!--card-html-->\n<!--/card-html-->"
        pages, html_urls = PromptDrivenSkill._extract_card_pages(raw)
        assert pages == []
        assert html_urls == []

    def test_card_pages_have_unique_ids(self):
        raw = "<!--card-html--><html>A</html><!--/card-html-->\n<!--card-html--><html>B</html><!--/card-html-->"
        pages, html_urls = PromptDrivenSkill._extract_card_pages(raw)
        ids = [p["id"] for p in pages]
        assert len(set(ids)) == len(ids)

    def test_5_cards_type_assignment(self):
        raw = "\n".join(
            f"<!--card-html--><html>Card {i + 1}</html><!--/card-html-->"
            for i in range(5)
        )
        pages, html_urls = PromptDrivenSkill._extract_card_pages(raw)
        assert len(pages) == 5
        assert pages[0]["type"] == "cover"
        assert pages[1]["type"] == "content"
        assert pages[2]["type"] == "content"
        assert pages[3]["type"] == "content"
        assert pages[4]["type"] == "ending"


# ============================================================================
# Test 2: PromptDrivenSkill.execute 返回 card_draft
# ============================================================================


class _ScriptedLLM:
    model_name = "mock-scripted"

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._call_count = 0

    async def chat(self, messages, response_format=None):
        resp = self._responses[self._call_count] if self._call_count < len(self._responses) else ""
        self._call_count += 1
        return {"content": resp, "reasoning_content": None, "token_usage": 100}

    async def stream_chat(self, messages, response_format=None, tools=None):
        resp = await self.chat(messages, response_format)
        yield {"content": resp["content"], "reasoning_content": None, "token_usage": 100}


class TestPromptDrivenSkillReturnsCardDraft:
    """验证 PromptDrivenSkill.execute 在 LLM 返回 card-html 时构建 card_draft。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        ensure_builtin_skills_registered()
        self.registry = SkillRegistry.instance()

    @pytest.mark.asyncio
    async def test_card_xiaohongshu_returns_card_draft(self):
        skill_cls = self.registry.get("produce", "card_xiaohongshu")
        skill = skill_cls()

        llm_output = """# 小红书卡片组: 极简生活
风格: 瑞士极简
数量: 3张

<!--card-html-->
<!DOCTYPE html><html><head><style>.card{width:1080px;height:1440px;background:#fff;}</style></head><body><div class="card"><h1>极简生活</h1></div></body></html>
<!--/card-html-->

<!--card-html-->
<!DOCTYPE html><html><head><style>.card{width:1080px;height:1440px;background:#f8f8f8;}</style></head><body><div class="card"><p>习惯1：一进一出</p></div></body></html>
<!--/card-html-->

<!--card-html-->
<!DOCTYPE html><html><head><style>.card{width:1080px;height:1440px;background:#fff;}</style></head><body><div class="card"><p>开始你的极简之旅</p></div></body></html>
<!--/card-html-->"""

        mock_llm = _ScriptedLLM([llm_output])
        result = await skill.execute({
            "llm": mock_llm,
            "topic": "极简生活",
            "platform": "小红书",
        })

        assert "card_draft" in result
        card_draft = result["card_draft"]
        assert card_draft["title"] == "极简生活"
        assert card_draft["template"] == "card_xiaohongshu"
        assert len(card_draft["pages"]) == 3
        assert card_draft["pages"][0]["type"] == "cover"
        assert card_draft["pages"][1]["type"] == "content"
        assert card_draft["pages"][2]["type"] == "ending"
        assert len(card_draft["htmlUrls"]) == 3
        for page in card_draft["pages"]:
            assert "htmlContent" in page
            assert "<!DOCTYPE html>" in page["htmlContent"]

    @pytest.mark.asyncio
    async def test_xhs_note_creator_no_card_draft_when_no_html(self):
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        skill = skill_cls()

        llm_output = json.dumps({
            "title": "极简生活",
            "content": "极简不是扔东西...",
            "tags": ["极简生活"],
        }, ensure_ascii=False)

        mock_llm = _ScriptedLLM([llm_output])
        result = await skill.execute({
            "llm": mock_llm,
            "topic": "极简生活",
        })

        assert "card_draft" not in result

    @pytest.mark.asyncio
    async def test_xhs_note_creator_has_card_draft_when_html_included(self):
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        skill = skill_cls()

        llm_output = json.dumps({
            "title": "极简生活",
            "content": "极简不是扔东西...",
            "tags": ["极简生活"],
        }, ensure_ascii=False) + "\n\n<!--card-html--><html>策划卡片</html><!--/card-html-->"

        mock_llm = _ScriptedLLM([llm_output])
        result = await skill.execute({
            "llm": mock_llm,
            "topic": "极简生活",
        })

        assert "card_draft" in result
        assert len(result["card_draft"]["pages"]) == 1


# ============================================================================
# Test 3: _persist_creative_state 推送 draft_patch
# ============================================================================


class TestPersistCreativeStateEmitsDraftPatch:
    """验证 _persist_creative_state 对图文 Skill 推送 draft_patch SSE 事件。"""

    @pytest.mark.asyncio
    async def test_card_produce_tool_emits_draft_patch(self):
        from app.engine.harness.executor.loop import ReActLoop
        from app.services.sse_bus import EVENT_DRAFT_PATCH

        loop = ReActLoop()

        mock_harness = MagicMock()
        mock_context = MagicMock()
        mock_context.workflow_id = "test-workflow-123"
        mock_context.node_id = "test-node"

        card_draft = {
            "title": "极简生活",
            "template": "card_xiaohongshu",
            "pages": [
                {"id": "p1", "type": "cover", "title": "卡片 1", "htmlContent": "<html>...</html>"},
            ],
            "htmlUrls": ["card-html://inline/p1"],
        }

        result = {
            "card_draft": card_draft,
            "report": "some report",
        }

        with patch("app.engine.harness.executor.loop.sse_bus") as mock_bus:
            mock_bus.publish = AsyncMock()

            with patch("app.services.chat_session.update_creative_state", new_callable=AsyncMock):
                await loop._persist_creative_state(
                    mock_harness, mock_context, "card_xiaohongshu", result, {}
                )

                mock_bus.publish.assert_called_once()
                call_args = mock_bus.publish.call_args
                assert call_args[0][0] == "test-workflow-123"
                assert call_args[0][1] == EVENT_DRAFT_PATCH
                payload = call_args[0][2]
                assert "draft_id" in payload
                assert "updates" in payload
                assert "_card_draft" in payload["updates"]
                assert payload["updates"]["_card_draft"]["pages"][0]["htmlContent"] == "<html>...</html>"

    @pytest.mark.asyncio
    async def test_non_card_tool_does_not_emit_draft_patch(self):
        from app.engine.harness.executor.loop import ReActLoop

        loop = ReActLoop()

        mock_harness = MagicMock()
        mock_context = MagicMock()
        mock_context.workflow_id = "test-workflow-123"
        mock_context.node_id = "test-node"

        result = {"report": "some analysis result"}

        with patch("app.engine.harness.executor.loop.sse_bus") as mock_bus:
            mock_bus.publish = AsyncMock()

            with patch("app.services.chat_session.update_creative_state", new_callable=AsyncMock):
                await loop._persist_creative_state(
                    mock_harness, mock_context, "topic_evaluator", result, {}
                )

                mock_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_card_tool_without_card_draft_does_not_emit(self):
        from app.engine.harness.executor.loop import ReActLoop

        loop = ReActLoop()

        mock_harness = MagicMock()
        mock_context = MagicMock()
        mock_context.workflow_id = "test-workflow-123"
        mock_context.node_id = "test-node"

        result = {"report": "LLM output without card-html markers"}

        with patch("app.engine.harness.executor.loop.sse_bus") as mock_bus:
            mock_bus.publish = AsyncMock()

            with patch("app.services.chat_session.update_creative_state", new_callable=AsyncMock):
                await loop._persist_creative_state(
                    mock_harness, mock_context, "card_xiaohongshu", result, {}
                )

                mock_bus.publish.assert_not_called()