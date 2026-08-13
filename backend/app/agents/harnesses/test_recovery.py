"""Recovery 最小实现验证脚本。

验证点：
1. RecoveryLoop 已注入到 build_search_harness 和 build_publish_harness
2. Observer 的 log_attempt / log_attempt_failed 等方法可正常调用
3. RecoveryLoop 的 execute_with_recovery 在失败时按策略重试
4. 熔断器在多次失败后开启

运行：cd backend && python -m app.agents.harnesses.test_recovery
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

from app.agents.core.harness.observer.observer import Observer
from app.agents.core.harness.recovery import (
    BackoffPolicy,
    CircuitBreaker,
    RecoveryLoop,
    RetryStrategy,
    BroadenKeywordStrategy,
)
from app.agents.core.schemas import NodeExecutionError, WorkflowContext


def make_context() -> WorkflowContext:
    return WorkflowContext(
        workflow_id="wf_test_recovery",
        node_id="search",
        user_id="u_test",
        account_id="acc_test",
        topic="测试主题",
    )


class FakeAgent:
    """模拟 AgentHarness 的最小接口。"""
    agent_id = "search"


async def test_observer_methods() -> None:
    """测试 1：Observer 的 log_attempt 系列方法可正常调用。"""
    print("\n[测试 1] Observer.log_attempt 系列方法")
    events: list[tuple[str, dict[str, Any]]] = []

    async def _emit(node_id: str, event_type: str, payload: dict[str, Any]) -> None:
        events.append((event_type, payload))

    observer = Observer(emit_callback=_emit)

    await observer.log_attempt("search", 0, "retry", {"keyword": "测试"})
    await observer.log_attempt_failed("search", 0, "retry", "连接超时", "TimeoutError")
    await observer.log_recovery_success("search", 1, "broaden_keyword")
    await observer.log_recovery_exhausted("search", 2, "全部策略失败")
    await observer.log_circuit_open("search", "open")

    assert len(events) == 5, f"期望 5 个事件，实际 {len(events)}"
    assert events[0][0] == "recovery_attempt"
    assert events[1][0] == "recovery_attempt_failed"
    assert events[2][0] == "recovery_success"
    assert events[3][0] == "recovery_exhausted"
    assert events[4][0] == "circuit_open"
    assert events[0][1]["strategy"] == "retry"
    assert events[1][1]["error"] == "连接超时"
    print("  ✅ 5 个方法全部正常，事件字段正确")


async def test_recovery_loop_success_on_retry() -> None:
    """测试 2：第一次失败，第二次重试成功。"""
    print("\n[测试 2] RecoveryLoop 重试成功")
    events: list[str] = []

    async def _emit(node_id: str, event_type: str, payload: dict[str, Any]) -> None:
        events.append(event_type)

    observer = Observer(emit_callback=_emit)
    loop = RecoveryLoop(
        max_attempts=2,
        strategies=[RetryStrategy(), RetryStrategy()],
        backoff=BackoffPolicy(base_delay=0.01, max_delay=0.01),
        observer=observer,
    )

    call_count = 0

    async def execute_fn(inp: dict[str, Any], ctx: WorkflowContext) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("模拟第一次失败")
        return {"result": "成功"}

    ctx = make_context()
    result = await loop.execute_with_recovery(FakeAgent(), {"keyword": "测试"}, ctx, execute_fn)

    assert result == {"result": "成功"}, f"期望成功，实际 {result}"
    assert call_count == 2, f"期望调用 2 次，实际 {call_count}"
    assert "recovery_attempt" in events
    assert "recovery_success" in events
    print(f"  ✅ 第一次失败后第二次重试成功，事件序列: {events}")


async def test_recovery_loop_exhausted() -> None:
    """测试 3：所有策略都失败，抛出 RecoveryExhaustedError。"""
    print("\n[测试 3] RecoveryLoop 策略耗尽")
    from app.agents.core.schemas import RecoveryExhaustedError

    events: list[str] = []

    async def _emit(node_id: str, event_type: str, payload: dict[str, Any]) -> None:
        events.append(event_type)

    observer = Observer(emit_callback=_emit)
    loop = RecoveryLoop(
        max_attempts=2,
        strategies=[RetryStrategy(), BroadenKeywordStrategy()],
        backoff=BackoffPolicy(base_delay=0.01, max_delay=0.01),
        observer=observer,
    )

    async def execute_fn(inp: dict[str, Any], ctx: WorkflowContext) -> dict[str, Any]:
        raise RuntimeError("持续失败")

    ctx = make_context()
    raised = False
    try:
        await loop.execute_with_recovery(FakeAgent(), {"keyword": "测试"}, ctx, execute_fn)
    except RecoveryExhaustedError as e:
        raised = True
        assert e.attempts == 2
        assert "持续失败" in e.last_error

    assert raised, "期望抛出 RecoveryExhaustedError"
    assert events.count("recovery_attempt") == 2
    assert events.count("recovery_attempt_failed") == 2
    assert "recovery_exhausted" in events
    print(f"  ✅ 2 次策略都失败后抛出 RecoveryExhaustedError，事件序列: {events}")


async def test_circuit_breaker_opens() -> None:
    """测试 4：熔断器在 5 次失败后开启。"""
    print("\n[测试 4] 熔断器开启")

    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)

    # 前 5 次失败
    for i in range(5):
        assert cb.allow_request("search"), f"第 {i+1} 次应该放行"
        cb.record_failure("search")

    from app.agents.core.harness.recovery import CircuitOpenError

    # 第 6 次应该被熔断
    assert not cb.allow_request("search"), "第 6 次应该被熔断拒绝"
    state = cb.get_state("search")
    assert state.value == "open", f"期望 open，实际 {state.value}"
    print(f"  ✅ 5 次失败后熔断器状态: {state.value}")


async def test_factory_injection() -> None:
    """测试 5：factory.build_search_harness 注入了 recovery_loop。"""
    print("\n[测试 5] factory 注入 recovery_loop")
    from app.agents.harnesses.factory import build_search_harness, build_publish_harness

    search_harness = build_search_harness("wf_test")
    assert search_harness.recovery_loop is not None, "search harness 的 recovery_loop 不应为 None"
    assert search_harness.recovery_loop.max_attempts == 2
    assert len(search_harness.recovery_loop.strategies) == 2
    assert search_harness.recovery_loop.strategies[0].name == "retry"
    assert search_harness.recovery_loop.strategies[1].name == "broaden_keyword"
    print(f"  ✅ search harness 注入成功: max_attempts=2, strategies=[retry, broaden_keyword]")

    publish_harness = build_publish_harness("wf_test")
    assert publish_harness.recovery_loop is not None
    assert publish_harness.recovery_loop.strategies[1].name == "refresh_token"
    print(f"  ✅ publish harness 注入成功: strategies=[retry, refresh_token]")


async def test_broaden_keyword_strategy() -> None:
    """测试 6：BroadenKeywordStrategy 能简化关键词。"""
    print("\n[测试 6] BroadenKeywordStrategy 策略")
    strategy = BroadenKeywordStrategy()
    ctx = make_context()

    # 去掉"类"后缀
    inp1, _ = strategy.adjust({"keyword": "科技类"}, ctx, None)
    assert inp1["keyword"] == "科技", f"期望 '科技'，实际 '{inp1['keyword']}'"

    # 去掉引号
    inp2, _ = strategy.adjust({"keyword": "\"夏日穿搭\""}, ctx, None)
    assert inp2["keyword"] == "夏日穿搭", f"期望 '夏日穿搭'，实际 '{inp2['keyword']}'"

    # 无后缀无引号保持原样
    inp3, _ = strategy.adjust({"keyword": "美食"}, ctx, None)
    assert inp3["keyword"] == "美食"
    print("  ✅ 关键词简化逻辑正确：'科技类'→'科技'，'\"夏日穿搭\"'→'夏日穿搭'")


async def main() -> None:
    print("=" * 60)
    print("Recovery 最小实现验证")
    print("=" * 60)

    try:
        await test_observer_methods()
        await test_recovery_loop_success_on_retry()
        await test_recovery_loop_exhausted()
        await test_circuit_breaker_opens()
        await test_factory_injection()
        await test_broaden_keyword_strategy()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过")
        print("=" * 60)
        print("\n修复总结：")
        print("1. Observer 补全了 log_attempt/log_attempt_failed/log_recovery_success")
        print("   /log_recovery_exhausted/log_circuit_open 5 个专用方法")
        print("2. RecoveryLoop._emit 改用 Observer 专用方法（替代通用 emit_trace）")
        print("3. factory.py 新增 _make_recovery_loop + _make_search_recovery + _make_publish_recovery")
        print("4. build_search_harness 注入 recovery_loop（retry → broaden_keyword）")
        print("5. build_publish_harness 注入 recovery_loop（retry → refresh_token）")
        print("6. 前端 workflow.ts 处理 5 种 recovery 事件 + 更新 levelMap")
        return 0
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 运行出错: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
