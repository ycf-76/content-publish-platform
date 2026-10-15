"""终止信号 / 纯文本直出行为回归（2026-10-09 改造后的行为契约）。

覆盖 4 个场景，全部针对当天改动的核心行为：
  A. 调过工具后输出总结 → 必须直接接受（旧逻辑会因 _PLAN_MARKERS 误杀并崩溃）
  B. 从头到尾不调工具   → 最多 nudge 2 次，之后必须接受（不能死催到跑满轮次）
  C. 从不给 final        → 撞上限后必须给出人话 summary，不能空白
  D. 非 JSON 纯文本      → _parse_step 降级必须留下可观测日志
"""

import asyncio
import json

from app.engine.harness.executor.loop import LoopExecutor
from app.engine.harness.runtime import AgentHarness
from app.engine.schemas import WorkflowContext
from app.engine.governance.request_queue import LLMRequestQueue
from app.tools.base import Skill


class _ScriptedLLM:
    """按顺序返回脚本化流式响应，模拟 OpenAI function calling。"""

    model_name = "mock-loop"

    def __init__(self, responses):
        self._responses = list(responses)
        self._index = 0

    async def stream_chat(self, messages, tools=None, response_format=None):
        idx = min(self._index, len(self._responses) - 1)
        self._index += 1
        for chunk in self._responses[idx]["chunks"]:
            yield chunk

    async def chat(self, messages, response_format=None):
        idx = min(self._index, len(self._responses) - 1)
        self._index += 1
        content_parts = []
        tool_calls = []
        token_usage = 0
        for chunk in self._responses[idx]["chunks"]:
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


def _chunk(content="", tool_calls=None):
    return {
        "content": content,
        "reasoning_content": "",
        "is_final": True,
        "token_usage": 1,
        "tool_calls": tool_calls or [],
    }


def _call(name="mock_search", arguments='{"keyword": "AI"}'):
    return {"function": {"name": name, "arguments": arguments}}


def _run(responses, max_iterations=5, topic="帮我搜索一下AI教育的热点"):
    llm = _ScriptedLLM(responses)
    harness = AgentHarness(
        agent_id="test",
        role="tester",
        llm=llm,
        skills=[_MockSearchSkill()],
        executor=LoopExecutor(max_iterations=max_iterations),
        llm_queue=LLMRequestQueue(),
    )
    return asyncio.run(harness.run({"topic": topic}, _context()))


def test_a_summary_after_tools_is_accepted_not_rejected():
    """A：调过工具后输出总结，必须原样接受。

    旧逻辑会命中 _PLAN_MARKERS（"首先"/"接下来"）把总结判成废话，
    注入 retry 后再调 _detect_required_tools → AttributeError 直接崩。
    """
    out = _run([
        {"chunks": [_chunk("先搜索", [_call()])]},
        {"chunks": [_chunk("任务完成。首先我查了热点，接下来生成了文案。")]},
    ])
    assert out.output["_iterations"] == 2, "第 2 轮就该结束，不该被踹回去"
    assert "首先" in out.output["summary"], (
        f"总结应原样保留，实际: {out.output.get('summary')!r}"
    )
    assert not out.output.get("_loop_truncated")


def test_b_no_tool_ever_nudges_at_most_twice():
    """B：动作意图请求但从头到尾不调工具，最多催 2 次，第 3 轮必须接受输出。

    防止死催：旧逻辑每轮都重试，直到跑满 max_iterations。
    """
    out = _run([
        {"chunks": [_chunk("我来帮你查一下，首先看看数据")]},
    ], max_iterations=8)
    assert out.output["_iterations"] == 3, (
        f"应在第 3 轮接受输出（nudge 上限 2 次），实际: {out.output['_iterations']}"
    )
    assert "我来" in out.output["summary"]


def test_c_no_final_signal_yields_readable_summary():
    """C：模型从不给 final，撞上限后必须给出人话 summary，不能空白。

    同时验证不再崩溃（旧逻辑撞 _detect_required_tools → AttributeError）。
    """
    out = _run([
        {"chunks": [_chunk("继续搜索", [_call()])]},
    ], max_iterations=3)
    assert out.output.get("_loop_truncated") is True
    summary = out.output.get("summary", "")
    assert "任务未跑完" in summary, f"应给出人话说明，实际: {summary!r}"
    assert len(summary) > 10


def test_e_chitchat_is_not_nudged():
    """E：闲聊/纯问答不该被催调工具，模型给了有效回答就直接接受。

    真机实证（batch 任务4）：用户说"你好"，模型回答"你好！我是创作助手"，
    却被强制 nudge 两轮；模型试图发起澄清又撞上未定义的 _serialize_msg；
    最后接受空输出，兜底成一句没意义的"处理完成。"。
    """
    out = _run([
        {"chunks": [_chunk("你好！我是你的内容创作助手。")]},
    ], topic="你好")
    assert out.output["_iterations"] == 1, (
        f"闲聊应第 1 轮直接结束，实际: {out.output['_iterations']}"
    )
    summary = out.output["summary"]
    assert "创作助手" in summary, f"回答应原样保留，实际: {summary!r}"
    assert summary != "处理完成。", "不应兜底成无意义的'处理完成。'"


def test_d_parse_degradation_is_observable(caplog):
    """D：非 JSON 纯文本导致 _parse_step 降级时，必须留下 [loop:signal] 日志。

    这是"终止信号不可靠"的量化入口：以前全程静默，无从统计。
    """
    import logging as _logging

    with caplog.at_level(_logging.WARNING, logger="app.engine.harness.executor.loop"):
        _run([
            {"chunks": [_chunk("先搜索", [_call()])]},
            {"chunks": [_chunk("任务完成，首先查了热点，接下来生成文案")]},
        ])

    degradation = [
        r.message for r in caplog.records
        if "_parse_step L3 degraded" in r.message
    ]
    assert degradation, (
        "应记录 _parse_step 三级降级日志，否则终止信号丢失无从排查"
    )
    assert "[loop:signal]" in degradation[0]
