"""Agent 管理 API：运行时注册 / 查询 / 修改 / 删除。

P0: Agent 运行时注册（不重启后端即可创建新 Agent）
P1: LLM 运行时切换（修改 Agent 的 LLM 模型）
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.registry import AgentDef, get_agent_registry
from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.tools.registry import ensure_builtin_skills_registered

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentCreateRequest(BaseModel):
    agent_id: str = Field(description="Agent 唯一标识，如 'my_expert'")
    role: str = Field(default="", description="角色描述，如 '美食分析专家'")
    llm_model: str = Field(default="deepseek-v3", description="LLM 模型，如 deepseek-v3 / deepseek-r1")
    skills: list[str] = Field(default_factory=list, description="技能名称列表，如 ['trending_search', 'viral_analysis']")
    executor: str = Field(default="loop", description="执行器类型：loop 或 single_shot")
    max_iterations: int = Field(default=5, description="最大迭代次数（loop 执行器生效）")
    prompt_template: str = Field(default="", description="系统提示词模板，支持 {topic} 占位符")
    hard_rules: list[str] = Field(default_factory=list, description="硬性规则列表")
    recovery: dict[str, Any] = Field(default_factory=dict, description="恢复策略配置")


class AgentUpdateRequest(BaseModel):
    role: str | None = None
    llm_model: str | None = None
    skills: list[str] | None = None
    executor: str | None = None
    max_iterations: int | None = None
    prompt_template: str | None = None
    hard_rules: list[str] | None = None
    recovery: dict[str, Any] | None = None


class AgentLlmSwitchRequest(BaseModel):
    llm_model: str = Field(description="目标 LLM 模型，如 deepseek-v3 / deepseek-r1 / mock-test")


class AgentSummary(BaseModel):
    agent_id: str
    role: str
    llm_model: str | None
    skills: list[str]
    executor: str
    max_iterations: int
    prompt_template: str
    is_builtin: bool


@router.get("")
async def list_agents(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list[AgentSummary]]:
    """列出所有已注册的 Agent（内置 + 运行时注册）。"""
    ensure_builtin_skills_registered()
    registry = get_agent_registry()
    agents = registry.list_agents()
    from app.agents.registry import BUILTIN_AGENTS
    builtin_ids = set(BUILTIN_AGENTS.keys())
    result = []
    for a in agents:
        result.append(AgentSummary(
            agent_id=a.agent_id,
            role=a.role,
            llm_model=a.llm_model,
            skills=a.skills or [],
            executor=a.executor,
            max_iterations=a.max_iterations,
            prompt_template=a.prompt_template[:200] + "..." if len(a.prompt_template) > 200 else a.prompt_template,
            is_builtin=(a.agent_id in builtin_ids),
        ))
    return StandardResponse(data=result)


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[AgentSummary]:
    """查询单个 Agent 详情。"""
    ensure_builtin_skills_registered()
    registry = get_agent_registry()
    a = registry.get(agent_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")
    return StandardResponse(data=AgentSummary(
        agent_id=a.agent_id,
        role=a.role,
        llm_model=a.llm_model,
        skills=a.skills or [],
        executor=a.executor,
        max_iterations=a.max_iterations,
        prompt_template=a.prompt_template,
        is_builtin=True,
    ))


@router.post("", status_code=201)
async def create_agent(
    req: AgentCreateRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[AgentSummary]:
    """运行时注册新 Agent（不重启后端）。

    agent_id 不可与已有 Agent 重复。
    skills 中的名称必须在 SkillRegistry 中存在（不存在的会被忽略并警告）。
    """
    ensure_builtin_skills_registered()
    registry = get_agent_registry()

    if registry.get(req.agent_id) is not None:
        raise HTTPException(status_code=409, detail=f"Agent '{req.agent_id}' 已存在")

    agent_def = AgentDef(
        agent_id=req.agent_id,
        role=req.role,
        llm_model=req.llm_model,
        skills=req.skills,
        executor=req.executor,
        max_iterations=req.max_iterations,
        prompt_template=req.prompt_template,
        hard_rules=req.hard_rules,
        recovery=req.recovery,
    )
    registry.register(agent_def)
    logger.info(f"[agents-api] registered agent: {req.agent_id}")

    return StandardResponse(
        data=AgentSummary(
            agent_id=agent_def.agent_id,
            role=agent_def.role,
            llm_model=agent_def.llm_model,
            skills=agent_def.skills or [],
            executor=agent_def.executor,
            max_iterations=agent_def.max_iterations,
            prompt_template=agent_def.prompt_template,
            is_builtin=False,
        ),
        message=f"Agent '{req.agent_id}' 注册成功",
    )


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    req: AgentUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[AgentSummary]:
    """修改 Agent 配置（部分更新）。

    内置 Agent 也可以修改（修改后当前进程生效，重启后恢复默认）。
    """
    ensure_builtin_skills_registered()
    registry = get_agent_registry()
    existing = registry.get(agent_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

    updated = existing.model_copy(update={
        k: v for k, v in req.model_dump().items() if v is not None
    })
    registry.register(updated)
    logger.info(f"[agents-api] updated agent: {agent_id}")

    return StandardResponse(
        data=AgentSummary(
            agent_id=updated.agent_id,
            role=updated.role,
            llm_model=updated.llm_model,
            skills=updated.skills,
            executor=updated.executor,
            max_iterations=updated.max_iterations,
            prompt_template=updated.prompt_template,
            is_builtin=False,
        ),
        message=f"Agent '{agent_id}' 更新成功",
    )


@router.patch("/{agent_id}/llm")
async def switch_agent_llm(
    agent_id: str,
    req: AgentLlmSwitchRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[AgentSummary]:
    """P1: 运行时切换 Agent 的 LLM 模型。

    切换后，下次 build_harness 时使用新模型。
    已在运行的 Harness 不受影响（因为 LLM 在 build 时绑定）。
    """
    ensure_builtin_skills_registered()
    registry = get_agent_registry()
    existing = registry.get(agent_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

    updated = existing.model_copy(update={"llm_model": req.llm_model})
    registry.register(updated)
    logger.info(f"[agents-api] switched LLM for agent {agent_id}: {req.llm_model}")

    return StandardResponse(
        data=AgentSummary(
            agent_id=updated.agent_id,
            role=updated.role,
            llm_model=updated.llm_model,
            skills=updated.skills,
            executor=updated.executor,
            max_iterations=updated.max_iterations,
            prompt_template=updated.prompt_template,
            is_builtin=False,
        ),
        message=f"Agent '{agent_id}' LLM 已切换为 {req.llm_model}",
    )


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[str]:
    """删除运行时注册的 Agent。

    内置 Agent（BUILTIN_AGENTS 中的）不可删除。
    """
    ensure_builtin_skills_registered()
    registry = get_agent_registry()

    from app.agents.registry import BUILTIN_AGENTS
    if agent_id in BUILTIN_AGENTS:
        raise HTTPException(status_code=403, detail=f"内置 Agent '{agent_id}' 不可删除")

    if registry.get(agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")

    registry.unregister(agent_id)
    logger.info(f"[agents-api] deleted agent: {agent_id}")

    return StandardResponse(data=agent_id, message=f"Agent '{agent_id}' 已删除")