"""测试 LLM 能否驱动图文 Skill 完成图文作品。

覆盖维度：
1. Skill 注册验证 — 图文相关 Skill 是否正确注册到 SkillRegistry
2. PromptDrivenSkill 加载验证 — 图文 .md Skill 是否被正确解析和注册
3. 创作类型 Skill 解析验证 — creation_type="image_text" 是否解析出正确的 Skill 子集
4. Mock LLM 驱动 ReAct Loop — 模拟 LLM 自主选择图文 Skill 并执行
5. Mock LLM 驱动完整图文创作流程 — 模拟 LLM 依次调用 xhs_note_creator → copywrite → card_xiaohongshu
"""

from __future__ import annotations

import asyncio
import json
import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.base import Skill, PromptDrivenSkill
from app.tools.registry import SkillRegistry, ensure_builtin_skills_registered


IMAGE_TEXT_PRODUCE_SKILLS = {
    "xhs_note_creator",
    "copywriting",
    "card_xiaohongshu",
    "card_quote",
    "infographic",
    "poster_hero",
    "comparison_card",
    "style_transfer",
}

IMAGE_TEXT_ALL_SKILL_NAMES = {
    "xhs_note_creator", "copywriting", "social_content",
    "card_xiaohongshu", "card_quote", "card_design", "infographic",
    "poster_hero", "comparison_card", "style_transfer",
    "content_matrix", "topic_evaluator", "hook_generator", "carousel_planner",
    "voice_builder", "positioning_analysis",
    "publish_checklist", "quality_gate", "risk_scanner", "content_repurposing",
    "trending_topics", "competitor_analysis", "content_gap_analysis",
    "data_tracker", "comment_insights", "strategy_advisor", "content_postmortem",
    "text_polisher", "text_condenser", "caption_hashtag", "post_formatter",
    "persona_check",
    "casual", "elegant", "lively_girl", "professional",
    "trending_search", "xhs_search",
}


class _ScriptedLLM:
    """脚本化 LLM：按预设轮次返回指定响应，模拟 LLM 自主决策。"""

    model_name = "mock-scripted"

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._call_count = 0
        self._all_messages: list[list[dict]] = []

    async def chat(self, messages, response_format=None):
        self._all_messages.append(messages)
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
        else:
            resp = json.dumps({
                "thought": "已完成所有步骤",
                "final": True,
                "output": {"result": "图文作品生成完成"},
            })
        self._call_count += 1
        return {"content": resp, "reasoning_content": None, "token_usage": 100}

    async def stream_chat(self, messages, response_format=None, tools=None):
        resp = await self.chat(messages, response_format)
        yield {"content": resp["content"], "reasoning_content": None, "token_usage": 100}


def _make_tool_call_json(thought: str, tool_name: str, arguments: dict, final: bool = False):
    return json.dumps({
        "thought": thought,
        "tool_calls": [{"name": tool_name, "arguments": arguments}],
        "final": final,
    }, ensure_ascii=False)


def _make_final_json(thought: str, output: dict):
    return json.dumps({
        "thought": thought,
        "final": True,
        "output": output,
    }, ensure_ascii=False)


# ============================================================================
# Test 1: Skill 注册验证
# ============================================================================


class TestImageTextSkillRegistration:
    """验证图文相关 Skill 是否正确注册到 SkillRegistry。"""

    @pytest.fixture(autouse=True)
    def _setup_registry(self):
        ensure_builtin_skills_registered()
        self.registry = SkillRegistry.instance()

    def test_prompt_skills_are_registered(self):
        """PromptDrivenSkill .md 文件应被自动扫描并注册。"""
        all_skills = self.registry.all_skill_classes()
        prompt_skills = [s for s in all_skills if issubclass(s, PromptDrivenSkill)]
        skill_names = {s.name for s in prompt_skills}
        print(f"\n[已注册 PromptDrivenSkill] ({len(prompt_skills)}): {sorted(skill_names)}")

        for name in IMAGE_TEXT_PRODUCE_SKILLS:
            assert name in skill_names, f"图文 produce Skill '{name}' 未注册"

    def test_xhs_note_creator_skill_exists(self):
        """小红书笔记创作 Skill 必须存在。"""
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        assert skill_cls is not None, "xhs_note_creator Skill 未注册"
        assert issubclass(skill_cls, PromptDrivenSkill)
        assert skill_cls.node_type == "produce"

    def test_card_xiaohongshu_skill_exists(self):
        """小红书知识卡片 Skill 必须存在。"""
        skill_cls = self.registry.get("produce", "card_xiaohongshu")
        assert skill_cls is not None, "card_xiaohongshu Skill 未注册"
        assert issubclass(skill_cls, PromptDrivenSkill)
        assert skill_cls.node_type == "produce"

    def test_copywrite_skills_exist(self):
        """文案 Skill 集合必须存在。"""
        for style_name in ("lively_girl", "elegant", "professional", "casual"):
            skill_cls = self.registry.get("copywrite", style_name)
            assert skill_cls is not None, f"文案 Skill '{style_name}' 未注册"

    def test_image_text_skills_have_correct_node_types(self):
        """图文 Skill 的 node_type 应与预期一致。"""
        produce_skills = self.registry.list_by_node("produce")
        produce_names = {s["name"] for s in produce_skills}
        for name in IMAGE_TEXT_PRODUCE_SKILLS:
            assert name in produce_names, f"Skill '{name}' 不在 produce 节点下"


