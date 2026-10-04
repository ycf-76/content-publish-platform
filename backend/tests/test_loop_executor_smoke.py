import asyncio
import json

import pytest

from app.engine.harness.executor import loop as loop_module
from app.engine.harness.executor.loop import LoopExecutor
from app.engine.harness.runtime import AgentHarness
from app.engine.schemas import NodeExecutionError, WorkflowContext
from app.engine.governance.request_queue import LLMRequestQueue
from app.tools.base import Skill
from app.engine.schemas import Permission


class _ScriptedLLM:
    """按顺序返回脚本化流式响应，模拟 OpenAI function calling。"""

    model_name = "mock-loop"

    def __init__(self, responses):
        self._responses = list(responses)
        self._index = 0

    async def stream_chat(self, messages, tools=None, response_format=None):
        idx = min(self._index, len(self._responses) - 1)
        self._index += 1
        response = self._responses[idx]
        for chunk in response["chunks"]:
            yield chunk

    async def chat(self, messages, response_format=None):
        """非流式兜底，把脚本响应压缩成一次普通回复。"""
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


class _MockSearchSkill(Skill):
    node_type = "test"
    name = "mock_search"

    async def execute(self, inputs):
        return {"found": True, "keyword": inputs.get("keyword", "")}


def _context() -> WorkflowContext:
    return WorkflowContext(
        workflow_id="wf",
        node_id="test",
        user_id="user",
        account_id="account",
    )


def test_loop_executor_runs_react_loop():
    async def run():
        llm = _ScriptedLLM([
            {
                "chunks": [
                    {
                        "content": "先搜索",
                        "reasoning_content": "",
                        "is_final": True,
                        "token_usage": 1,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "mock_search",
                                    "arguments": '{"keyword": "AI"}',
                                }
                            }
                        ],
                    }
                ]
            },
            {
                "chunks": [
                    {
                        "content": "搜索完成",
                        "reasoning_content": "",
                        "is_final": True,
                        "token_usage": 1,
                        "tool_calls": [],
                    }
                ]
            },
        ])
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_MockSearchSkill()],
            executor=LoopExecutor(max_iterations=3),
            llm_queue=LLMRequestQueue(),
        )
        output = await harness.run({"topic": "AI 教育"}, _context())
        return output

    output = asyncio.run(run())
    assert output.output["summary"] == "搜索完成"
    assert output.output["_iterations"] == 2
    assert output.token_usage == 2


def test_loop_executor_hits_max_iterations_and_falls_back():
    async def run():
        # 永远不返回 final，验证 max_iterations 兜底
        llm = _ScriptedLLM([
            {
                "chunks": [
                    {
                        "content": "继续搜索",
                        "reasoning_content": "",
                        "is_final": True,
                        "token_usage": 1,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "mock_search",
                                    "arguments": "{}",
                                }
                            }
                        ],
                    }
                ]
            },
        ])
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_MockSearchSkill()],
            executor=LoopExecutor(max_iterations=2),
            llm_queue=LLMRequestQueue(),
        )
        output = await harness.run({"topic": "AI 教育"}, _context())
        return output

    output = asyncio.run(run())
    assert output.output.get("_loop_truncated") is True


def test_loop_executor_injects_llm_into_skill():
    """验证 LoopExecutor 调用 skill 时注入了 harness.llm（供 copywrite 等 Skill 使用）。"""
    injected_llm = {}

    class _LlmRecordingSkill(Skill):
        node_type = "test"
        name = "recorder"

        async def execute(self, inputs):
            injected_llm["llm"] = inputs.get("llm")
            return {"recorded": True}

    async def run():
        llm = _ScriptedLLM([
            {
                "chunks": [
                    {
                        "content": "记录",
                        "reasoning_content": "",
                        "is_final": True,
                        "token_usage": 1,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "recorder",
                                    "arguments": "{}",
                                }
                            }
                        ],
                    }
                ]
            },
            {
                "chunks": [
                    {
                        "content": "已记录",
                        "reasoning_content": "",
                        "is_final": True,
                        "token_usage": 1,
                        "tool_calls": [],
                    }
                ]
            },
        ])
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_LlmRecordingSkill()],
            executor=LoopExecutor(max_iterations=2),
            llm_queue=LLMRequestQueue(),
        )
        await harness.run({"topic": "AI"}, _context())

    asyncio.run(run())
    assert injected_llm.get("llm") is not None


