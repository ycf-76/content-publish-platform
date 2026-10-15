"""Workflow service stub.

DAG 工作流已完整迁移至 workflow-engine 独立项目。
本 stub 保证原项目（ReAct 主流程）所有 import 不报错，
调用时返回安全空值 / None，不阻塞服务启动。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_MIGRATED_MSG = "DAG workflow migrated to workflow-engine project"


class _StubWorkflow:
    def __init__(self, **kwargs: Any) -> None:
        self.id = ""
        self.status = "stub"
        for k, v in kwargs.items():
            setattr(self, k, v)


class WorkflowService:
    def __init__(self, db: AsyncSession | None = None) -> None:
        self._db = db

    async def start_workflow(self, **kwargs: Any) -> _StubWorkflow:
        logger.warning(f"[workflow stub] start_workflow called → stub ({_MIGRATED_MSG})")
        raise NotImplementedError(_MIGRATED_MSG)

    async def get_workflow(self, workflow_id: str, user_id: str) -> dict[str, Any] | None:
        logger.debug(f"[workflow stub] get_workflow({workflow_id}) → None")
        return None

    async def submit_review(self, **kwargs: Any) -> dict[str, Any]:
        logger.debug(f"[workflow stub] submit_review → not-implemented")
        return {"success": False, "message": _MIGRATED_MSG}

    async def inject_card_images(self, **kwargs: Any) -> dict[str, Any]:
        return {"success": False, "message": _MIGRATED_MSG}

    async def _get_graph_for_workflow(self, wf: Any = None) -> tuple[None, None]:
        logger.debug(f"[workflow stub] _get_graph_for_workflow → (None, None)")
        return (None, None)


def get_workflow_service(db: AsyncSession) -> WorkflowService:
    return WorkflowService(db)