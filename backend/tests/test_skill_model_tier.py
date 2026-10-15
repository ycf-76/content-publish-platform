"""Tests for Skill model_tier / task_type / temperature_override — compute allocation.

Covers:
1. Frontmatter parsing injects model_tier, task_type, temperature_override as class attributes
2. Skills with tier/task resolve LLM via ModelRouter
3. Skills without tier/task fall back to inputs["llm"]
4. ModelRouter failure falls back to inputs["llm"]
5. End-to-end: xhs_note_creator has premium/copywrite/0.8
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.base import PromptDrivenSkill
from app.tools.registry import SkillRegistry
import app.tools.prompt_skills as prompt_skills


@pytest.fixture(autouse=True)
def _reset_scanned():
    prompt_skills._scanned = False
    yield
    prompt_skills._scanned = False


@pytest.fixture
def registered_skills():
    prompt_skills.scan_and_register_prompt_skills()
    return SkillRegistry.instance()


class TestFrontmatterParsing:
    def test_xhs_note_creator_has_premium_tier(self, registered_skills):
        cls = registered_skills._skills.get("produce", {}).get("xhs_note_creator")
        assert cls is not None
        assert getattr(cls, "model_tier", "") == "premium"
        assert getattr(cls, "task_type", "") == "copywrite"
        assert getattr(cls, "temperature_override", None) == 0.8

    def test_quality_gate_has_budget_tier(self, registered_skills):
        cls = registered_skills._skills.get("quality_gate", {}).get("quality_gate")
        assert cls is not None
        assert getattr(cls, "model_tier", "") == "budget"
        assert getattr(cls, "task_type", "") == "analyze"
        assert getattr(cls, "temperature_override", None) == 0.1

    def test_risk_scanner_has_budget_tier(self, registered_skills):
        cls = registered_skills._skills.get("publish", {}).get("risk_scanner")
        assert cls is not None
        assert getattr(cls, "model_tier", "") == "budget"
        assert getattr(cls, "task_type", "") == "analyze"
        assert getattr(cls, "temperature_override", None) == 0.1

    def test_trending_topics_has_standard_tier(self, registered_skills):
        cls = registered_skills._skills.get("discover", {}).get("trending_topics")
        assert cls is not None
        assert getattr(cls, "model_tier", "") == "standard"
        assert getattr(cls, "task_type", "") == "analyze"
        assert getattr(cls, "temperature_override", None) == 0.5

    def test_skill_without_tier_has_empty_attrs(self, registered_skills):
        cls = registered_skills._skills.get("plan", {}).get("content_calendar")
        if cls is None:
            pytest.skip("content_calendar not registered")
        assert getattr(cls, "model_tier", "") == ""
        assert getattr(cls, "task_type", "") == ""
        assert getattr(cls, "temperature_override", None) is None


class TestLLMResolution:
    @pytest.mark.asyncio
    async def test_skill_with_tier_resolves_via_model_router(self, registered_skills):
        cls = registered_skills._skills.get("produce", {}).get("xhs_note_creator")
        assert cls is not None
        skill = cls()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value={"content": "test result"})
        mock_main_llm = AsyncMock()
        mock_main_llm.chat = AsyncMock(return_value={"content": "should not be called"})

        mock_selected = MagicMock()
        mock_selected.model_id = "deepseek-r1"

        mock_router = MagicMock()
        mock_router._select_model.return_value = mock_selected
        mock_router.resolve_llm.return_value = mock_llm

        with patch("app.adapters.model_router.get_model_router", return_value=mock_router):
            with patch.object(skill, "_load_skill_md", return_value="test skill md"):
                with patch.object(skill, "_load_references", return_value=""):
                    result = await skill.execute({"llm": mock_main_llm})

        mock_router._select_model.assert_called_once()
        mock_router.resolve_llm.assert_called_once_with(model="deepseek-r1", temperature=0.8)
        mock_llm.chat.assert_called()

    @pytest.mark.asyncio
    async def test_skill_without_tier_uses_main_llm(self, registered_skills):
        cls = registered_skills._skills.get("plan", {}).get("content_calendar")
        if cls is None:
            pytest.skip("content_calendar not registered")
        skill = cls()

        mock_main_llm = AsyncMock()
        mock_main_llm.chat = AsyncMock(return_value={"content": "main llm result"})

        with patch.object(skill, "_load_skill_md", return_value="test skill md"):
            with patch.object(skill, "_load_references", return_value=""):
                result = await skill.execute({"llm": mock_main_llm})

        mock_main_llm.chat.assert_called()

    @pytest.mark.asyncio
    async def test_model_router_failure_falls_back_to_main_llm(self, registered_skills):
        cls = registered_skills._skills.get("produce", {}).get("xhs_note_creator")
        assert cls is not None
        skill = cls()

        mock_main_llm = AsyncMock()
        mock_main_llm.chat = AsyncMock(return_value={"content": "fallback result"})

        with patch("app.adapters.model_router.get_model_router", side_effect=Exception("router broken")):
            with patch.object(skill, "_load_skill_md", return_value="test skill md"):
                with patch.object(skill, "_load_references", return_value=""):
                    result = await skill.execute({"llm": mock_main_llm})

        mock_main_llm.chat.assert_called()

    @pytest.mark.asyncio
    async def test_model_router_returns_none_falls_back(self, registered_skills):
        cls = registered_skills._skills.get("produce", {}).get("xhs_note_creator")
        assert cls is not None
        skill = cls()

        mock_main_llm = AsyncMock()
        mock_main_llm.chat = AsyncMock(return_value={"content": "fallback result"})

        mock_router = MagicMock()
        mock_router._select_model.return_value = None
        mock_router.resolve_llm.return_value = None

        with patch("app.adapters.model_router.get_model_router", return_value=mock_router):
            with patch.object(skill, "_load_skill_md", return_value="test skill md"):
                with patch.object(skill, "_load_references", return_value=""):
                    result = await skill.execute({"llm": mock_main_llm})

        mock_main_llm.chat.assert_called()


class TestTierDistribution:
    def test_premium_tier_skills(self, registered_skills):
        premium_skills = []
        for nt in registered_skills._skills:
            for name, cls in registered_skills._skills[nt].items():
                if getattr(cls, "model_tier", "") == "premium":
                    premium_skills.append(name)
        assert len(premium_skills) >= 3, f"Expected >=3 premium skills, got {premium_skills}"
        assert "xhs_note_creator" in premium_skills
        assert "copywriting" in premium_skills

    def test_budget_tier_skills(self, registered_skills):
        budget_skills = []
        for nt in registered_skills._skills:
            for name, cls in registered_skills._skills[nt].items():
                if getattr(cls, "model_tier", "") == "budget":
                    budget_skills.append(name)
        assert len(budget_skills) >= 2, f"Expected >=2 budget skills, got {budget_skills}"
        assert "quality_gate" in budget_skills

    def test_standard_tier_skills(self, registered_skills):
        standard_skills = []
        for nt in registered_skills._skills:
            for name, cls in registered_skills._skills[nt].items():
                if getattr(cls, "model_tier", "") == "standard":
                    standard_skills.append(name)
        assert len(standard_skills) >= 2, f"Expected >=2 standard skills, got {standard_skills}"

    def test_total_tiered_skills_count(self, registered_skills):
        tiered = 0
        for nt in registered_skills._skills:
            for name, cls in registered_skills._skills[nt].items():
                if getattr(cls, "model_tier", "") or getattr(cls, "task_type", ""):
                    tiered += 1
        assert tiered == 12, f"Expected 12 tiered skills, got {tiered}"