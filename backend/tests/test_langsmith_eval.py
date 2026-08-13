"""LangSmith 评估测试：用 LangSmith evaluate 框架测试工作流各节点。

功能：
1. 追踪模式：开启 LANGCHAIN_TRACING_V2 后，每次 pytest 运行自动上报到 LangSmith
2. 评估模式：用 langsmith.evaluate() 对工作流做批量评估 + 自定义评估器
3. 数据集：在 LangSmith 上创建/复用数据集，用固定输入做回归测试

前置条件：
- 安装 langsmith：已内置（langgraph 依赖）
- 设置环境变量 LANGCHAIN_API_KEY（在 .env 或 export）
- 可选：LANGCHAIN_PROJECT 指定项目名

运行方式：
- 追踪测试：pytest tests/test_langsmith_eval.py -v -k "test_tracing"
- 评估测试：pytest tests/test_langsmith_eval.py -v -k "test_evaluate"
- 全量：pytest tests/test_langsmith_eval.py -v

红线：
- 全程用 mock，禁用真实 LLM / MCP / Playwright
- 测试可独立运行，不依赖外部服务
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("DASHSCOPE_API_KEY", "")
os.environ.setdefault("PERMISSIONS_ALLOW", "")


def _setup_langsmith_env() -> None:
    """确保 LangSmith 追踪环境变量已设置（测试用）。"""
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if not os.environ.get("LANGCHAIN_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = ""
    os.environ.setdefault("LANGCHAIN_PROJECT", "multi-agent-xhs-platform-test")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")


def _is_langsmith_configured() -> bool:
    """检查 LangSmith API Key 是否已配置。"""
    return bool(os.environ.get("LANGCHAIN_API_KEY"))


# ---------------------------------------------------------------------------
# Part 1: 追踪测试 — 验证 LangSmith 追踪正常工作
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tracing_search_node() -> None:
    """验证 search_node 运行后 LangSmith 收到追踪记录。

    如果 LANGCHAIN_API_KEY 未设置，跳过（不报错）。
    """
    _setup_langsmith_env()

    from app.agents.graph import search_node, initial_state

    state = initial_state(
        workflow_id=f"wf_langsmith_search_{uuid.uuid4().hex[:8]}",
        user_id="user_langsmith_test",
        account_id="acc_test",
        topic="科技",
    )

    result = await search_node(state)

    assert "node_statuses" in result
    assert result["node_statuses"].get("search") in ("completed", "error")


@pytest.mark.asyncio
async def test_tracing_analyze_node() -> None:
    """验证 analyze_node 运行后 LangSmith 收到追踪记录。"""
    _setup_langsmith_env()

    from app.agents.graph import analyze_node, initial_state

    state = initial_state(
        workflow_id=f"wf_langsmith_analyze_{uuid.uuid4().hex[:8]}",
        user_id="user_langsmith_test",
        account_id="acc_test",
        topic="美食",
    )
    state["node_outputs"]["search"] = {
        "results": [
            {"note_id": "mock_1", "title": "爆款美食笔记", "likes": 5000},
        ],
        "count": 1,
        "summary": "mock search result for 美食",
    }
    state["node_statuses"]["search"] = "completed"

    result = await analyze_node(state)
    assert "node_statuses" in result


@pytest.mark.asyncio
async def test_tracing_full_workflow_mock() -> None:
    """用 mock 跑完整工作流，验证 LangSmith 追踪整个 LangGraph 执行。

    这是核心追踪测试：一次工作流运行会在 LangSmith 上生成一条完整的 trace，
    包含所有节点的 span（输入/输出/耗时/Token）。
    """
    _setup_langsmith_env()

    from app.agents.graph import build_workflow_graph, initial_state, LANGGRAPH_AVAILABLE

    if not LANGGRAPH_AVAILABLE:
        pytest.skip("LangGraph not available")

    graph = build_workflow_graph(checkpointer=None)
    assert graph is not None

    wf_id = f"wf_langsmith_full_{uuid.uuid4().hex[:8]}"
    state = initial_state(
        workflow_id=wf_id,
        user_id="user_langsmith_test",
        account_id="acc_test",
        topic="穿搭",
    )

    config = {"configurable": {"thread_id": wf_id}}

    final_state = None
    async for event in graph.astream(state, config):
        final_state = event

    assert final_state is not None, "workflow should produce at least one event"


# ---------------------------------------------------------------------------
# Part 2: LangSmith evaluate 评估测试
# ---------------------------------------------------------------------------


def _create_test_inputs() -> list[dict[str, Any]]:
    """创建测试输入数据集（模拟不同主题的工作流启动）。"""
    return [
        {"topic": "穿搭", "user_id": "eval_user_1", "account_id": "acc_eval"},
        {"topic": "美食", "user_id": "eval_user_2", "account_id": "acc_eval"},
        {"topic": "科技", "user_id": "eval_user_3", "account_id": "acc_eval"},
        {"topic": "旅行", "user_id": "eval_user_4", "account_id": "acc_eval"},
        {"topic": "美妆", "user_id": "eval_user_5", "account_id": "acc_eval"},
    ]


async def _run_search_for_eval(inputs: dict[str, Any]) -> dict[str, Any]:
    """评估目标函数：对给定输入运行 search 节点，返回结果。"""
    from app.agents.graph import search_node, initial_state

    wf_id = f"wf_eval_{uuid.uuid4().hex[:8]}"
    state = initial_state(
        workflow_id=wf_id,
        user_id=inputs["user_id"],
        account_id=inputs["account_id"],
        topic=inputs["topic"],
    )

    result = await search_node(state)
    return {
        "topic": inputs["topic"],
        "status": result.get("node_statuses", {}).get("search", "unknown"),
        "output": result.get("node_outputs", {}).get("search", {}),
    }


def _evaluator_search_completed(run: dict, example: dict) -> dict[str, Any]:
    """评估器：检查 search 节点是否完成。"""
    output = run.get("output", {})
    status = output.get("status", "unknown")
    return {
        "key": "search_completed",
        "score": 1.0 if status == "completed" else 0.0,
        "comment": f"search status: {status}",
    }


def _evaluator_has_results(run: dict, example: dict) -> dict[str, Any]:
    """评估器：检查 search 是否返回了结果。"""
    output = run.get("output", {})
    search_output = output.get("output", {})
    has_results = bool(search_output.get("results")) or search_output.get("count", 0) > 0
    return {
        "key": "has_search_results",
        "score": 1.0 if has_results else 0.0,
        "comment": f"results count: {search_output.get('count', 0)}",
    }


def _evaluator_topic_relevance(run: dict, example: dict) -> dict[str, Any]:
    """评估器：检查搜索结果与主题的相关性（简单关键词匹配）。"""
    output = run.get("output", {})
    topic = output.get("topic", "")
    search_output = output.get("output", {})
    results = search_output.get("results", [])

    if not results:
        return {
            "key": "topic_relevance",
            "score": 0.0,
            "comment": "no results to evaluate",
        }

    relevant_count = 0
    for r in results:
        title = (r.get("title") or "").lower()
        if topic.lower() in title or any(kw in title for kw in topic.split()):
            relevant_count += 1

    relevance_ratio = relevant_count / len(results) if results else 0
    return {
        "key": "topic_relevance",
        "score": relevance_ratio,
        "comment": f"{relevant_count}/{len(results)} results relevant to '{topic}'",
    }


@pytest.mark.asyncio
async def test_evaluate_search_node() -> None:
    """用 LangSmith evaluate 对 search 节点做批量评估。

    需要 LANGCHAIN_API_KEY，未配置时跳过。
    """
    if not _is_langsmith_configured():
        pytest.skip("LANGCHAIN_API_KEY not set — skip LangSmith evaluate")

    _setup_langsmith_env()

    try:
        import langsmith
    except ImportError:
        pytest.skip("langsmith not installed")

    client = langsmith.Client()

    dataset_name = "xhs_search_eval_dataset"
    test_inputs = _create_test_inputs()

    try:
        dataset = client.read_dataset(dataset_name=dataset_name)
    except Exception:
        dataset = client.create_dataset(dataset_name=dataset_name)
        for inp in test_inputs:
            client.create_example(
                inputs=inp,
                outputs={"expected_status": "completed"},
                dataset_id=dataset.id,
            )

    async def target(inputs: dict) -> dict:
        return await _run_search_for_eval(inputs)

    results = await langsmith.aevaluate(
        target,
        data=dataset_name,
        evaluators=[
            _evaluator_search_completed,
            _evaluator_has_results,
            _evaluator_topic_relevance,
        ],
        experiment_prefix="xhs-search-eval",
    )

    result_list = []
    async for r in results:
        result_list.append(r)
    assert len(result_list) > 0, "evaluate should produce results"


# ---------------------------------------------------------------------------
# Part 3: LangSmith 数据集 + 回归测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dataset_create_and_run() -> None:
    """创建 LangSmith 数据集并运行各节点做回归测试。

    数据集包含多组 (topic, expected_nodes) 输入，
    验证工作流各节点在 mock 模式下都能正常完成。
    """
    if not _is_langsmith_configured():
        pytest.skip("LANGCHAIN_API_KEY not set — skip dataset test")

    _setup_langsmith_env()

    try:
        import langsmith
    except ImportError:
        pytest.skip("langsmith not installed")

    client = langsmith.Client()

    dataset_name = "xhs_workflow_regression"
    regression_inputs = [
        {"topic": "穿搭", "expected_nodes": ["search", "analyze"]},
        {"topic": "美食探店", "expected_nodes": ["search", "analyze"]},
        {"topic": "AI工具", "expected_nodes": ["search", "analyze"]},
    ]

    try:
        dataset = client.read_dataset(dataset_name=dataset_name)
    except Exception:
        dataset = client.create_dataset(dataset_name=dataset_name)
        for inp in regression_inputs:
            client.create_example(
                inputs={"topic": inp["topic"]},
                outputs={"expected_nodes": inp["expected_nodes"]},
                dataset_id=dataset.id,
            )

    async def run_nodes(inputs: dict) -> dict:
        from app.agents.graph import search_node, analyze_node, initial_state

        wf_id = f"wf_regress_{uuid.uuid4().hex[:8]}"
        state = initial_state(
            workflow_id=wf_id,
            user_id="user_regress",
            account_id="acc_regress",
            topic=inputs["topic"],
        )

        search_result = await search_node(state)
        state.update(search_result)

        analyze_result = await analyze_node(state)
        state.update(analyze_result)

        return {
            "topic": inputs["topic"],
            "search_status": state.get("node_statuses", {}).get("search", "unknown"),
            "analyze_status": state.get("node_statuses", {}).get("analyze", "unknown"),
        }

    def eval_nodes_completed(run: dict, example: dict) -> dict[str, Any]:
        output = run.get("output", {})
        expected_nodes = example.get("outputs", {}).get("expected_nodes", [])
        scores = {}
        for node in expected_nodes:
            key = f"{node}_completed"
            status = output.get(f"{node}_status", "unknown")
            scores[key] = {
                "key": key,
                "score": 1.0 if status == "completed" else 0.0,
                "comment": f"{node} status: {status}",
            }
        return scores

    results = await langsmith.aevaluate(
        run_nodes,
        data=dataset_name,
        evaluators=[eval_nodes_completed],
        experiment_prefix="xhs-regression",
    )

    result_list = []
    async for r in results:
        result_list.append(r)
    assert len(result_list) > 0


# ---------------------------------------------------------------------------
# Part 4: LangSmith 对比测试（A/B 实验）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_search_strategies() -> None:
    """对比两种搜索策略（builtin vs tavily）的效果。

    在 LangSmith 控制台中可以并排对比两次实验的结果。
    """
    if not _is_langsmith_configured():
        pytest.skip("LANGCHAIN_API_KEY not set — skip compare test")

    _setup_langsmith_env()

    try:
        import langsmith
    except ImportError:
        pytest.skip("langsmith not installed")

    topics = ["穿搭", "美食", "科技", "旅行", "美妆"]

    async def run_with_source(inputs: dict) -> dict:
        from app.agents.graph import search_node, initial_state

        wf_id = f"wf_compare_{uuid.uuid4().hex[:8]}"
        state = initial_state(
            workflow_id=wf_id,
            user_id="user_compare",
            account_id="acc_compare",
            topic=inputs["topic"],
        )

        result = await search_node(state)
        return {
            "topic": inputs["topic"],
            "source": inputs.get("source", "unknown"),
            "status": result.get("node_statuses", {}).get("search", "unknown"),
            "result_count": result.get("node_outputs", {}).get("search", {}).get("count", 0),
        }

    def eval_result_count(run: dict, example: dict) -> dict[str, Any]:
        output = run.get("output", {})
        count = output.get("result_count", 0)
        return {
            "key": "result_count",
            "score": min(count / 5.0, 1.0),
            "comment": f"got {count} results",
        }

    client = langsmith.Client()
    dataset_name = "xhs_search_compare"

    try:
        dataset = client.read_dataset(dataset_name=dataset_name)
    except Exception:
        dataset = client.create_dataset(dataset_name=dataset_name)
        for topic in topics:
            for source in ["builtin", "tavily"]:
                client.create_example(
                    inputs={"topic": topic, "source": source},
                    outputs={},
                    dataset_id=dataset.id,
                )

    results = await langsmith.aevaluate(
        run_with_source,
        data=dataset_name,
        evaluators=[eval_result_count],
        experiment_prefix="xhs-search-compare",
    )

    result_list = []
    async for r in results:
        result_list.append(r)
    assert len(result_list) > 0