# ============================================================================
# Test 2: PromptDrivenSkill 内容加载验证
# ============================================================================


class TestPromptDrivenSkillContent:
    """验证图文 PromptDrivenSkill 的 .md 内容是否正确加载。"""

    @pytest.fixture(autouse=True)
    def _setup_registry(self):
        ensure_builtin_skills_registered()
        self.registry = SkillRegistry.instance()

    def test_xhs_note_creator_has_trigger_words(self):
        """xhs_note_creator 应有触发词。"""
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        assert len(skill_cls.trigger_words) > 0
        assert "小红书笔记" in skill_cls.trigger_words
        assert "图文笔记" in skill_cls.trigger_words

    def test_card_xiaohongshu_has_trigger_words(self):
        """card_xiaohongshu 应有触发词。"""
        skill_cls = self.registry.get("produce", "card_xiaohongshu")
        assert len(skill_cls.trigger_words) > 0
        assert "小红书卡片" in skill_cls.trigger_words

    def test_xhs_note_creator_has_references(self):
        """xhs_note_creator 应引用了参考知识文件。"""
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        assert len(skill_cls.reference_paths) > 0

    def test_card_xiaohongshu_has_references(self):
        """card_xiaohongshu 应引用了参考知识文件。"""
        skill_cls = self.registry.get("produce", "card_xiaohongshu")
        assert len(skill_cls.reference_paths) > 0

    def test_xhs_note_creator_skill_md_loads(self):
        """xhs_note_creator 的 SKILL.md 应能正确加载。"""
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        md_content = skill_cls._load_skill_md()
        assert len(md_content) > 100
        assert "小红书" in md_content

    def test_card_xiaohongshu_skill_md_loads(self):
        """card_xiaohongshu 的 SKILL.md 应能正确加载。"""
        skill_cls = self.registry.get("produce", "card_xiaohongshu")
        md_content = skill_cls._load_skill_md()
        assert len(md_content) > 100
        assert "1080" in md_content
        assert "1440" in md_content


# ============================================================================
# Test 3: 创作类型 Skill 解析验证
# ============================================================================


class TestCreationTypeSkillResolution:
    """验证 creation_type="image_text" 是否解析出正确的 Skill 子集。"""

    def test_image_text_creation_type_resolves_correct_skills(self):
        from app.agents.registry import CREATION_TYPE_SKILLS, _resolve_creation_type_skills

        mapping = CREATION_TYPE_SKILLS.get("image_text")
        assert mapping is not None, "image_text 创作类型未定义"

        all_names = _resolve_creation_type_skills("image_text")
        assert all_names is not None
        assert len(all_names) > 0

        for name in IMAGE_TEXT_PRODUCE_SKILLS:
            assert name in all_names, f"图文 produce Skill '{name}' 未在 image_text 解析结果中"

        print(f"\n[image_text 解析的 Skill] ({len(all_names)}): {sorted(all_names)}")

    def test_image_text_includes_core_skills(self):
        from app.agents.registry import _resolve_creation_type_skills

        names = _resolve_creation_type_skills("image_text")
        assert "xhs_note_creator" in names
        assert "card_xiaohongshu" in names
        assert "copywriting" in names
        assert "lively_girl" in names

    def test_image_text_includes_always_load_skills(self):
        from app.agents.registry import _resolve_creation_type_skills, ALWAYS_LOAD_SKILLS

        names = _resolve_creation_type_skills("image_text")
        for name in ALWAYS_LOAD_SKILLS:
            assert name in names, f"ALWAYS_LOAD Skill '{name}' 未包含"


# ============================================================================
# Test 4: LLM 路由验证 — ChatAgent 在有 LLM 时应走 agentic loop
# ============================================================================


