"""pytest 全局配置：autouse fixture 注入 mock，让测试零 token + 零外部依赖。

红线（来自 project_memory）：
- 全程用 mock，禁用真实 LLM / MCP / Playwright
- 测试可独立运行，不依赖外部服务
- LLM 测试用 mock 模式，不消耗 token

注入的 mock：
1. _MockLLM → 替换 get_deepseek_llm，所有 LLM 调用返回固定 JSON（零 token）
2. MockMCPClient → 替换 mcp_manager，搜索返回固定 mock 笔记（不连小红书）
3. AsyncSessionLocal → 替换 DB session，选题池存储等 DB 操作静默成功（不连 SQLite）
4. sse_bus.publish → 静默吞掉（测试不需要真实 SSE 推送）

LangSmith 追踪照常上报：
- LANGCHAIN_TRACING_V2=true 时，langgraph 的 astream 自动上报 trace
- trace 里的 span 包含 mock 数据，但不影响追踪链路完整性
- 适合验证"工作流结构是否正确"、"节点是否按顺序执行"、"interrupt 是否生效"
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# 测试前置：加载 .env 文件（确保 LangSmith API Key 等配置在 pytest 进程启动时就可用）
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k = _k.strip()
        _v = _v.strip().strip('"').strip("'")
        # 只设置未存在的环境变量（不覆盖 pytest 命令行传入的）
        os.environ.setdefault(_k, _v)

# 测试前置：禁用真实外部依赖的 API Key（覆盖 .env 中的真实 key，确保零 token）
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["DASHSCOPE_API_KEY"] = ""
os.environ["PERMISSIONS_ALLOW"] = ""


@pytest_asyncio.fixture(autouse=True)
async def mock_llm() -> AsyncIterator[None]:
    """注入 mock LLM：所有 get_deepseek_llm 返回 _MockLLM，不连真实 API、不消耗 token。

    覆盖范围：
    - analyze_node 的 LLM 粗分析 + 深度归因
    - copywrite_node 的文案生成
    - quality_check_* 的软语义检查
    - search_node 的关键词翻译 fallback（虽然主流程不走 LLM）
    """
    from app.agents.harnesses.factory import _MockLLM

    mock_llm = _MockLLM(model="mock-chat")
    with patch(
        "app.agents.harnesses.factory.get_deepseek_llm",
        return_value=mock_llm,
    ):
        yield


@pytest_asyncio.fixture(autouse=True)
async def mock_mcp() -> AsyncIterator[None]:
    """注入 mock MCP client：搜索返回固定 mock 笔记，不连真实小红书。

    覆盖范围：
    - search_node 的 TrendingSearchSkill（内部调 mcp_manager）
    - publish_node 的 XhsPublishSkill（内部调 mcp_manager）
    """
    from app.agents.skills.mcp.xhs_client import mcp_manager
    from tests.mocks.mock_mcp import MockMCPClient

    mock_client = MockMCPClient()
    await mock_client.connect()

    # 直接替换 mcp_manager 的内部 client 引用
    mcp_manager._local_client = mock_client
    mcp_manager._plugin_client = None

    yield

    await mock_client.close()
    mcp_manager._local_client = None


@pytest_asyncio.fixture(autouse=True)
async def mock_db() -> AsyncIterator[None]:
    """注入 mock DB session：选题池存储等 DB 操作静默成功，不连真实 SQLite。

    覆盖范围：
    - search_node 的 _save_search_results_to_pool
    - search_node 的 _fetch_other_platforms_to_pool
    - publish_node 的 agent_memory.record_publish
    """
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock(return_value=[])
    mock_session.flush = AsyncMock()

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.db.session.AsyncSessionLocal", mock_session_local):
        yield


@pytest_asyncio.fixture(autouse=True)
async def mock_sse() -> AsyncIterator[None]:
    """静默 SSE 推送：测试不需要真实 SSE 事件分发。

    注意：这不影响 LangSmith 追踪——LangSmith 通过 langgraph 的 callback 机制上报，
    与 sse_bus 无关。
    """
    with patch(
        "app.services.sse_bus.sse_bus.publish",
        new_callable=AsyncMock,
    ):
        yield


@pytest_asyncio.fixture(autouse=True)
async def mock_agent_memory() -> AsyncIterator[None]:
    """静默 agent_memory 的 DB 操作：record_publish 等不连真实 DB。"""
    with patch("app.services.agent_memory.record_publish", new_callable=AsyncMock):
        with patch("app.services.agent_memory.load_for_workflow", new_callable=AsyncMock, return_value={}):
            yield
