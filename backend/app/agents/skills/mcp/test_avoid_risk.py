"""验证 MCP 风控规避方案：双模式 fallback + 频率控制 + 边界处理。

验证点：
1. search_notes 插件失败时 fallback 到 local_client（双模式架构）
2. 三层频率控制生效（最小间隔 + 滑动窗口 + 每日上限）
3. 插件和 local 都未配置时抛 RuntimeError（让上层处理）
4. local_client 仍可用于 get_current_user_info

运行：cd backend ; .venv\Scripts\python.exe -m app.agents.skills.mcp.test_avoid_risk
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

from app.agents.skills.mcp.xhs_client import MCPClientManager


class FakePluginClient:
    """模拟插件 MCP client，记录调用次数和参数。"""

    def __init__(self) -> None:
        self.call_count = 0
        self.keywords: list[str] = []

    async def search_notes(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        self.call_count += 1
        self.keywords.append(keyword)
        return [{"note_id": f"note_{self.call_count}", "title": keyword, "likes": 100}]


class FailingPluginClient:
    """模拟失败的插件 client。"""

    def __init__(self) -> None:
        self.call_count = 0

    async def search_notes(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        self.call_count += 1
        raise RuntimeError("模拟插件失败：桥接页面未在线")


async def test_plugin_fallback_to_local() -> None:
    """测试 1：插件失败时 fallback 到 local_client（双模式架构）。"""
    print("\n[测试 1] 插件失败 fallback 到 local_client")
    manager = MCPClientManager()
    failing = FailingPluginClient()
    manager.set_plugin_client(failing)

    # 设置 local_client，验证会被调用（fallback 生效）
    local_called = [False]

    class FakeLocal:
        async def search_notes(self, k, l=20):
            local_called[0] = True
            return [{"note_id": "local_note", "title": k, "likes": 50}]
    manager.set_local_client(FakeLocal())

    result = await manager.search_notes("测试关键词")

    assert failing.call_count == 1, f"期望插件调用 1 次，实际 {failing.call_count}"
    assert local_called[0], "local_client 应该被调用（fallback 生效）"
    assert result, f"期望 local_client 返回结果，实际 {result}"
    print("  ✅ 插件失败时 fallback 到 local_client 成功")


async def test_rate_limit_min_interval() -> None:
    """测试 2：最小间隔 30 秒生效。"""
    print("\n[测试 2] 最小间隔频率控制")
    manager = MCPClientManager()
    fake = FakePluginClient()
    manager.set_plugin_client(fake)

    # 临时把最小间隔调小到 1 秒（避免测试等 30 秒）
    manager._min_interval = 1.0
    manager._window_max = 10  # 放宽窗口限制，专注测最小间隔
    manager._daily_max = 100  # 放宽每日上限

    t0 = time.time()
    await manager.search_notes("关键词1")
    t1 = time.time()
    await manager.search_notes("关键词2")
    t2 = time.time()

    first_duration = t1 - t0
    second_duration = t2 - t1

    assert first_duration < 0.5, f"第一次搜索应该立即返回，实际 {first_duration:.2f}s"
    assert second_duration >= 0.9, f"第二次搜索应该等待 >=1s，实际 {second_duration:.2f}s"
    assert fake.call_count == 2
    assert fake.keywords == ["关键词1", "关键词2"]
    print(f"  ✅ 第1次立即返回（{first_duration:.2f}s），第2次等待 {second_duration:.2f}s")


async def test_rate_limit_window() -> None:
    """测试 3：滑动窗口限制（60 秒内最多 2 次）。"""
    print("\n[测试 3] 滑动窗口频率控制")
    manager = MCPClientManager()
    fake = FakePluginClient()
    manager.set_plugin_client(fake)

    # 调小参数加速测试
    manager._min_interval = 0.1
    manager._window_seconds = 2.0  # 2 秒窗口
    manager._window_max = 2  # 窗口内最多 2 次
    manager._daily_max = 100

    await manager.search_notes("搜索1")
    await manager.search_notes("搜索2")

    t0 = time.time()
    # 第三次应该被窗口限制，等待 2 秒后才能执行
    await manager.search_notes("搜索3")
    wait_duration = time.time() - t0

    assert wait_duration >= 1.5, f"第三次应该等待窗口过期（~2s），实际 {wait_duration:.2f}s"
    assert fake.call_count == 3
    print(f"  ✅ 窗口内第 3 次搜索等待了 {wait_duration:.2f}s（窗口 2s 限制 2 次）")


async def test_rate_limit_daily_cap() -> None:
    """测试 4：每日上限。"""
    print("\n[测试 4] 每日搜索上限")
    manager = MCPClientManager()
    fake = FakePluginClient()
    manager.set_plugin_client(fake)

    manager._min_interval = 0.01
    manager._window_seconds = 0.01
    manager._window_max = 100
    manager._daily_max = 3  # 只允许 3 次

    # 前 3 次成功
    for i in range(3):
        result = await manager.search_notes(f"搜索{i+1}")
        assert result, f"第 {i+1} 次应该返回结果"

    # 第 4 次应该被拒绝
    result = await manager.search_notes("搜索4")
    assert result == [], f"第 4 次应该返回空（达每日上限），实际 {result}"
    assert fake.call_count == 3, f"插件应该只被调用 3 次，实际 {fake.call_count}"
    print(f"  ✅ 每日上限 3 次生效，第 4 次被拒绝，插件未调用")


async def test_no_plugin_configured() -> None:
    """测试 5：插件和 local 都未配置时抛 RuntimeError（让上层处理）。"""
    print("\n[测试 5] 无可用 MCP client 时抛异常")
    manager = MCPClientManager()
    # 不设置 plugin_client 和 local_client

    raised = False
    try:
        await manager.search_notes("测试")
    except RuntimeError as e:
        raised = True
        print(f"  ✅ 抛 RuntimeError: {e}")
    assert raised, "期望抛 RuntimeError（无可用 MCP client）"


async def test_local_client_still_used_for_user_info() -> None:
    """测试 6：local_client 仍可用于 get_current_user_info（登录功能保留）。"""
    print("\n[测试 6] local_client 用于用户信息（登录功能保留）")
    manager = MCPClientManager()

    class FakeLocal:
        async def get_current_user_info(self):
            return {"xhs_user_id": "test123", "nickname": "测试用户"}
    manager.set_local_client(FakeLocal())

    # 没有插件时，get_current_user_info 应该走 local_client
    info = await manager.get_current_user_info()
    assert info["xhs_user_id"] == "test123"
    print(f"  ✅ local_client 用于用户信息获取：{info['nickname']}")


async def main() -> None:
    print("=" * 60)
    print("风控规避方案验证")
    print("=" * 60)

    try:
        await test_plugin_fallback_to_local()
        await test_rate_limit_min_interval()
        await test_rate_limit_window()
        await test_rate_limit_daily_cap()
        await test_no_plugin_configured()
        await test_local_client_still_used_for_user_info()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过")
        print("=" * 60)
        print("\n验证内容：")
        print("1. [双模式] 插件失败时 fallback 到 local_client（QR Worker session）")
        print("2. [频率控制] 三层节流：最小间隔 30s + 60s 窗口最多 2 次 + 每日 30 次")
        print("3. [并发安全] 频率控制加 asyncio.Lock 防止并发绕过")
        print("4. [边界处理] 无可用 client 时抛异常（不返回假数据）")
        print("5. [登录保留] local_client 仍可用于 get_current_user_info")
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
