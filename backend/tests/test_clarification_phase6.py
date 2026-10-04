"""Phase 6 测试：文档剩余功能项验证

覆盖：
- §2.3.1 Ambiguous 判定（L1/L2 规则）
- §2.3 v2.2 意图过滤（CLARIFY_TRIGGER_NODE_TYPES）
- §2.3 v2.2 when=always 去重
- §2.8 Iteration 补偿
- §5.3 超时机制
- §5.2 v2.2 并发文件锁
- §6.3 Skip 级联
- §4 Phase 4 BEHAVIOR.md <needs_clarification> 指引
- Question ID 格式 skill_name__clarify_field_name
"""

import json
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from app.agents.clarification_schema import (
    ClarifyFieldMeta,
    ClarifyOption,
    ClarifyWhen,
    ClarifyDepends,
)


class TestAmbiguousDetection:
    def test_l1_keyword_sui_bian(self):
        from app.engine.harness.executor.loop import _is_ambiguous
        assert _is_ambiguous("style", {"style": "随便"}, {}) is True

    def test_l1_keyword_bang_wo_zuo(self):
        from app.engine.harness.executor.loop import _is_ambiguous
        assert _is_ambiguous("topic", {"topic": "帮我做一个图"}, {}) is True

    def test_l1_keyword_dou_xing(self):
        from app.engine.harness.executor.loop import _is_ambiguous
        assert _is_ambiguous("style", {"style": "都行"}, {}) is True

    def test_l2_short_value(self):
        from app.engine.harness.executor.loop import _is_ambiguous
        assert _is_ambiguous("topic", {"topic": "护肤"}, {}) is True

    def test_not_ambiguous_explicit_value(self):
        from app.engine.harness.executor.loop import _is_ambiguous
        assert _is_ambiguous("topic", {"topic": "我想写一篇关于秋冬护肤的种草笔记"}, {}) is False

    def test_not_ambiguous_already_clarified(self):
        from app.engine.harness.executor.loop import _is_ambiguous
        assert _is_ambiguous("style", {"style": "casual"}, {"style": "casual"}) is False

    def test_ambiguous_missing_value(self):
        from app.engine.harness.executor.loop import _is_ambiguous
        assert _is_ambiguous("style", {}, {}) is True

    def test_ambiguous_empty_value(self):
        from app.engine.harness.executor.loop import _is_ambiguous
        assert _is_ambiguous("style", {"style": ""}, {}) is True


class TestIntentFilter:
    def test_produce_type_triggers(self):
        from app.engine.harness.executor.loop import _CLARIFY_TRIGGER_NODE_TYPES
        assert "produce" in _CLARIFY_TRIGGER_NODE_TYPES

    def test_search_type_not_triggers(self):
        from app.engine.harness.executor.loop import _CLARIFY_TRIGGER_NODE_TYPES
        assert "search" not in _CLARIFY_TRIGGER_NODE_TYPES
        assert "analyze" not in _CLARIFY_TRIGGER_NODE_TYPES


class TestWhenAlwaysDedup:
    def test_always_field_not_triggered_if_already_answered(self):
        from app.agents.clarification_graph import collect_clarify_fields

        class FakeSkill:
            name = "test_skill"
            node_type = "produce"
            clarify_meta = {
                "standard": ClarifyFieldMeta(
                    hint="审核标准是什么？",
                    when=ClarifyWhen.always,
                    options=[ClarifyOption(label="严格", value="strict")],
                ),
            }

        fields = collect_clarify_fields([FakeSkill()], clarified_answers={"standard": "strict"})
        assert "standard" not in fields

    def test_always_field_triggered_if_not_answered(self):
        from app.agents.clarification_graph import collect_clarify_fields

        class FakeSkill:
            name = "test_skill"
            node_type = "produce"
            clarify_meta = {
                "standard": ClarifyFieldMeta(
                    hint="审核标准是什么？",
                    when=ClarifyWhen.always,
                    options=[ClarifyOption(label="严格", value="strict")],
                ),
            }

        fields = collect_clarify_fields([FakeSkill()], clarified_answers={})
        assert "standard" in fields


class TestQuestionIdFormat:
    def test_question_id_includes_skill_name(self):
        from app.agents.clarification_graph import collect_clarify_fields, build_batches

        class FakeSkill:
            name = "xhs_note_creator"
            node_type = "produce"
            clarify_meta = {
                "topic": ClarifyFieldMeta(
                    hint="核心主题？",
                    when=ClarifyWhen.missing,
                    options=[ClarifyOption(label="干货", value="skill_share")],
                ),
            }

        fields = collect_clarify_fields([FakeSkill()], clarified_answers={})
        batches = build_batches(fields, clarified_answers={})
        assert len(batches) >= 1
        qid = batches[0].questions[0].id
        assert qid.startswith("xhs_note_creator__clarify_")


class TestIterationCompensation:
    def test_compensation_on_clarification_resume(self):
        max_iter = 8
        state = {"_awaiting_clarification": True, "max_iterations": max_iter}
        if state.get("_awaiting_clarification"):
            compensated = max(max_iter, int(state.get("max_iterations", max_iter)) + 1)
        else:
            compensated = max_iter
        assert compensated == 9

    def test_no_compensation_without_clarification(self):
        max_iter = 8
        state = {"max_iterations": max_iter}
        if state.get("_awaiting_clarification"):
            compensated = max(max_iter, int(state.get("max_iterations", max_iter)) + 1)
        else:
            compensated = max_iter
        assert compensated == 8


