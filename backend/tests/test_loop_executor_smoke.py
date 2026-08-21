import asyncio

from app.agents.core.harness.executor.loop import LoopExecutor
from app.agents.core.harness.runtime import AgentHarness
from app.agents.core.schemas import WorkflowContext
from app.agents.skills.base import Skill


class _ScriptedLLM:
    """按顺序返回脚本化响应，验证 ReAct 循环：先调工具，再 final。"""

    model_name = "mock-loop"

    def __init__(self, responses):
        self._responses = list(responses)
        self._index = 0

    async def chat(self, messages, response_format=None):
        idx = min(self._index, len(self._responses) - 1)
        self._index += 1
        return {
            "content": self._responses[idx],
            "reasoning_content": None,
            "token_usage": 1,
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
            '{"thought": "先搜索", "tool_calls": [{"name": "mock_search", "arguments": {"keyword": "AI"}}], "final": false}',
            '{"thought": "完成", "final": true, "output": {"result": "done"}}',
        ])
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_MockSearchSkill()],
            executor=LoopExecutor(max_iterations=3),
        )
        output = await harness.run({"topic": "AI 教育"}, _context())
        return output

    output = asyncio.run(run())
    assert output.output["result"] == "done"
    assert output.output["_iterations"] == 2
    assert output.token_usage == 2


def test_loop_executor_hits_max_iterations_and_falls_back():
    async def run():
        # 永远不返回 final，验证 max_iterations 兜底
        llm = _ScriptedLLM([
            '{"thought": "继续", "tool_calls": [{"name": "mock_search", "arguments": {}}], "final": false}',
        ])
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_MockSearchSkill()],
            executor=LoopExecutor(max_iterations=2),
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
            '{"thought": "call", "tool_calls": [{"name": "recorder", "arguments": {}}], "final": false}',
            '{"thought": "done", "final": true, "output": {"result": "ok"}}',
        ])
        harness = AgentHarness(
            agent_id="test",
            role="tester",
            llm=llm,
            skills=[_LlmRecordingSkill()],
            executor=LoopExecutor(max_iterations=2),
        )
        await harness.run({"topic": "AI"}, _context())

    asyncio.run(run())
    assert injected_llm.get("llm") is not None