def test_loop_executor_retries_plan_text_instead_of_returning_it():
    """回归：用户要求重新写时，模型第一轮只输出计划文本，不能当成最终回复。"""

    class _MockBlCaptainSkill(Skill):
        node_type = "test"
        name = "lively_girl"

        async def execute(self, inputs):
            return {"status": "ok", "title": "test", "content": "test", "tags": []}

    async def run():
        llm = _ScriptedLLM([
            {
                "chunks": [
                    {
                        "content": (
                            "我来基于这篇梨形穿搭文案，亲笔写这份视觉组图的 brief。"
                            "核心分析：这是身材痛点共鸣。正在渲染你的视觉组图……"
                            "让我用完整 brief 驱动风格引擎。"
                        ),
                        "reasoning_content": "",
                        "is_final": True,
                        "token_usage": 1,
                        "tool_calls": [],
                    }
                ]
            },
            {
                "chunks": [
                    {
                        "content": "",
                        "reasoning_content": "",
                        "is_final": True,
                        "token_usage": 1,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "lively_girl",
                                    "arguments": (
                                        '{"title": "梨形穿搭", "content": "上短下长显瘦", '
                                        '"tags": ["穿搭"], "theme": "sp-hearth-table"}'
                                    ),
                                }
                            }
                        ],
                    }
                ]
            },
            {
                "chunks": [
                    {
                        "content": "已为你重新生成梨形穿搭视觉组图。",
                        "reasoning_content": "",
                        "is_final": True,
                        "token_usage": 1,
                        "tool_calls": [],
                    }
                ]
            },
        ])
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_MockBlCaptainSkill()],
            executor=LoopExecutor(max_iterations=4),
            llm_queue=LLMRequestQueue(),
        )
        topic = (
            "之前的对话：\n用户：请基于分析内容生成梨形穿搭视觉组图\n"
            "助手：已生成视觉组图\n\n"
            "最新消息：重新基于你分析完的内容来重新写"
        )
        output = await harness.run({"topic": topic}, _context())
        return output

    output = asyncio.run(run())
    final_text = output.output.get("summary", "")
    assert final_text == "已为你重新生成梨形穿搭视觉组图。"
    assert "我来基于" not in final_text
    assert "核心分析" not in final_text
    assert "正在渲染" not in final_text
    assert output.output.get("_loop_truncated") is not True


class _NeverFinalLLM:
    """每轮都要求调工具、永不 final 的 LLM。"""

    model_name = "mock-never-final"

    def __init__(self):
        self.calls = 0

    async def stream_chat(self, messages, tools=None, response_format=None):
        self.calls += 1
        yield {
            "content": "继续",
            "reasoning_content": "",
            "is_final": True,
            "token_usage": 1,
            "tool_calls": [
                {
                    "function": {
                        "name": "mock_search",
                        "arguments": "{}",
                    }
                }
            ],
        }

    async def chat(self, messages, response_format=None):
        return {
            "content": "继续",
            "reasoning_content": None,
            "token_usage": 1,
            "tool_calls": [
                {"function": {"name": "mock_search", "arguments": "{}"}}
            ],
        }


class _HangingLLM:
    """每次调用都挂起的 LLM，用于验证 LLM 调用超时。"""

    model_name = "mock-hanging"

    async def stream_chat(self, messages, tools=None, response_format=None):
        await asyncio.sleep(5)
        yield {"content": "never", "reasoning_content": "", "is_final": True, "token_usage": 1}

    async def chat(self, messages, response_format=None):
        await asyncio.sleep(5)
        return {"content": "never", "token_usage": 1}


def test_loop_executor_total_timeout_stops_loop():
    """P0-b 回归：整体时间预算超限后立即停止并返回友好 summary。"""
    llm = _NeverFinalLLM()

    async def run():
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_MockSearchSkill()],
            # total_timeout=-1 → deadline 必在过去，第一轮迭代开头即超时
            executor=LoopExecutor(max_iterations=5, total_timeout=-1),
            llm_queue=LLMRequestQueue(),
        )
        return await harness.run({"topic": "AI 教育"}, _context())

    output = asyncio.run(run())
    assert output.output.get("_loop_truncated") is True
    assert "时间预算" in output.output.get("summary", "")
    # 超时发生在第一轮 LLM 调用之前
    assert llm.calls == 0


