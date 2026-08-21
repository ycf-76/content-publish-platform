"""聚焦测试：PAUSED 状态流转 + 计数器增减。

验证：
1. _pause_workflow: DB 置 PAUSED + 递减计数器
2. _unpause_workflow: DB 置 RUNNING + 递增计数器
3. cancel from PAUSED: 不重复递减计数器
4. cancel from RUNNING: 正常递减计数器
5. terminate from PAUSED: 不重复递减计数器
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import WorkflowStatus
from app.services.workflow import WorkflowService


def _make_svc():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    return WorkflowService(db=db), db


def test_pause_sets_db_and_decrements():
    svc, db = _make_svc()

    async def run():
        with patch.object(svc.__class__, "_decrement_workflow_count", new_callable=AsyncMock) as mock_dec:
            await svc._pause_workflow("wf_123")
            mock_dec.assert_called_once()
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    asyncio.run(run())


def test_unpause_sets_db_and_increments():
    svc, db = _make_svc()

    async def run():
        with patch.object(svc.__class__, "_increment_workflow_count", new_callable=AsyncMock) as mock_inc:
            await svc._unpause_workflow("wf_123")
            mock_inc.assert_called_once()
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    asyncio.run(run())


def test_cancel_from_paused_does_not_decrement():
    svc, db = _make_svc()
    workflow = MagicMock()
    workflow.status = WorkflowStatus.PAUSED
    workflow.id = "wf_123"
    svc.get_workflow = AsyncMock(return_value=workflow)

    async def run():
        with patch.object(svc.__class__, "_decrement_workflow_count", new_callable=AsyncMock) as mock_dec:
            result = await svc.cancel_workflow("wf_123", "user_1")
            assert result["success"] is True
            mock_dec.assert_not_called()

    asyncio.run(run())


def test_cancel_from_running_decrements():
    svc, db = _make_svc()
    workflow = MagicMock()
    workflow.status = WorkflowStatus.RUNNING
    workflow.id = "wf_123"
    svc.get_workflow = AsyncMock(return_value=workflow)

    async def run():
        with patch.object(svc.__class__, "_decrement_workflow_count", new_callable=AsyncMock) as mock_dec:
            result = await svc.cancel_workflow("wf_123", "user_1")
            assert result["success"] is True
            mock_dec.assert_called_once()

    asyncio.run(run())


def test_terminate_from_paused_does_not_decrement():
    svc, db = _make_svc()
    workflow = MagicMock()
    workflow.status = WorkflowStatus.PAUSED
    workflow.id = "wf_123"
    svc.get_workflow = AsyncMock(return_value=workflow)

    async def run():
        with patch.object(svc.__class__, "_decrement_workflow_count", new_callable=AsyncMock) as mock_dec:
            result = await svc.terminate_workflow("wf_123", "user_1")
            assert result["success"] is True
            mock_dec.assert_not_called()

    asyncio.run(run())


def test_terminate_from_running_decrements():
    svc, db = _make_svc()
    workflow = MagicMock()
    workflow.status = WorkflowStatus.RUNNING
    workflow.id = "wf_123"
    svc.get_workflow = AsyncMock(return_value=workflow)

    async def run():
        with patch.object(svc.__class__, "_decrement_workflow_count", new_callable=AsyncMock) as mock_dec:
            result = await svc.terminate_workflow("wf_123", "user_1")
            assert result["success"] is True
            mock_dec.assert_called_once()

    asyncio.run(run())