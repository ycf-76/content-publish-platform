"""Chat 链路画像注入测试（D18）。

覆盖两层注入：
1. LLM 层（A4）：ChatAgent.process 读画像 → input_data["profile_prompt"]
   → LoopExecutor messages 里有画像 system 消息（自由回复也带调性）
2. Skill 层（B1）：LoopExecutor._dispatch_tool 把 user_profile 塞进
   execute_params（文案/审核等 skill 消费）

软注入语义：无画像/读失败 → 静默跳过，chat 不被拦截。
"""

import asyncio

import pytest

from app.engine.harness.executor.loop import LoopExecutor
from app.engine.harness.runtime import AgentHarness
from app.engine.schemas import AgentOutput, WorkflowContext
from app.engine.governance.request_queue import LLMRequestQueue
from app.tools.base import Skill


# ============================================================================
# 公共 mock 基建（与 test_loop_executor_smoke 同款风格）
# ============================================================================


class _ScriptedLLM:
    """按顺序返回脚本化流式响应。"""

    model_name = "mock-profile"

    def __init__(self, responses):
        self._responses = list(responses)
        self._index = 0
        self.seen_messages = []

    async def stream_chat(self, messages, tools=None, response_format=None):
        self.seen_messages.append([dict(m) for m in messages])
        idx = min(self._index, len(self._responses) - 1)
        self._index += 1
        response = self._responses[idx]
        for chunk in response["chunks"]:
            yield chunk

    async def chat(self, messages, response_format=None):
        idx = min(self._index, len(self._responses) - 1)
        self._index += 1
        response = self._responses[idx]
        content_parts = []
        tool_calls = []
        token_usage = 0
        for chunk in response["chunks"]:
            if chunk.get("content"):
                content_parts.append(chunk["content"])
            if chunk.get("tool_calls"):
                tool_calls.extend(chunk["tool_calls"])
            if chunk.get("is_final"):
                token_usage = chunk.get("token_usage", 0) or token_usage
        return {
            "content": "".join(content_parts),
            "reasoning_content": None,
            "token_usage": token_usage or 1,
            "tool_calls": tool_calls,
        }


class _ProfileRecordingSkill(Skill):
    """记录收到的 execute_params，用于验证 user_profile 注入。"""

    node_type = "test"
    name = "profile_recorder"

    def __init__(self):
        self.seen_inputs: list[dict] = []

    async def execute(self, inputs):
        self.seen_inputs.append(dict(inputs))
        return {"recorded": True}


def _final_response(text: str):
    return {
        "chunks": [
            {
                "content": text,
                "reasoning_content": "",
                "is_final": True,
                "token_usage": 1,
                "tool_calls": [],
            }
        ]
    }


def _tool_call_response():
    return {
        "chunks": [
            {
                "content": "调工具",
                "reasoning_content": "",
                "is_final": True,
                "token_usage": 1,
                "tool_calls": [
                    {
                        "function": {
                            "name": "profile_recorder",
                            "arguments": "{}",
                        }
                    }
                ],
            }
        ]
    }


def _context(user_id: str = "user_1") -> WorkflowContext:
    return WorkflowContext(
        workflow_id="wf_chat",
        node_id="chat",
        user_id=user_id,
        account_id="",
    )


def _harness(llm, skills, max_iterations=4) -> AgentHarness:
    return AgentHarness(
        agent_id="chat_agent",
        role="tester",
        llm=llm,
        skills=skills,
        executor=LoopExecutor(max_iterations=max_iterations),
        llm_queue=LLMRequestQueue(),
    )


_FAKE_PROFILE_DICT = {
    "primary_domain": "tech",
    "sub_domain": "AI 工具",
    "tone": "professional",
    "visual_style": "warm",
    "taboo_topics": ["政治"],
    "taboo_words": ["绝绝子"],
}


# ============================================================================
# Skill 层（B1）：execute_params 注入 user_profile
# ============================================================================