def test_loop_executor_llm_call_timeout_raises(monkeypatch):
    """P0-b 回归：单次 LLM 调用挂死时超时上抛，且错误信息非空。

    超时语义已改为空闲超时（有 chunk 就续期，长回复不再被拦腰截断），
    挂死的 LLM 表现为「始终无 chunk」，由 _STREAM_IDLE_TIMEOUT 看护。
    """
    monkeypatch.setattr(loop_module, "_STREAM_IDLE_TIMEOUT", 0.2)
    monkeypatch.setattr(loop_module, "_LLM_CALL_TIMEOUT", 0.2)

    async def run():
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=_HangingLLM(),
            skills=[_MockSearchSkill()],
            executor=LoopExecutor(max_iterations=3),
            llm_queue=LLMRequestQueue(),
        )
        return await harness.run({"topic": "AI 教育"}, _context())

    # AgentHarness.run 会把内部异常统一包装为 NodeExecutionError
    with pytest.raises(NodeExecutionError) as exc_info:
        asyncio.run(run())
    # str(TimeoutError()) 本为空串，修复后必须携带可定位信息
    assert "timed out" in str(exc_info.value)


def test_loop_executor_max_iter_error_not_leaked():
    """P0-b 回归：max_iterations 兜底时工具错误信息不泄漏到最终输出。"""

    class _FailingSkill(Skill):
        node_type = "test"
        name = "mock_search"

        async def execute(self, inputs):
            return {"error": "NotImplementedError: boom", "detail": "secret-stderr"}

    async def run():
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=_NeverFinalLLM(),
            skills=[_FailingSkill()],
            executor=LoopExecutor(max_iterations=2),
            llm_queue=LLMRequestQueue(),
        )
        return await harness.run({"topic": "AI 教育"}, _context())

    output = asyncio.run(run())
    assert output.output.get("_loop_truncated") is True
    summary = output.output.get("summary", "")
    assert "NotImplementedError" not in summary
    assert "secret-stderr" not in summary
    assert summary  # 必须有友好文案而非空


def _tool_call_response():
    return {
        "chunks": [
            {
                "content": "调工具",
                "reasoning_content": "",
                "is_final": True,
                "token_usage": 1,
                "tool_calls": [
                    {"function": {"name": "mock_search", "arguments": "{}"}}
                ],
            }
        ]
    }


def test_tool_consecutive_failure_circuit_breaker(caplog):
    """P1-a/P1-b 回归：
    1. 工具抛空消息异常时，错误信息必须带异常类型名（NotImplementedError 而非空串）
    2. 同一工具连续失败 3 次后，第 4 次调用被直接拦截（skill 不再执行）
    3. 熔断后 LLM 仍能正常走 final，循环不卡死
    """

    class _CrashingSkill(Skill):
        node_type = "test"
        name = "mock_search"

        def __init__(self):
            self.calls = 0

        async def execute(self, inputs):
            self.calls += 1
            raise NotImplementedError()  # 空消息异常，复现线上场景

    skill = _CrashingSkill()
    # LLM 脚本：连续 4 轮要求调同一工具，第 5 轮 final
    llm = _ScriptedLLM([
        _tool_call_response(),
        _tool_call_response(),
        _tool_call_response(),
        _tool_call_response(),
        {
            "chunks": [
                {
                    "content": "基于已有信息总结。",
                    "reasoning_content": "",
                    "is_final": True,
                    "token_usage": 1,
                    "tool_calls": [],
                }
            ]
        },
    ])
    executor = LoopExecutor(max_iterations=6)

    async def run():
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[skill],
            executor=executor,
            llm_queue=LLMRequestQueue(),
        )
        return await harness.run({"topic": "AI 教育"}, _context())

    import logging as _logging
    with caplog.at_level(_logging.WARNING, logger="app.engine.harness.executor.loop"):
        output = asyncio.run(run())

    # P1-b: 前 3 次真实执行并失败，第 4 次被拦截（skill 只执行 3 次）
    assert skill.calls == 3
    assert executor._tool_fail_counts.get("mock_search") == 3
    # P1-b: 拦截后循环仍能正常 final
    assert output.output.get("summary") == "基于已有信息总结。"
    # P1-a: 日志中的工具失败信息必须含异常类型名（str(NotImplementedError()) 为空串）
    fail_logs = [r.message for r in caplog.records if "failed" in r.message]
    assert fail_logs, "应记录工具失败日志"
    assert any("NotImplementedError" in m for m in fail_logs), (
        f"日志须含异常类型名，实际: {fail_logs[:2]}"
    )


