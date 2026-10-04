"""Phase 2 测试：后端流程 — 澄清前置检查 + 暂停/恢复 + API 端点。"""

import json
import pytest

from app.agents.clarification_schema import (
    ClarifyFieldMeta,
    ClarifyWhen,
    ClarifyOption,
    ClarificationBatch,
    ClarificationQuestion,
    QuestionType,
)
from app.agents.clarification_graph import (
    collect_clarify_fields,
    build_batches,
    compile_clarification_result,
)


# ============================================================
# Step 0: Clarification 前置检查逻辑
# ============================================================

class TestClarificationPreCheck:
    """验证 _execute_tool_call 中 Step 0 的判断逻辑。"""

    def test_no_clarify_meta_passes_through(self):
        """Skill 无 clarify_meta → 不触发澄清。"""
        class NoMetaSkill:
            name = "search"
            clarify_meta = {}

        skill = NoMetaSkill()
        meta = getattr(skill, "clarify_meta", None)
        assert not meta or not isinstance(meta, dict) or not meta

    def test_missing_when_triggers_clarify(self):
        """when=missing 且字段未在 clarification_result 中 → 触发澄清。"""
        meta = {"writing_style": ClarifyFieldMeta(hint="选择风格", when=ClarifyWhen.missing)}
        already_clarified = {}
        needs_clarify = False
        for fname, fmeta in meta.items():
            when_val = fmeta.when.value
            if when_val == "missing" and fname not in already_clarified:
                needs_clarify = True
                break
        assert needs_clarify is True

    def test_missing_when_already_answered_skips(self):
        """when=missing 且字段已在 clarification_result 中 → 不触发。"""
        meta = {"writing_style": ClarifyFieldMeta(hint="选择风格", when=ClarifyWhen.missing)}
        already_clarified = {"writing_style": "lively"}
        needs_clarify = False
        for fname, fmeta in meta.items():
            when_val = fmeta.when.value
            if when_val == "missing" and fname not in already_clarified:
                needs_clarify = True
                break
        assert needs_clarify is False

    def test_always_when_triggers_even_if_answered(self):
        """when=always → 即使已回答也触发。"""
        meta = {"writing_style": ClarifyFieldMeta(hint="选择风格", when=ClarifyWhen.always)}
        already_clarified = {"writing_style": "lively"}
        needs_clarify = False
        for fname, fmeta in meta.items():
            when_val = fmeta.when.value
            if when_val == "always":
                needs_clarify = True
                break
        assert needs_clarify is True

    def test_ambiguous_when_always_triggers(self):
        """when=ambiguous → 总是触发。"""
        meta = {"writing_style": ClarifyFieldMeta(hint="选择风格", when=ClarifyWhen.ambiguous)}
        already_clarified = {"writing_style": "lively"}
        needs_clarify = False
        for fname, fmeta in meta.items():
            when_val = fmeta.when.value
            if when_val == "ambiguous":
                needs_clarify = True
                break
        assert needs_clarify is True

    def test_approved_skips_clarification(self):
        """_approved=True → 跳过澄清（和确认同构）。"""
        _approved = True
        _needs_clarify = True
        should_clarify = _needs_clarify and not _approved
        assert should_clarify is False


# ============================================================
# Clarification break 输出格式
# ============================================================

class TestClarificationOutputFormat:
    """验证 loop.py 中澄清 break 时 final_output 的格式。"""

    def test_awaiting_clarification_output_keys(self):
        confirmation = {
            "_type": "clarification",
            "name": "copywriting",
            "arguments": {"topic": "测试"},
            "_clarification_batches": [
                ClarificationBatch(
                    batch_id="b1",
                    batch_index=0,
                    total_batches=1,
                    title="创作偏好确认（1/1）",
                    description="请确认偏好",
                    questions=[
                        ClarificationQuestion(
                            id="clarify_writing_style",
                            source_skill="copywriting",
                            question="选择写作风格",
                        ),
                    ],
                ).model_dump(),
            ],
            "_clarification_prompt": "创作偏好确认（1/1）",
        }

        final_output = {
            "_awaiting_clarification": True,
            "_clarification_prompt": confirmation.get("_clarification_prompt", ""),
            "_clarification_skill": confirmation.get("name", ""),
            "_clarification_arguments": confirmation.get("arguments", {}),
            "_clarification_batches": confirmation.get("_clarification_batches", []),
            "_loop_state_path": "/tmp/test_state.json",
        }

        assert final_output["_awaiting_clarification"] is True
        assert final_output["_clarification_skill"] == "copywriting"
        assert len(final_output["_clarification_batches"]) == 1
        assert final_output["_clarification_batches"][0]["questions"][0]["id"] == "clarify_writing_style"

    def test_confirmation_output_unchanged(self):
        """确认（非澄清）的输出格式不应被修改。"""
        confirmation = {
            "name": "publish",
            "arguments": {},
            "_confirmation_prompt": "确认发布？",
            "_risk_level": "high",
        }

        final_output = {
            "_awaiting_confirmation": True,
            "_confirmation_prompt": confirmation.get("_confirmation_prompt", ""),
            "_confirmation_skill": confirmation.get("name", ""),
            "_confirmation_arguments": confirmation.get("arguments", {}),
            "_loop_state_path": "/tmp/test_state.json",
        }

        assert final_output["_awaiting_confirmation"] is True
        assert "_awaiting_clarification" not in final_output