class TestLLMRoutingForImageText:
    """验证 ChatAgent 在有 LLM 时正确路由到 agentic loop（而非 fallback）。"""

    @pytest.mark.asyncio
    async def test_chat_agent_routes_to_agentic_loop_with_llm(self):
        """有 LLM 时，ChatAgent 应走 agentic loop（status=agent_output），而非 fallback。"""
        from app.agents.chat_agent import ChatAgent
        from app.engine.schemas import AgentOutput

        llm = _ScriptedLLM([
            json.dumps({"thought": "完成", "final": True, "output": {"result": "图文创作完成"}}),
        ])

        class _FakeHarnessWithRun:
            llm = None
            run_called = False

            async def run(self, input_data, context):
                self.run_called = True
                return AgentOutput(output={"result": "图文创作完成", "skills_used": ["xhs_note_creator"]})

            async def shutdown(self):
                pass

        class _FakeReg:
            def __init__(self):
                self.harness = _FakeHarnessWithRun()

            def build_harness(self, agent_id, workflow_id=None, creation_type=None):
                return self.harness

        registry = _FakeReg()
        agent = ChatAgent(registry=registry, llm=llm)
        result = await agent.process("帮我写小红书图文笔记", "s1", "u1")

        assert result.status == "agent_output"
        assert result.output is not None
        assert result.output.output.get("result") == "图文创作完成"
        print(f"\n[路由结果] status={result.status}, output={result.output.output}")

    @pytest.mark.asyncio
    async def test_chat_agent_falls_back_without_llm(self):
        """无 LLM 时，ChatAgent 应走 fallback 路由（status=chat）。"""
        from app.agents.chat_agent import ChatAgent

        class _FakeHarnessNoLLM:
            llm = None

            async def run(self, input_data, context):
                pass

            async def shutdown(self):
                pass

        class _FakeReg:
            def build_harness(self, agent_id, workflow_id=None, creation_type=None):
                return _FakeHarnessNoLLM()

        agent = ChatAgent(registry=_FakeReg())
        result = await agent.process("帮我写小红书图文笔记", "s1", "u1")

        assert result.status == "chat"
        print(f"\n[无 LLM 路由] status={result.status}")


# ============================================================================
# Test 5: LLM 驱动 PromptDrivenSkill 完整图文创作流程
# ============================================================================