def test_copy_request_gating_for_yiqi_phrasing():
    """P2 回归："出一期/一篇"类文案请求必须命中文案工具门控，
    防止 LLM 在无门控约束下误调视觉渲染工具。"""
    # 线上真实案例：用户只要文案，旧逻辑完全无门控
    req = "基于这篇文案帮我出一期穿搭文案"
    assert LoopExecutor._is_action_intent_text(req) is True
    tools = LoopExecutor._required_tools_for_request(req, req)
    assert tools == {"lively_girl", "elegant", "professional"}

    # 同类表述
    for phrase in ("出一篇笔记", "来一期干货", "来一篇种草文"):
        assert LoopExecutor._required_tools_for_request(phrase, phrase) == {
            "lively_girl", "elegant", "professional"
        }, f"'{phrase}' 应命中文案工具门控"

    # 分析类请求不受影响
    analysis_req = "帮我分析一下这篇文案"
    assert LoopExecutor._required_tools_for_request(analysis_req, analysis_req) == set()


class _CapturingLLM(_ScriptedLLM):
    """记录每次收到的 messages，用于验证回喂内容。"""

    def __init__(self, responses):
        super().__init__(responses)
        self.seen_messages = []

    async def stream_chat(self, messages, tools=None, response_format=None):
        self.seen_messages.append([dict(m) for m in messages])
        async for chunk in super().stream_chat(messages, tools=tools, response_format=response_format):
            yield chunk


def test_sanitize_error_observation_unit():
    """P3-a 单元：错误 observation 脱敏规则。"""
    s = LoopExecutor._sanitize_error_observation

    # 1. 内部细节字段被剔除，业务错误信息保留
    raw = json.dumps({
        "error": "build blocked: 01-cover need a hero image",
        "cmd": "node D:\\secret\\path\\build.mjs build",
        "stdout": "secret-stdout-content",
        "stderr": "secret-stderr-content",
        "returncode": 1,
    }, ensure_ascii=False)
    out = s(raw)
    assert "secret" not in out
    assert "returncode" not in out
    assert "need a hero image" in out

    # 2. 业务 hint 保留（引导 LLM 下一步的关键信息）
    raw2 = json.dumps({"error": "missing brief", "hint": "请先调用文案工具"}, ensure_ascii=False)
    out2 = s(raw2)
    assert "missing brief" in out2
    assert "请先调用文案工具" in out2

    # 3. 成功 observation 原样返回（不误伤正常结果）
    ok = json.dumps({"status": "ok", "pages": [{"name": "cover"}]}, ensure_ascii=False)
    assert s(ok) == ok

    # 4. 非 JSON 字符串原样返回
    assert s("plain text") == "plain text"

    # 5. 超长 error 截断
    long_err = json.dumps({"error": "x" * 1000}, ensure_ascii=False)
    out5 = s(long_err)
    assert len(json.loads(out5)["error"]) < 400


def test_error_details_not_fed_to_llm():
    """P3-a 集成：工具错误的内部细节（cmd/stdout）不进入 LLM 上下文。"""

    class _LeakyErrorSkill(Skill):
        node_type = "test"
        name = "mock_search"

        async def execute(self, inputs):
            return {
                "error": "render failed: something broke",
                "cmd": "node D:\\secret\\path\\cli.mjs build",
                "stdout": "secret-stdout",
                "returncode": 1,
            }

    llm = _CapturingLLM([
        _tool_call_response(),
        {
            "chunks": [
                {
                    "content": "渲染失败，我直接给文字版。",
                    "reasoning_content": "",
                    "is_final": True,
                    "token_usage": 1,
                    "tool_calls": [],
                }
            ]
        },
    ])

    async def run():
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_LeakyErrorSkill()],
            executor=LoopExecutor(max_iterations=3),
            llm_queue=LLMRequestQueue(),
        )
        return await harness.run({"topic": "AI 教育"}, _context())

    asyncio.run(run())
    # 第二轮 LLM 调用能看到第一轮的 observation
    assert len(llm.seen_messages) == 2
    observations = [
        m["content"] for m in llm.seen_messages[1]
        if m.get("role") == "user" and str(m.get("content", "")).startswith("[observation]")
    ]
    assert observations, "应存在 observation 消息"
    obs_text = observations[-1]
    assert "secret" not in obs_text, f"内部细节泄漏进 LLM 上下文: {obs_text}"
    assert "returncode" not in obs_text
    assert "render failed" in obs_text  # 业务错误信息保留