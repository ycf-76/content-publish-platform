"""Phase 1 测试：clarification_schema + clarification_graph + base.py clarify_meta 注入。"""

import pytest

from app.agents.clarification_schema import (
    ClarifyWhen,
    ClarifyOption,
    ClarifyDepends,
    ClarifyFieldMeta,
    QuestionType,
    ClarificationQuestion,
    ClarificationBatch,
    ClarificationAnswer,
    ClarificationSubmitRequest,
    ClarificationSubmitResponse,
)
from app.agents.clarification_graph import (
    collect_clarify_fields,
    filter_by_depends_on,
    build_dependency_graph,
    topological_sort,
    build_batches,
    compile_clarification_result,
)
from app.tools.base import Skill


# ============================================================
# clarification_schema 类型定义
# ============================================================

class TestClarifyFieldMeta:
    def test_from_dict_full(self):
        data = {
            "hint": "选择写作风格",
            "when": "missing",
            "options": [
                {"label": "活泼少女", "value": "lively", "description": "轻松活泼"},
                {"label": "知性优雅", "value": "elegant", "description": "沉稳大气"},
            ],
            "default": "lively",
            "depends_on": [{"field": "platform", "value": "xiaohongshu"}],
            "question_type": "single_choice",
            "required": True,
        }
        meta = ClarifyFieldMeta.from_dict(data)
        assert meta.hint == "选择写作风格"
        assert meta.when == ClarifyWhen.missing
        assert len(meta.options) == 2
        assert meta.options[0].label == "活泼少女"
        assert meta.options[0].value == "lively"
        assert meta.default == "lively"
        assert len(meta.depends_on) == 1
        assert meta.depends_on[0].field == "platform"
        assert meta.question_type == QuestionType.single_choice
        assert meta.required is True

    def test_from_dict_minimal(self):
        data = {"hint": "输入标题"}
        meta = ClarifyFieldMeta.from_dict(data)
        assert meta.hint == "输入标题"
        assert meta.when == ClarifyWhen.missing
        assert meta.options == []
        assert meta.default == ""
        assert meta.depends_on == []
        assert meta.question_type == QuestionType.single_choice

    def test_from_dict_invalid_when_fallback(self):
        data = {"hint": "test", "when": "invalid_value"}
        meta = ClarifyFieldMeta.from_dict(data)
        assert meta.when == ClarifyWhen.missing

    def test_from_dict_invalid_question_type_fallback(self):
        data = {"hint": "test", "question_type": "nonexistent"}
        meta = ClarifyFieldMeta.from_dict(data)
        assert meta.question_type == QuestionType.single_choice

    def test_from_dict_preview_url_alias(self):
        data = {
            "hint": "选图片",
            "question_type": "image_select",
            "options": [
                {"label": "风格A", "value": "a", "preview": "https://img.example.com/a.jpg"},
            ],
        }
        meta = ClarifyFieldMeta.from_dict(data)
        assert meta.options[0].preview_url == "https://img.example.com/a.jpg"


class TestClarificationBatch:
    def test_batch_construction(self):
        batch = ClarificationBatch(
            batch_id="b1",
            batch_index=0,
            total_batches=2,
            title="创作偏好确认（1/2）",
            description="请确认偏好",
            questions=[
                ClarificationQuestion(
                    id="clarify_writing_style",
                    source_skill="copywriting",
                    question="选择写作风格",
                    options=[
                        ClarifyOption(label="活泼", value="lively"),
                    ],
                ),
            ],
            next_batch_hint="还有 1 批问题待确认",
        )
        assert batch.batch_index == 0
        assert batch.total_batches == 2
        assert len(batch.questions) == 1
        assert batch.questions[0].id == "clarify_writing_style"


# ============================================================
# clarification_graph 依赖图与分批
# ============================================================