def test_skill_receives_user_profile_via_soft_inject(monkeypatch):
    """有画像时，工具调用参数里带 user_profile（DB 唯一事实来源，LLM 传什么都不算）。"""
    from app.services import profile_service as ps_mod
    from app.tools.context_vars import current_db_session

    class _FakeProfile:
        def model_dump(self, mode="json"):
            return dict(_FAKE_PROFILE_DICT)

    async def _fake_cached(db, user_id):
        return _FakeProfile()

    monkeypatch.setattr(ps_mod, "get_profile_cached", _fake_cached)

    skill = _ProfileRecordingSkill()
    llm = _ScriptedLLM([_tool_call_response(), _final_response("完成")])
    harness = _harness(llm, [skill])

    class _FakeDB:
        pass

    token = current_db_session.set(_FakeDB())
    try:
        output = asyncio.run(harness.run({"topic": "写一篇文案"}, _context()))
    finally:
        current_db_session.reset(token)

    assert output.output.get("summary") == "完成"
    assert skill.seen_inputs, "skill 应被调用"
    injected = [i for i in skill.seen_inputs if "user_profile" in i]
    assert injected, "execute_params 应包含 user_profile"
    assert injected[0]["user_profile"]["primary_domain"] == "tech"
    assert injected[0]["user_profile"]["taboo_words"] == ["绝绝子"]


def test_skill_no_profile_no_inject_and_no_error(monkeypatch):
    """无画像：参数里没有 user_profile，chat 正常完成（软注入不拦）。"""
    from app.services import profile_service as ps_mod
    from app.tools.context_vars import current_db_session

    async def _fake_cached(db, user_id):
        return None

    monkeypatch.setattr(ps_mod, "get_profile_cached", _fake_cached)

    skill = _ProfileRecordingSkill()
    llm = _ScriptedLLM([_tool_call_response(), _final_response("完成")])
    harness = _harness(llm, [skill])

    class _FakeDB:
        pass

    token = current_db_session.set(_FakeDB())
    try:
        output = asyncio.run(harness.run({"topic": "写一篇文案"}, _context()))
    finally:
        current_db_session.reset(token)

    assert output.output.get("summary") == "完成"
    assert all("user_profile" not in i for i in skill.seen_inputs)


def test_skill_profile_read_failure_degrades_silently(monkeypatch):
    """画像读取抛异常：静默降级，chat 不挂。"""
    from app.services import profile_service as ps_mod
    from app.tools.context_vars import current_db_session

    async def _fake_cached(db, user_id):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(ps_mod, "get_profile_cached", _fake_cached)

    skill = _ProfileRecordingSkill()
    llm = _ScriptedLLM([_tool_call_response(), _final_response("完成")])
    harness = _harness(llm, [skill])

    token = current_db_session.set(object())
    try:
        output = asyncio.run(harness.run({"topic": "写一篇文案"}, _context()))
    finally:
        current_db_session.reset(token)

    assert output.output.get("summary") == "完成"
    assert all("user_profile" not in i for i in skill.seen_inputs)


# ============================================================================
# LLM 层（A4）：profile_prompt 进入 messages
# ============================================================================


def test_profile_prompt_in_llm_messages(monkeypatch):
    """input 带 profile_prompt → LLM 收到画像 system 消息。"""
    profile_prompt = "[创作者画像 — 你作为该创作者 AI 搭档的身份与约束]\n主领域: tech"
    skill = _ProfileRecordingSkill()
    llm = _ScriptedLLM([_final_response("好的")])
    harness = _harness(llm, [skill])

    asyncio.run(
        harness.run(
            {"topic": "你好", "profile_prompt": profile_prompt}, _context()
        )
    )

    assert llm.seen_messages, "LLM 应被调用"
    system_msgs = [
        m["content"] for m in llm.seen_messages[0] if m.get("role") == "system"
    ]
    assert any("创作者画像" in c for c in system_msgs), (
        f"messages 应包含画像 system 消息: {system_msgs}"
    )


def test_no_profile_prompt_no_extra_system_message(monkeypatch):
    """无 profile_prompt → messages 不多出画像消息（token 不白花）。"""
    skill = _ProfileRecordingSkill()
    llm = _ScriptedLLM([_final_response("好的")])
    harness = _harness(llm, [skill])

    asyncio.run(harness.run({"topic": "你好"}, _context()))

    system_msgs = [
        m["content"] for m in llm.seen_messages[0] if m.get("role") == "system"
    ]
    assert all("创作者画像" not in c for c in system_msgs)


# ============================================================================
# ChatAgent 层：process → _agentic_loop 注入 input_data["profile_prompt"]
# ============================================================================