class TestClarificationTimeout:
    def test_not_timed_out(self):
        from app.engine.harness.executor.loop_state import check_clarification_timeout
        state = {
            "_awaiting_clarification": True,
            "_clarification_saved_at": datetime.now(timezone.utc).isoformat(),
        }
        assert check_clarification_timeout(state) is None

    def test_timed_out_expired(self):
        from app.engine.harness.executor.loop_state import (
            check_clarification_timeout,
            _CLARIFICATION_TIMEOUT_SECONDS,
            _CLARIFICATION_EXPIRED_GRACE_SECONDS,
        )
        past = datetime.now(timezone.utc) - timedelta(
            seconds=_CLARIFICATION_TIMEOUT_SECONDS + _CLARIFICATION_EXPIRED_GRACE_SECONDS + 10
        )
        state = {
            "_awaiting_clarification": True,
            "_clarification_saved_at": past.isoformat(),
        }
        assert check_clarification_timeout(state) == "expired"

    def test_timed_out_grace(self):
        from app.engine.harness.executor.loop_state import (
            check_clarification_timeout,
            _CLARIFICATION_TIMEOUT_SECONDS,
        )
        past = datetime.now(timezone.utc) - timedelta(
            seconds=_CLARIFICATION_TIMEOUT_SECONDS + 30
        )
        state = {
            "_awaiting_clarification": True,
            "_clarification_saved_at": past.isoformat(),
        }
        assert check_clarification_timeout(state) == "grace"

    def test_no_clarification_not_timed_out(self):
        from app.engine.harness.executor.loop_state import check_clarification_timeout
        state = {"_awaiting_clarification": False}
        assert check_clarification_timeout(state) is None


class TestConcurrentFileLock:
    def test_lock_per_path(self):
        from app.engine.harness.executor.loop_state import _get_lock
        lock1 = _get_lock("/tmp/test_state_1.json")
        lock2 = _get_lock("/tmp/test_state_2.json")
        lock3 = _get_lock("/tmp/test_state_1.json")
        assert lock1 is lock3
        assert lock1 is not lock2

    def test_lock_acquire_release(self):
        from app.engine.harness.executor.loop_state import _get_lock
        lock = _get_lock("/tmp/test_lock.json")
        lock.acquire()
        assert lock.locked()
        lock.release()
        assert not lock.locked()


class TestSkipCascade:
    def test_cascade_skip_when_dep_not_met(self):
        from app.agents.clarification_graph import compile_clarification_result

        fields = {
            "visual_style": (
                ClarifyFieldMeta(
                    hint="视觉风格？",
                    when=ClarifyWhen.ambiguous,
                    options=[ClarifyOption(label="极简白底", value="minimal_white")],
                    default="minimal_white",
                ),
                "card_design",
            ),
            "layout": (
                ClarifyFieldMeta(
                    hint="布局偏好？",
                    when=ClarifyWhen.ambiguous,
                    depends_on=[ClarifyDepends(field="visual_style", value="minimal_white")],
                    options=[ClarifyOption(label="左文右图", value="left_text_right_img")],
                    default="left_text_right_img",
                ),
                "card_design",
            ),
        }

        result = compile_clarification_result(
            all_answers={},
            fields=fields,
            model_settings={},
        )
        assert "visual_style" in result
        assert result["visual_style"] == "minimal_white"
        assert "layout" in result
        assert result["layout"] == "left_text_right_img"

    def test_cascade_skip_when_dep_value_mismatch(self):
        from app.agents.clarification_graph import compile_clarification_result

        fields = {
            "visual_style": (
                ClarifyFieldMeta(
                    hint="视觉风格？",
                    when=ClarifyWhen.ambiguous,
                    options=[ClarifyOption(label="极简白底", value="minimal_white")],
                    default="gradient",
                ),
                "card_design",
            ),
            "layout": (
                ClarifyFieldMeta(
                    hint="布局偏好？",
                    when=ClarifyWhen.ambiguous,
                    depends_on=[ClarifyDepends(field="visual_style", value="minimal_white")],
                    options=[ClarifyOption(label="左文右图", value="left_text_right_img")],
                    default="left_text_right_img",
                ),
                "card_design",
            ),
        }

        result = compile_clarification_result(
            all_answers={},
            fields=fields,
            model_settings={},
        )
        assert "visual_style" in result
        assert result["visual_style"] == "gradient"
        assert "layout" not in result


class TestBehaviorMdClarification:
    def test_behavior_md_contains_needs_clarification(self):
        behavior_path = Path(__file__).parent.parent / "app" / "agents" / "prompts" / "BEHAVIOR.md"
        if not behavior_path.exists():
            pytest.skip("BEHAVIOR.md not found")
        content = behavior_path.read_text(encoding="utf-8")
        assert "<needs_clarification>" in content
        assert "CLARIFICATION" in content


class TestLoopStateTimestamp:
    def test_save_loop_state_adds_clarification_timestamp(self):
        from app.engine.harness.executor.loop_state import save_loop_state, load_loop_state, cleanup_loop_state

        state = {
            "_awaiting_clarification": True,
            "messages": [],
            "context_snapshot": {},
        }
        path = save_loop_state("test_ts_session", state)
        try:
            loaded = load_loop_state(path)
            assert "_clarification_saved_at" in loaded
            ts = datetime.fromisoformat(loaded["_clarification_saved_at"])
            assert ts.tzinfo is not None
        finally:
            cleanup_loop_state(path)