class TestCollectClarifyFields:
    def test_collect_from_skills(self):
        class FakeSkill:
            name = "copywriting"
            clarify_meta = {
                "writing_style": ClarifyFieldMeta(hint="选择写作风格"),
                "tone": ClarifyFieldMeta(hint="选择语气"),
            }

        class FakeSkill2:
            name = "image_gen"
            clarify_meta = {
                "image_style": ClarifyFieldMeta(hint="选择图片风格"),
            }

        fields = collect_clarify_fields([FakeSkill(), FakeSkill2()])
        assert "writing_style" in fields
        assert "tone" in fields
        assert "image_style" in fields
        assert fields["writing_style"][1] == "copywriting"
        assert fields["image_style"][1] == "image_gen"

    def test_dedup_same_field_name(self):
        class Skill1:
            name = "copywriting"
            clarify_meta = {"style": ClarifyFieldMeta(hint="风格1")}

        class Skill2:
            name = "audit"
            clarify_meta = {"style": ClarifyFieldMeta(hint="风格2")}

        fields = collect_clarify_fields([Skill1(), Skill2()])
        assert len(fields) == 1
        assert fields["style"][0].hint == "风格1"

    def test_skip_no_clarify_meta(self):
        class NoMeta:
            name = "search"

        fields = collect_clarify_fields([NoMeta()])
        assert fields == {}

    def test_always_when_dedup_with_answered(self):
        class SkillAlways:
            name = "copywriting"
            clarify_meta = {
                "style": ClarifyFieldMeta(hint="风格", when=ClarifyWhen.always),
            }

        fields = collect_clarify_fields(
            [SkillAlways()],
            clarified_answers={"style": "lively"},
        )
        assert "style" not in fields


class TestFilterByDependsOn:
    def test_no_depends_pass_through(self):
        fields = {
            "style": (ClarifyFieldMeta(hint="风格"), "copywriting"),
        }
        result = filter_by_depends_on(fields, {})
        assert "style" in result

    def test_depends_satisfied(self):
        fields = {
            "style": (ClarifyFieldMeta(
                hint="风格",
                depends_on=[ClarifyDepends(field="platform", value="xiaohongshu")],
            ), "copywriting"),
        }
        result = filter_by_depends_on(fields, {"platform": "xiaohongshu"})
        assert "style" in result

    def test_depends_not_satisfied(self):
        fields = {
            "style": (ClarifyFieldMeta(
                hint="风格",
                depends_on=[ClarifyDepends(field="platform", value="xiaohongshu")],
            ), "copywriting"),
        }
        result = filter_by_depends_on(fields, {"platform": "douyin"})
        assert "style" not in result

    def test_multiple_depends_all_must_satisfy(self):
        fields = {
            "style": (ClarifyFieldMeta(
                hint="风格",
                depends_on=[
                    ClarifyDepends(field="platform", value="xiaohongshu"),
                    ClarifyDepends(field="mode", value="pro"),
                ],
            ), "copywriting"),
        }
        result = filter_by_depends_on(fields, {"platform": "xiaohongshu", "mode": "pro"})
        assert "style" in result

        result2 = filter_by_depends_on(fields, {"platform": "xiaohongshu", "mode": "basic"})
        assert "style" not in result2


class TestTopologicalSort:
    def test_no_deps_single_level(self):
        graph = {"a": set(), "b": set(), "c": set()}
        levels = topological_sort(graph)
        assert levels is not None
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_linear_chain(self):
        graph = {"a": set(), "b": {"a"}, "c": {"b"}}
        levels = topological_sort(graph)
        assert levels is not None
        assert levels == [["a"], ["b"], ["c"]]

    def test_diamond(self):
        graph = {"a": set(), "b": {"a"}, "c": {"a"}, "d": {"b", "c"}}
        levels = topological_sort(graph)
        assert levels is not None
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]

    def test_cycle_detected(self):
        graph = {"a": {"b"}, "b": {"a"}}
        levels = topological_sort(graph)
        assert levels is None