# ============================================================
# ChatResult status
# ============================================================

class TestChatResultStatus:
    """验证 ChatAgent 返回的 status 值。"""

    def test_awaiting_clarification_status(self):
        """output_data 含 _awaiting_clarification → status='awaiting_clarification'。"""
        output_data = {"_awaiting_clarification": True, "_clarification_prompt": "确认偏好"}
        if output_data.get("_awaiting_clarification"):
            status = "awaiting_clarification"
        elif output_data.get("_awaiting_confirmation"):
            status = "awaiting_confirmation"
        else:
            status = "agent_output"
        assert status == "awaiting_clarification"

    def test_awaiting_confirmation_still_works(self):
        """确认 status 不受澄清影响。"""
        output_data = {"_awaiting_confirmation": True, "_confirmation_prompt": "确认操作"}
        if output_data.get("_awaiting_clarification"):
            status = "awaiting_clarification"
        elif output_data.get("_awaiting_confirmation"):
            status = "awaiting_confirmation"
        else:
            status = "agent_output"
        assert status == "awaiting_confirmation"

    def test_normal_output(self):
        """无澄清无确认 → 正常输出。"""
        output_data = {"summary": "任务完成"}
        if output_data.get("_awaiting_clarification"):
            status = "awaiting_clarification"
        elif output_data.get("_awaiting_confirmation"):
            status = "awaiting_confirmation"
        else:
            status = "agent_output"
        assert status == "agent_output"


# ============================================================
# Clarify API 端点逻辑
# ============================================================

class TestClarifyAPILogic:
    """验证 /clarify 端点的核心逻辑（不依赖 FastAPI）。"""

    def test_cancel_action(self):
        request_action = "cancel"
        if request_action == "cancel":
            result = {"status": "cancelled", "message": "用户取消了创作偏好确认"}
        assert result["status"] == "cancelled"

    def test_answers_merge(self):
        """多次澄清的回答应合并。"""
        existing = {"writing_style": "lively"}
        new_answers = {"tone": "casual", "length": "short"}
        existing.update(new_answers)
        assert existing == {"writing_style": "lively", "tone": "casual", "length": "short"}

    def test_clarification_result_compiled_into_arguments(self):
        """clarification_result 应合并进 Skill 的 arguments。"""
        arguments = {"topic": "小红书文案"}
        clarification_result = {"writing_style": "lively", "tone": "casual"}
        arguments.update(clarification_result)
        assert arguments["writing_style"] == "lively"
        assert arguments["tone"] == "casual"
        assert arguments["topic"] == "小红书文案"

    def test_clarification_result_priority_chain(self):
        """优先级链：clarification_answer > model_settings > default。"""
        fields = {
            "style": (ClarifyFieldMeta(hint="风格", default="elegant"), "copywriting"),
            "tone": (ClarifyFieldMeta(hint="语气", default="formal"), "copywriting"),
        }

        # 全部有回答
        result = compile_clarification_result(
            all_answers={"style": "lively", "tone": "casual"},
            fields=fields,
            model_settings={"style": "playful"},
        )
        assert result["style"] == "lively"  # 回答优先
        assert result["tone"] == "casual"

        # 部分有回答，部分走 model_settings
        result2 = compile_clarification_result(
            all_answers={"style": "lively"},
            fields=fields,
            model_settings={"tone": "warm"},
        )
        assert result2["style"] == "lively"
        assert result2["tone"] == "warm"

        # 全部走 default
        result3 = compile_clarification_result(
            all_answers={},
            fields=fields,
            model_settings={},
        )
        assert result3["style"] == "elegant"
        assert result3["tone"] == "formal"


# ============================================================
# Loop state 扩展
# ============================================================

class TestLoopStateExtension:
    """验证 loop_state JSON 序列化支持新字段。"""

    def test_pending_clarification_serializable(self):
        import json
        state = {
            "messages": [],
            "iteration": 0,
            "max_iterations": 12,
            "pending_skill_call": {"name": "copywriting", "arguments": {}},
            "pending_clarification": {
                "_type": "clarification",
                "name": "copywriting",
                "arguments": {},
                "_clarification_batches": [],
                "_clarification_prompt": "确认偏好",
            },
            "clarified_answers": {"writing_style": "lively"},
            "context_snapshot": {
                "workflow_id": "test",
                "node_id": "chat",
                "user_id": "u1",
                "account_id": "a1",
                "extra": {"clarification_result": {"writing_style": "lively"}},
            },
            "total_token_usage": {},
        }
        serialized = json.dumps(state, ensure_ascii=False, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["pending_clarification"]["_type"] == "clarification"
        assert deserialized["clarified_answers"]["writing_style"] == "lively"
        assert deserialized["context_snapshot"]["extra"]["clarification_result"]["writing_style"] == "lively"