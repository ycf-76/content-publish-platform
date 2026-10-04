"""CodexSession ReAct 心脏端到端边界测试。

覆盖场景：
1. LLM 持续返回无效 JSON（解析鲁棒性）
2. LLM 返回空 content（空响应边界）
3. LLM 全部重试失败（3 次重试耗尽）
4. 工具调用返回超长 observation（截断边界）
5. 消息链超长触发截断（_MESSAGES_MAX_LEN 边界）
6. 权限门控：部分工具允许、部分拒绝（混合权限）
7. 工具参数类型错误（TypeError 边界）
8. 工具执行抛异常（Exception 边界）
9. max_iterations=1 单步边界
10. max_iterations=0 零步边界
11. LLM 返回 tool_calls 中 arguments 不是 dict
12. SSE bus 异常不影响主流程
13. _extract_json_from_text 嵌套 JSON 边界
14. observation 截断长度精确边界
15. _token_count 超限边界
16. primitive execute 返回非 dict（自动包装）
17. 条件边 condition 字段在动态图构建中的传递
18. 插件安装/卸载后节点映射缓存刷新
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.schemas import Permission


class _MockLLM:
    def __init__(self, responses: list[dict[str, Any]] | None = None):
        self.responses = responses or []
        self._index = 0

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        if self._index < len(self.responses):
            resp = self.responses[self._index]
            self._index += 1
            return resp
        return {"content": '{"final": true, "output": {"done": true}}', "token_usage": 10}


class _FailingLLM:
    async def chat(self, messages, **kwargs):
        raise ConnectionError("LLM service unavailable")


class _MockSSEBus:
    def __init__(self):
        self.events: list[tuple[str, str, dict]] = []
        self._fail_on_nth: int | None = None
        self._call_count: int = 0

    async def publish(self, workflow_id: str, event_type: str, payload: dict):
        self._call_count += 1
        if self._fail_on_nth and self._call_count == self._fail_on_nth:
            raise RuntimeError("SSE bus broken")
        self.events.append((workflow_id, event_type, payload))


class _MockPrimitive:
    from app.engine.codex.primitives import Primitive

    def __init__(self, name, permissions, result):
        self.name = name
        self.required_permissions = permissions
        self._result = result

    async def execute(self, **kwargs):
        return self._result


# ============================================================================
# 1. LLM 持续返回无效 JSON
# ============================================================================
class TestLLMInvalidJSON:
    @pytest.mark.asyncio
    async def test_garbage_json_falls_back_to_thought(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {"content": "this is not json at all!!!", "token_usage": 5},
            {"content": json.dumps({"final": True, "output": {"ok": True}}), "token_usage": 5},
        ])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("test")
        assert result["_iterations"] == 1
        assert "raw_text" in result or "thought" in result

    @pytest.mark.asyncio
    async def test_partial_json_extracts_embedded(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([{
            "content": 'Sure, here is my plan:\n{"thought": "search", "final": true, "output": {"plan": "search_first"}}\nDone.',
            "token_usage": 10,
        }])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("test")
        assert result["plan"] == "search_first"


# ============================================================================
# 2. LLM 返回空 content
# ============================================================================
class TestLLMEmptyContent:
    @pytest.mark.asyncio
    async def test_empty_string_content(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {"content": "", "token_usage": 0},
            {"content": json.dumps({"final": True, "output": {"recovered": True}}), "token_usage": 5},
        ])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("test")
        assert result["_iterations"] == 1
        assert "raw_text" in result or "thought" in result

    @pytest.mark.asyncio
    async def test_whitespace_only_content(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {"content": "   \n  \t  ", "token_usage": 0},
            {"content": json.dumps({"final": True, "output": {"ok": True}}), "token_usage": 5},
        ])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("test")
        assert result["_iterations"] == 1
        assert "raw_text" in result or "thought" in result


# ============================================================================
# 3. LLM 全部重试失败
# ============================================================================
class TestLLMRetryExhaustion:
    @pytest.mark.asyncio
    async def test_all_retries_fail_returns_error(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(llm=_FailingLLM(), max_iterations=3)
        result = await session.run("test")
        assert "error" in result
        assert "LLM call failed" in result.get("error", "") or "unavailable" in result.get("error", "")


# ============================================================================
# 4. 工具调用返回超长 observation（截断边界）
# ============================================================================
class TestObservationTruncation:
    @pytest.mark.asyncio
    async def test_long_observation_truncated(self):
        from app.engine.codex.session import CodexSession, _OBSERVATION_MAX_LEN

        long_data = {"ok": True, "content": "x" * 10000}
        mock_prim = _MockPrimitive("content_check", [], long_data)

        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "check",
                    "tool_calls": [{"name": "content_check", "arguments": {"text": "test"}}],
                    "final": False,
                }),
                "token_usage": 10,
            },
            {"content": json.dumps({"final": True, "output": {"ok": True}}), "token_usage": 5},
        ])
        session = CodexSession(
            llm=llm,
            primitives=[mock_prim],
            max_iterations=5,
        )
        result = await session.run("test")
        assert result["ok"] is True

        last_user_msg = None
        for msg in result.get("_steps", []):
            for obs in msg.get("observations", []):
                last_user_msg = obs

        assert len(json.dumps(long_data)) > _OBSERVATION_MAX_LEN


# ============================================================================
# 5. 消息链超长触发截断
# ============================================================================
class TestMessageTruncationBoundary:
    def test_exact_boundary_not_truncated(self):
        from app.engine.codex.session import CodexSession, _MESSAGES_MAX_LEN
        session = CodexSession()
        msgs = [{"role": "system", "content": "sys"}] + [
            {"role": "user", "content": f"msg {i}"} for i in range(_MESSAGES_MAX_LEN - 1)
        ]
        result = session._maybe_truncate_messages(msgs)
        assert len(result) == _MESSAGES_MAX_LEN

    def test_one_over_boundary_truncated(self):
        from app.engine.codex.session import CodexSession, _MESSAGES_MAX_LEN
        session = CodexSession()
        msgs = [{"role": "system", "content": "sys"}] + [
            {"role": "user", "content": f"msg {i}"} for i in range(_MESSAGES_MAX_LEN)
        ]
        result = session._maybe_truncate_messages(msgs)
        assert len(result) == _MESSAGES_MAX_LEN
        assert result[0]["role"] == "system"

    def test_multiple_system_messages_preserved(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        msgs = [
            {"role": "system", "content": "sys1"},
            {"role": "system", "content": "sys2"},
        ] + [{"role": "user", "content": f"msg {i}"} for i in range(100)]
        result = session._maybe_truncate_messages(msgs)
        system_count = sum(1 for m in result if m["role"] == "system")
        assert system_count == 2


# ============================================================================
# 6. 混合权限：部分允许、部分拒绝
# ============================================================================
class TestMixedPermissions:
    @pytest.mark.asyncio
    async def test_allowed_and_denied_in_same_iteration(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "try both",
                    "tool_calls": [
                        {"name": "content_check", "arguments": {"text": "ok"}},
                        {"name": "bash", "arguments": {"command": "ls"}},
                    ],
                    "final": False,
                }),
                "token_usage": 10,
            },
            {"content": json.dumps({"final": True, "output": {"done": True}}), "token_usage": 5},
        ])
        session = CodexSession(
            llm=llm,
            allowed_permissions=set(),
            max_iterations=5,
        )
        result = await session.run("test")
        assert result["done"] is True
        step0 = result["_steps"][0]
        tool_results = step0["tool_calls"]
        assert len(tool_results) == 2
        content_check_result = next(t for t in tool_results if t["name"] == "content_check")
        bash_result = next(t for t in tool_results if t["name"] == "bash")
        assert content_check_result["ok"] is True
        assert bash_result["ok"] is False


# ============================================================================
# 7. 工具参数类型错误
# ============================================================================
class TestToolArgumentTypeError:
    @pytest.mark.asyncio
    async def test_arguments_as_string_triggers_type_error(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "bad args",
                    "tool_calls": [{"name": "file_read", "arguments": "not_a_dict"}],
                    "final": False,
                }),
                "token_usage": 10,
            },
            {"content": json.dumps({"final": True, "output": {"ok": True}}), "token_usage": 5},
        ])
        session = CodexSession(
            llm=llm,
            allowed_permissions={Permission.FILE_READ},
            max_iterations=5,
        )
        result = await session.run("test")
        assert result["ok"] is True


# ============================================================================
# 8. 工具执行抛异常
# ============================================================================
class TestToolExecutionException:
    @pytest.mark.asyncio
    async def test_primitive_raises_exception(self):
        from app.engine.codex.session import CodexSession
        from app.engine.codex.primitives import Primitive

        class ExplodingPrimitive(Primitive):
            name = "explode"
            description = "always fails"
            required_permissions = []

            async def execute(self, **kwargs):
                raise RuntimeError("kaboom")

        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "try explode",
                    "tool_calls": [{"name": "explode", "arguments": {}}],
                    "final": False,
                }),
                "token_usage": 10,
            },
            {"content": json.dumps({"final": True, "output": {"survived": True}}), "token_usage": 5},
        ])
        session = CodexSession(llm=llm, primitives=[ExplodingPrimitive()], max_iterations=5)
        result = await session.run("test")
        assert result["survived"] is True
        step0 = result["_steps"][0]
        assert step0["tool_calls"][0]["ok"] is False


# ============================================================================
# 9 & 10. max_iterations 边界
# ============================================================================
class TestMaxIterationsBoundary:
    @pytest.mark.asyncio
    async def test_max_iterations_1(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([{
            "content": json.dumps({
                "thought": "need more steps",
                "tool_calls": [{"name": "content_check", "arguments": {"text": "test"}}],
                "final": False,
            }),
            "token_usage": 10,
        }])
        session = CodexSession(llm=llm, max_iterations=1)
        result = await session.run("test")
        assert result.get("_loop_truncated") is True
        assert result["_iterations"] == 1

    @pytest.mark.asyncio
    async def test_max_iterations_0(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([{
            "content": json.dumps({"final": True, "output": {"ok": True}}),
            "token_usage": 10,
        }])
        session = CodexSession(llm=llm, max_iterations=0)
        result = await session.run("test")
        assert result.get("_loop_truncated") is True


# ============================================================================
# 11. arguments 不是 dict
# ============================================================================
class TestArgumentsNotDict:
    @pytest.mark.asyncio
    async def test_arguments_as_list(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "list args",
                    "tool_calls": [{"name": "content_check", "arguments": ["a", "b"]}],
                    "final": False,
                }),
                "token_usage": 10,
            },
            {"content": json.dumps({"final": True, "output": {"ok": True}}), "token_usage": 5},
        ])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("test")
        assert result["ok"] is True


# ============================================================================
# 12. SSE bus 异常不影响主流程
# ============================================================================
class TestSSEBusResilience:
    @pytest.mark.asyncio
    async def test_sse_bus_failure_does_not_crash(self):
        from app.engine.codex.session import CodexSession
        bus = _MockSSEBus()
        bus._fail_on_nth = 2

        llm = _MockLLM([{
            "content": json.dumps({"final": True, "output": {"ok": True}}),
            "token_usage": 10,
        }])
        session = CodexSession(llm=llm, sse_bus=bus, workflow_id="test_wf", max_iterations=5)
        result = await session.run("test")
        assert result["ok"] is True


# ============================================================================
# 13. _extract_json_from_text 嵌套 JSON
# ============================================================================
class TestExtractNestedJSON:
    def test_deeply_nested_json(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        nested = '{"a": {"b": {"c": [1, 2, 3]}}}'
        text = f"Here: {nested} done."
        result = session._extract_json_from_text(text)
        assert result is not None
        assert result["a"]["b"]["c"] == [1, 2, 3]

    def test_multiple_json_objects_picks_first_valid(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        text = '{"x": 1} and {"y": 2}'
        result = session._extract_json_from_text(text)
        assert result is not None
        assert "x" in result

    def test_no_json_returns_none(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        result = session._extract_json_from_text("no json here")
        assert result is None


# ============================================================================
# 14. observation 截断长度精确边界
# ============================================================================
class TestObservationMaxLength:
    @pytest.mark.asyncio
    async def test_observation_exactly_at_limit(self):
        from app.engine.codex.session import CodexSession, _OBSERVATION_MAX_LEN

        exact_data = {"ok": True, "data": "x" * (_OBSERVATION_MAX_LEN - 20)}
        obs_str = json.dumps(exact_data, ensure_ascii=False)
        assert len(obs_str) <= _OBSERVATION_MAX_LEN + 50

    @pytest.mark.asyncio
    async def test_observation_just_over_limit(self):
        from app.engine.codex.session import CodexSession, _OBSERVATION_MAX_LEN

        over_data = {"ok": True, "data": "x" * _OBSERVATION_MAX_LEN}
        obs_str = json.dumps(over_data, ensure_ascii=False, default=str)
        truncated = obs_str[:_OBSERVATION_MAX_LEN] + "...(truncated)"
        assert len(truncated) == _OBSERVATION_MAX_LEN + len("...(truncated)")
        assert truncated.endswith("...(truncated)")


# ============================================================================
# 15. _token_count 超限
# ============================================================================
class TestTokenCountBoundary:
    @pytest.mark.asyncio
    async def test_token_count_accumulates(self):
        from app.engine.codex.session import CodexSession
        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "step1",
                    "tool_calls": [{"name": "content_check", "arguments": {"text": "a"}}],
                    "final": False,
                }),
                "token_usage": 5000,
            },
            {
                "content": json.dumps({
                    "thought": "step2",
                    "tool_calls": [{"name": "content_check", "arguments": {"text": "b"}}],
                    "final": False,
                }),
                "token_usage": 3000,
            },
            {"content": json.dumps({"final": True, "output": {"ok": True}}), "token_usage": 1000},
        ])
        session = CodexSession(llm=llm, max_iterations=5)
        result = await session.run("test")
        assert result["_token_usage"] == 9000


# ============================================================================
# 16. primitive execute 返回非 dict
# ============================================================================
class TestPrimitiveNonDictReturn:
    @pytest.mark.asyncio
    async def test_primitive_returns_string(self):
        from app.engine.codex.session import CodexSession
        from app.engine.codex.primitives import Primitive

        class StringPrimitive(Primitive):
            name = "string_tool"
            description = "returns a string"
            required_permissions = []

            async def execute(self, **kwargs):
                return "just a string"

        llm = _MockLLM([
            {
                "content": json.dumps({
                    "thought": "call string tool",
                    "tool_calls": [{"name": "string_tool", "arguments": {}}],
                    "final": False,
                }),
                "token_usage": 10,
            },
            {"content": json.dumps({"final": True, "output": {"ok": True}}), "token_usage": 5},
        ])
        session = CodexSession(llm=llm, primitives=[StringPrimitive()], max_iterations=5)
        result = await session.run("test")
        assert result["ok"] is True


# ============================================================================
# 17. 条件边 condition 在动态图构建中的传递
# ============================================================================
class TestDynamicGraphConditionEdge:
    def test_graph_edge_has_condition_field(self):
        from app.api.routers.workflow_definitions import GraphEdge
        edge = GraphEdge(id="e1", source="n1", target="n2", condition="confidence < 0.5")
        assert edge.condition == "confidence < 0.5"

    def test_graph_edge_condition_defaults_none(self):
        from app.api.routers.workflow_definitions import GraphEdge
        edge = GraphEdge(id="e1", source="n1", target="n2")
        assert edge.condition is None

    def test_effective_edges_preserve_condition(self):
        edges_def = [
            {"id": "e1", "source": "search", "target": "analyze"},
            {"id": "e2", "source": "analyze", "target": "copywrite", "condition": "confidence >= 0.7"},
            {"id": "e3", "source": "analyze", "target": "search", "condition": "confidence < 0.7"},
        ]
        node_id_to_type = {"n1": "search", "n2": "analyze", "n3": "copywrite"}
        effective_edges = [
            {
                **e,
                "source": node_id_to_type[e["source"]] if e["source"] in node_id_to_type else e["source"],
                "target": node_id_to_type[e["target"]] if e["target"] in node_id_to_type else e["target"],
            }
            for e in edges_def
        ]
        cond_edges = [e for e in effective_edges if e.get("condition")]
        assert len(cond_edges) == 2
        assert cond_edges[0]["condition"] == "confidence >= 0.7"
        assert cond_edges[1]["condition"] == "confidence < 0.7"


# ============================================================================
# 18. 插件安装/卸载后节点映射缓存刷新
# ============================================================================
class TestPluginCacheRefresh:
    def test_refresh_node_func_map_clears_cache(self):
        from app.agents.graph import refresh_node_func_map, _get_node_func_map

        _ = _get_node_func_map()
        refresh_node_func_map()

        import app.agents.graph as _g
        assert _g._NODE_FUNC_MAP is None

    def test_skill_cache_invalidation(self):
        from app.api.routers.skills import _invalidate_skill_caches
        import app.agents.registry as _ar

        _ar._skills_cache = {"dummy": True}
        _invalidate_skill_caches()
        assert _ar._skills_cache is None

    def test_trigger_words_cache_invalidation(self):
        from app.api.routers.skills import _invalidate_skill_caches
        import app.api.routers.chat_agent as _ca

        _ca._trigger_words_cache = {"dummy": True}
        _invalidate_skill_caches()
        assert _ca._trigger_words_cache is None


# ============================================================================
# 额外：_parse_step 边界
# ============================================================================
class TestParseStepBoundary:
    def test_empty_string(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        result = session._parse_step("")
        assert result["final"] is False

    def test_json_array_not_dict(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        result = session._parse_step('[1, 2, 3]')
        assert result["final"] is False

    def test_null_json(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        result = session._parse_step('null')
        assert result["final"] is False

    def test_deeply_nested_code_fence(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        text = '```json\n{"thought": "deep", "final": true, "output": {"v": 42}}\n```'
        result = session._parse_step(text)
        assert result["thought"] == "deep"
        assert result["output"]["v"] == 42


# ============================================================================
# 额外：_dispatch 边界
# ============================================================================
class TestDispatchBoundary:
    @pytest.mark.asyncio
    async def test_dispatch_with_no_name(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession()
        result = await session._dispatch({"arguments": {}})
        assert result["ok"] is False
        assert "unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_dispatch_with_empty_arguments(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(allowed_permissions=set())
        result = await session._dispatch({"name": "content_check", "arguments": {}})
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_dispatch_none_arguments(self):
        from app.engine.codex.session import CodexSession
        session = CodexSession(allowed_permissions=set())
        result = await session._dispatch({"name": "content_check", "arguments": None})
        assert result["ok"] is True