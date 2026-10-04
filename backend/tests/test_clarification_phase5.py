"""Phase 5 测试：现有 Skill 的 clarify_meta 声明验证"""

import pytest
from app.agents.clarification_schema import ClarifyFieldMeta, ClarifyWhen


class TestCopywriteSkillClarifyMeta:
    def test_copywrite_base_has_clarify_meta(self):
        from app.tools.copywrite_builder import CopywriteSkillBase
        meta = getattr(CopywriteSkillBase, "clarify_meta", None)
        assert meta is not None
        assert isinstance(meta, dict)
        assert len(meta) >= 3

    def test_copywrite_topic_field(self):
        from app.tools.copywrite_builder import CopywriteSkillBase
        meta = CopywriteSkillBase.clarify_meta
        assert "topic" in meta
        assert meta["topic"].when == ClarifyWhen.missing
        assert len(meta["topic"].options) >= 4

    def test_copywrite_style_field(self):
        from app.tools.copywrite_builder import CopywriteSkillBase
        meta = CopywriteSkillBase.clarify_meta
        assert "style" in meta
        assert meta["style"].when == ClarifyWhen.ambiguous

    def test_copywrite_audience_field(self):
        from app.tools.copywrite_builder import CopywriteSkillBase
        meta = CopywriteSkillBase.clarify_meta
        assert "target_audience" in meta
        assert meta["target_audience"].when == ClarifyWhen.missing


class TestPromptDrivenSkillClarifySchema:
    @pytest.fixture(autouse=True)
    def _ensure_registry(self):
        from app.tools.prompt_skills import scan_and_register_prompt_skills
        scan_and_register_prompt_skills()

    def _get_skill_cls(self, name: str):
        from app.tools.registry import get_skill_class_by_name
        return get_skill_class_by_name(name)

    def test_xhs_note_creator_has_clarify_meta(self):
        skill = self._get_skill_cls("xhs_note_creator")
        if skill is None:
            pytest.skip("xhs_note_creator not registered")
        meta = getattr(skill, "clarify_meta", None)
        assert meta is not None
        assert isinstance(meta, dict)
        assert "topic" in meta
        assert "style" in meta
        assert "target_audience" in meta
        assert "visual_style" in meta

    def test_xhs_note_creator_dependency_chain(self):
        skill = self._get_skill_cls("xhs_note_creator")
        if skill is None:
            pytest.skip("xhs_note_creator not registered")
        meta = skill.clarify_meta
        assert len(meta["style"].depends_on) > 0
        assert meta["style"].depends_on[0].field == "topic"
        assert len(meta["visual_style"].depends_on) > 0
        assert meta["visual_style"].depends_on[0].field == "style"

    def test_card_design_has_clarify_meta(self):
        skill = self._get_skill_cls("card_design")
        if skill is None:
            pytest.skip("card_design not registered")
        meta = getattr(skill, "clarify_meta", None)
        assert meta is not None
        assert "visual_style" in meta
        assert "layout" in meta

    def test_card_design_layout_depends_on_visual_style(self):
        skill = self._get_skill_cls("card_design")
        if skill is None:
            pytest.skip("card_design not registered")
        meta = skill.clarify_meta
        assert len(meta["layout"].depends_on) > 0
        assert meta["layout"].depends_on[0].field == "visual_style"

    def test_copywriting_has_clarify_meta(self):
        skill = self._get_skill_cls("copywriting")
        if skill is None:
            pytest.skip("copywriting not registered")
        meta = getattr(skill, "clarify_meta", None)
        assert meta is not None
        assert "topic" in meta
        assert "tone" in meta

    def test_search_skills_have_no_clarify_meta(self):
        for name in ["trending_search", "xhs_search", "vl_analyze"]:
            skill = self._get_skill_cls(name)
            if skill is None:
                continue
            meta = getattr(skill, "clarify_meta", None)
            assert meta is None or meta == {}, f"{name} should not have clarify_meta"


class TestClarifyMetaBatching:
    @pytest.fixture(autouse=True)
    def _ensure_registry(self):
        from app.tools.prompt_skills import scan_and_register_prompt_skills
        scan_and_register_prompt_skills()

    def _get_skill_cls(self, name: str):
        from app.tools.registry import get_skill_class_by_name
        return get_skill_class_by_name(name)

    def test_xhs_note_creator_batches(self):
        from app.agents.clarification_graph import collect_clarify_fields, build_batches
        skill = self._get_skill_cls("xhs_note_creator")
        if skill is None:
            pytest.skip("xhs_note_creator not registered")
        fields = collect_clarify_fields([skill], clarified_answers={})
        batches = build_batches(fields, clarified_answers={})
        assert len(batches) >= 1
        first_batch_fields = [q.id.split("__")[-1].replace("clarify_", "") for q in batches[0].questions]
        assert "topic" in first_batch_fields or "target_audience" in first_batch_fields

    def test_xhs_note_creator_progressive_batching(self):
        from app.agents.clarification_graph import collect_clarify_fields, build_batches
        skill = self._get_skill_cls("xhs_note_creator")
        if skill is None:
            pytest.skip("xhs_note_creator not registered")
        fields = collect_clarify_fields([skill], clarified_answers={})
        batches = build_batches(fields, clarified_answers={})
        assert len(batches) >= 1
        clarified = {"topic": "skill_share"}
        fields2 = collect_clarify_fields([skill], clarified_answers=clarified)
        batches2 = build_batches(fields2, clarified_answers=clarified)
        assert len(batches2) >= 1

    def test_card_design_batches(self):
        from app.agents.clarification_graph import collect_clarify_fields, build_batches
        skill = self._get_skill_cls("card_design")
        if skill is None:
            pytest.skip("card_design not registered")
        fields = collect_clarify_fields([skill], clarified_answers={})
        batches = build_batches(fields, clarified_answers={})
        assert len(batches) >= 1