class TestBuildBatches:
    def test_single_batch(self):
        fields = {
            "style": (ClarifyFieldMeta(hint="选择风格"), "copywriting"),
            "tone": (ClarifyFieldMeta(hint="选择语气"), "copywriting"),
        }
        batches = build_batches(fields)
        assert len(batches) == 1
        assert batches[0].total_batches == 1
        assert len(batches[0].questions) == 2

    def test_multi_level_batching(self):
        fields = {
            "platform": (ClarifyFieldMeta(hint="选择平台"), "copywriting"),
            "style": (ClarifyFieldMeta(
                hint="选择风格",
                depends_on=[ClarifyDepends(field="platform", value="xiaohongshu")],
            ), "copywriting"),
        }
        # 第一批：platform 无依赖，style 依赖 platform 但尚未回答 → 被过滤
        batches_round1 = build_batches(fields, clarified_answers={})
        assert len(batches_round1) == 1
        assert batches_round1[0].questions[0].id == "copywriting__clarify_platform"

        # 第二批：用户回答 platform=xiaohongshu 后，style 的 depends_on 满足
        # 此时 platform 无依赖仍在，style 依赖满足也出现
        # 拓扑排序分 2 层：[platform], [style]
        batches_round2 = build_batches(fields, clarified_answers={"platform": "xiaohongshu"})
        assert len(batches_round2) == 2
        assert batches_round2[0].questions[0].id == "copywriting__clarify_platform"
        assert batches_round2[1].questions[0].id == "copywriting__clarify_style"

    def test_empty_fields(self):
        batches = build_batches({})
        assert batches == []


class TestCompileClarificationResult:
    def test_priority_chain(self):
        fields = {
            "style": (ClarifyFieldMeta(hint="风格", default="elegant"), "copywriting"),
            "tone": (ClarifyFieldMeta(hint="语气", default="formal"), "copywriting"),
        }

        # 1. clarification_answer 优先
        result = compile_clarification_result(
            all_answers={"style": "lively", "tone": "casual"},
            fields=fields,
            model_settings={"style": "elegant"},
        )
        assert result["style"] == "lively"
        assert result["tone"] == "casual"

    def test_model_settings_fallback(self):
        fields = {
            "style": (ClarifyFieldMeta(hint="风格", default="elegant"), "copywriting"),
        }
        result = compile_clarification_result(
            all_answers={},
            fields=fields,
            model_settings={"style": "playful"},
        )
        assert result["style"] == "playful"

    def test_default_fallback(self):
        fields = {
            "style": (ClarifyFieldMeta(hint="风格", default="elegant"), "copywriting"),
        }
        result = compile_clarification_result(
            all_answers={},
            fields=fields,
            model_settings={},
        )
        assert result["style"] == "elegant"

    def test_writing_prefix_model_settings(self):
        fields = {
            "style": (ClarifyFieldMeta(hint="风格", default="elegant"), "copywriting"),
        }
        result = compile_clarification_result(
            all_answers={},
            fields=fields,
            model_settings={"writing_style": "playful"},
        )
        assert result["style"] == "playful"


# ============================================================
# Skill 基类 clarify_meta 属性
# ============================================================

class TestSkillClarifyMeta:
    def test_default_empty(self):
        class DummySkill(Skill):
            node_type = "test"
            name = "dummy"
            async def execute(self, inputs):
                return {}

        assert DummySkill.clarify_meta == {}

    def test_with_clarify_meta(self):
        class StyledSkill(Skill):
            node_type = "copywrite"
            name = "styled"
            clarify_meta = {
                "writing_style": ClarifyFieldMeta(hint="选择写作风格"),
                "tone": ClarifyFieldMeta(hint="选择语气"),
            }
            async def execute(self, inputs):
                return {}

        assert "writing_style" in StyledSkill.clarify_meta
        assert StyledSkill.clarify_meta["tone"].hint == "选择语气"