class TestLLMDrivesFullImageTextWorkflow:
    """验证 LLM 能依次驱动多个图文 PromptDrivenSkill 完成完整创作流程。

    核心验证点：
    - xhs_note_creator Skill 的 execute 能被 LLM 驱动并返回结构化结果
    - card_xiaohongshu Skill 的 execute 能被 LLM 驱动并返回 HTML 卡片
    - 多个 Skill 可以串联执行
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        ensure_builtin_skills_registered()
        self.registry = SkillRegistry.instance()

    @pytest.mark.asyncio
    async def test_xhs_note_creator_then_card_xiaohongshu_pipeline(self):
        """LLM 驱动 xhs_note_creator → card_xiaohongshu 串联执行。"""
        skill_note = self.registry.get("produce", "xhs_note_creator")()
        skill_card = self.registry.get("produce", "card_xiaohongshu")()

        note_result = json.dumps({
            "title": "极简生活｜5个习惯让你越活越轻盈",
            "content": "极简不是扔东西，而是让每件物品都有存在的理由...",
            "tags": ["极简生活", "断舍离", "生活方式"],
            "card_plan": [
                {"type": "cover", "title": "极简生活"},
                {"type": "content", "title": "习惯1：一进一出"},
                {"type": "content", "title": "习惯2：5分钟整理"},
                {"type": "content", "title": "习惯3：数字极简"},
                {"type": "ending", "title": "开始你的极简之旅"},
            ],
        }, ensure_ascii=False)

        card_result = "<!--card-html--><html><body><div class='card' style='width:1080px;height:1440px;'>卡片1</div></body></html><!--/card-html-->"

        mock_llm = _ScriptedLLM([note_result, card_result])

        step1 = await skill_note.execute({
            "llm": mock_llm,
            "topic": "极简生活",
            "platform": "小红书",
        })

        assert isinstance(step1, dict)
        assert "error" not in step1 or step1.get("error") is None
        print(f"\n[Step1 xhs_note_creator] LLM调用={mock_llm._call_count}, 结果keys={list(step1.keys())}")

        step2 = await skill_card.execute({
            "llm": mock_llm,
            "topic": "极简生活",
            "content": note_result,
            "platform": "小红书",
        })

        assert isinstance(step2, dict)
        print(f"[Step2 card_xiaohongshu] LLM调用={mock_llm._call_count}, 结果keys={list(step2.keys())}")
        print(f"[总LLM调用次数] {mock_llm._call_count}")

        assert mock_llm._call_count == 2

    @pytest.mark.asyncio
    async def test_copywrite_then_card_pipeline(self):
        """LLM 驱动 copywrite → card_xiaohongshu 串联执行。"""
        skill_copywrite = self.registry.get("copywrite", "lively_girl")()
        skill_card = self.registry.get("produce", "card_xiaohongshu")()

        copywrite_result = json.dumps({
            "title": "AI教育也太香了吧！",
            "content": "姐妹们！AI教育真的绝绝子...",
            "tags": ["AI教育", "未来课堂", "教育科技"],
        }, ensure_ascii=False)

        card_result = "<!--card-html--><html><body>卡片HTML</body></html><!--/card-html-->"

        mock_llm = _ScriptedLLM([copywrite_result, card_result])

        step1 = await skill_copywrite.execute({
            "llm": mock_llm,
            "topic": "AI教育",
        })

        assert isinstance(step1, dict)
        print(f"\n[Step1 lively_girl copywrite] LLM调用={mock_llm._call_count}")

        step2 = await skill_card.execute({
            "llm": mock_llm,
            "topic": "AI教育",
            "content": copywrite_result,
        })

        assert isinstance(step2, dict)
        print(f"[Step2 card_xiaohongshu] LLM调用={mock_llm._call_count}")
        assert mock_llm._call_count == 2


# ============================================================================
# Test 6: PromptDrivenSkill execute 验证
# ============================================================================


class TestPromptDrivenSkillExecution:
    """验证 PromptDrivenSkill 的 execute 方法能否正确调用 LLM。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        ensure_builtin_skills_registered()
        self.registry = SkillRegistry.instance()

    @pytest.mark.asyncio
    async def test_xhs_note_creator_execute_with_mock_llm(self):
        """xhs_note_creator 的 execute 应能正确调用 LLM 并返回结构化结果。"""
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        skill = skill_cls()

        mock_llm = _ScriptedLLM([
            json.dumps({
                "title": "AI教育：5个你不知道的真相",
                "content": "AI正在改变教育的方方面面...",
                "tags": ["AI教育", "未来课堂"],
                "card_plan": [
                    {"type": "cover", "title": "AI教育真相"},
                    {"type": "content", "title": "个性化学习"},
                    {"type": "ending", "title": "行动号召"},
                ],
            }, ensure_ascii=False),
        ])

        result = await skill.execute({
            "llm": mock_llm,
            "topic": "AI教育",
            "platform": "小红书",
        })

        assert isinstance(result, dict)
        assert "error" not in result or result.get("error") is None
        print(f"\n[xhs_note_creator execute 结果] {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")

    @pytest.mark.asyncio
    async def test_card_xiaohongshu_execute_with_mock_llm(self):
        """card_xiaohongshu 的 execute 应能正确调用 LLM 并返回 HTML 卡片。"""
        skill_cls = self.registry.get("produce", "card_xiaohongshu")
        skill = skill_cls()

        mock_llm = _ScriptedLLM([
            "<!--card-html--><!DOCTYPE html><html><head><style>.card{width:1080px;height:1440px;}</style></head><body><div class='card'>测试卡片</div></body></html><!--/card-html-->",
        ])

        result = await skill.execute({
            "llm": mock_llm,
            "topic": "极简生活",
            "platform": "小红书",
        })

        assert isinstance(result, dict)
        print(f"\n[card_xiaohongshu execute 结果] {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")

    @pytest.mark.asyncio
    async def test_prompt_skill_without_llm_returns_error(self):
        """没有 LLM 时，PromptDrivenSkill 应返回错误而非崩溃。"""
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        skill = skill_cls()

        result = await skill.execute({
            "topic": "AI教育",
        })

        assert isinstance(result, dict)
        assert "error" in result
        assert result.get("verdict") == "❌ LLM不可用"


# ============================================================================
# Test 7: Skill 触发词匹配验证
# ============================================================================


class TestSkillTriggerWordMatching:
    """验证图文 Skill 的触发词能否正确匹配用户意图。"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        ensure_builtin_skills_registered()
        self.registry = SkillRegistry.instance()

    def test_xhs_note_creator_trigger_words_match(self):
        """xhs_note_creator 的触发词应匹配典型用户输入。"""
        skill_cls = self.registry.get("produce", "xhs_note_creator")
        triggers = skill_cls.trigger_words

        test_inputs = [
            "帮我写小红书笔记",
            "出一套卡片",
            "小红书图文",
            "种草笔记",
            "写笔记",
        ]
        for inp in test_inputs:
            matched = any(t in inp for t in triggers)
            assert matched, f"用户输入 '{inp}' 未匹配任何触发词"

    def test_card_xiaohongshu_trigger_words_match(self):
        """card_xiaohongshu 的触发词应匹配典型用户输入。"""
        skill_cls = self.registry.get("produce", "card_xiaohongshu")
        triggers = skill_cls.trigger_words

        test_inputs = [
            "做小红书卡片",
            "知识卡",
            "渲染卡片",
            "竖版卡片",
            "3:4卡片",
        ]
        for inp in test_inputs:
            matched = any(t in inp for t in triggers)
            assert matched, f"用户输入 '{inp}' 未匹配任何触发词"