class _FakeHarness:
    """记录 run() 收到的 input；输出固定 final。"""

    agent_id = "chat_agent"

    def __init__(self):
        self.seen_input = None
        self.llm = object()  # truthy：让 ChatAgent 走 _agentic_loop

    async def run(self, input_data, context):
        self.seen_input = dict(input_data)
        return AgentOutput(
            output={"summary": "完成"},
            token_usage=1,
        )

    async def shutdown(self):
        pass


class _FakeRegistry:
    def build_harness(self, agent_id, workflow_id=None):
        return _FakeRegistry.last_harness

    last_harness = None


def _run_chat_agent(profile_or_none, message="写一篇文案"):
    from app.agents.chat_agent import ChatAgent

    harness = _FakeHarness()
    _FakeRegistry.last_harness = harness
    agent = ChatAgent(registry=_FakeRegistry())

    async def run():
        return await agent.process(
            message=message,
            session_id="sess_1",
            user_id="user_1",
            account_id="",
            db=object(),  # db truthy 才会走画像读取分支
            workflow_id="wf_chat",
        )

    return asyncio.run(run()), harness


def test_chat_agent_injects_profile_prompt(monkeypatch):
    """ChatAgent.process：画像存在 → input_data['profile_prompt'] 带完整画像文本。"""
    from app.services import profile_service as ps_mod

    async def _fake_cached(db, user_id):
        from app.api.schemas.profile import UserProfile

        return UserProfile.model_validate(_FAKE_PROFILE_DICT)

    monkeypatch.setattr(ps_mod, "get_profile_cached", _fake_cached)

    result, harness = _run_chat_agent("ignored")
    assert result.status == "agent_output"
    prompt = harness.seen_input.get("profile_prompt", "")
    assert "创作者画像" in prompt
    assert "科技" in prompt  # to_prompt_context 输出中文标签
    assert "AI 工具" in prompt
    assert "绝绝子" in prompt  # 禁忌词必须在 LLM 可见约束里


def test_chat_agent_no_profile_no_prompt(monkeypatch):
    """ChatAgent.process：无画像 → 不注入 profile_prompt，正常返回。"""
    from app.services import profile_service as ps_mod

    async def _fake_cached(db, user_id):
        return None

    monkeypatch.setattr(ps_mod, "get_profile_cached", _fake_cached)

    result, harness = _run_chat_agent("ignored")
    assert result.status == "agent_output"
    assert "profile_prompt" not in (harness.seen_input or {})


def test_chat_agent_profile_read_error_no_crash(monkeypatch):
    """ChatAgent.process：画像读取异常 → 软降级，chat 不挂。"""
    from app.services import profile_service as ps_mod

    async def _fake_cached(db, user_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(ps_mod, "get_profile_cached", _fake_cached)

    result, harness = _run_chat_agent("ignored")
    assert result.status == "agent_output"
    assert "profile_prompt" not in (harness.seen_input or {})


# ============================================================================
# 缓存语义：TTL 内复用、upsert 后失效
# ============================================================================


@pytest.mark.asyncio
async def test_profile_cache_hit_and_invalidate():
    """TTL 内第二次读取不打 DB；invalidate 后重新读。"""
    import time as _time

    from app.services import profile_service as ps_mod

    ps_mod._profile_cache.clear()
    calls = {"n": 0}

    class _FakeSvc:
        def __init__(self, db):
            pass

        async def get_profile(self, user_id):
            calls["n"] += 1
            return None

    monkey_db = object()

    orig_svc = ps_mod.ProfileService
    ps_mod.ProfileService = _FakeSvc
    try:
        await ps_mod.get_profile_cached(monkey_db, "u_cache")
        await ps_mod.get_profile_cached(monkey_db, "u_cache")
        assert calls["n"] == 1, "TTL 内应命中缓存，不重复打 DB"

        ps_mod.invalidate_profile_cache("u_cache")
        await ps_mod.get_profile_cached(monkey_db, "u_cache")
        assert calls["n"] == 2, "失效后应重新读 DB"

        # 换 user_id 不共享缓存条目
        await ps_mod.get_profile_cached(monkey_db, "u_other")
        assert calls["n"] == 3
    finally:
        ps_mod.ProfileService = orig_svc
        ps_mod._profile_cache.clear()