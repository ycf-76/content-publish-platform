"""Agent 注册表：用 Python 定义内置 Agent，替代损坏的 configs/*.yaml。

设计：
- `AgentDef` 用 Pydantic 定义（类型安全、IDE 可跳转）。
- `BUILTIN_AGENTS` 用 Python dict 定义内置 Agent。
- `configs/*.yaml` 降级为可选覆盖层（Phase 3 再实现）。
- `AgentRegistry.build_harness()` 把 `AgentDef` 装配成 `AgentHarness`。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.engine.harness.executor.loop import LoopExecutor
from app.engine.harness.executor.single_shot import SingleShotExecutor
from app.engine.harness.memory.memory import AgentMemory
from app.engine.harness.observer.observer import Observer
from app.engine.harness.runtime import AgentHarness
from app.tools.registry import get_skill_class_by_name

logger = logging.getLogger(__name__)


class AgentDef(BaseModel):
    """Agent 的声明式定义。"""

    agent_id: str
    role: str = ""
    llm_model: str | None = None
    skills: list[str] = Field(default_factory=list)
    executor: str = "single_shot"
    hard_rules: list[str] = Field(default_factory=list)
    soft_semantic: dict[str, Any] | None = None
    recovery: dict[str, Any] = Field(default_factory=dict)
    prompt_template: str = ""


# 内置 Agent 定义（与 DAG 9 节点对齐；llm_model 使用前端展示名，由 get_deepseek_llm 归一化）
BUILTIN_AGENTS: dict[str, AgentDef] = {
    "search": AgentDef(
        agent_id="search",
        role="爆款搜索专家",
        llm_model="deepseek-v3",
        skills=["trending_search"],
        executor="loop",
        hard_rules=["search_result_non_empty", "rate_limit_check"],
        recovery={
            "max_attempts": 3,
            "strategies": ["retry", "broaden_keyword", "switch_model:deepseek-v3"],
        },
    ),
    "analyze": AgentDef(
        agent_id="analyze",
        role="爆款分析专家",
        llm_model="deepseek-v3",
        skills=["vl_analyze"],
        executor="single_shot",
        soft_semantic={"enabled": True},
        prompt_template=(
            "你是小红书爆款分析专家。\n"
            "请分析主题「{topic}」的爆款规律和选题方向。\n"
            "只输出 JSON，包含 insights（趋势洞察）和 recommendations（选题建议数组）。"
        ),
        recovery={
            "max_attempts": 3,
            "strategies": ["retry", "reduce_input", "switch_model:deepseek-v3"],
        },
    ),
    "copywrite": AgentDef(
        agent_id="copywrite",
        role="小红书文案创作专家",
        llm_model="deepseek-r1",
        executor="single_shot",
        soft_semantic={"enabled": True},
        prompt_template=(
            "你是小红书文案创作专家。\n"
            "请为主题「{topic}」写一篇小红书笔记文案。\n"
            "只输出 JSON，包含 title（标题）、content（正文）、tags（标签数组）。"
        ),
        recovery={
            "max_attempts": 3,
            "strategies": ["retry", "simplify_prompt", "switch_model:deepseek-v3"],
        },
    ),
    "image_plan": AgentDef(
        agent_id="image_plan",
        role="图片规划专家",
        llm_model="deepseek-v3",
        executor="single_shot",
        prompt_template=(
            "你是图片规划专家。\n"
            "请为主题「{topic}」规划小红书卡片配图方案。\n"
            "只输出 JSON，包含 pages（页数组，每页有 type 和 title）。"
        ),
    ),
    "image_gen": AgentDef(
        agent_id="image_gen",
        role="图片生成专家",
        llm_model="deepseek-v3",
        executor="single_shot",
        prompt_template=(
            "你是图片生成专家。\n"
            "请为主题「{topic}」描述需要生成的图片方案。\n"
            "只输出 JSON，包含 images（图片描述数组，每项含 prompt 和 style）。"
        ),
    ),
    "image_review": AgentDef(
        agent_id="image_review",
        role="图片审核专家",
        llm_model="deepseek-v3",
        executor="single_shot",
        prompt_template=(
            "你是图片审核专家。\n"
            "请审核图片方案是否符合小红书规范。\n"
            "只输出 JSON，包含 passed（布尔）和 issues（问题数组）。"
        ),
    ),
    "audit": AgentDef(
        agent_id="audit",
        role="合规审核专家",
        llm_model="deepseek-v3",
        executor="single_shot",
        soft_semantic={"enabled": True},
        prompt_template=(
            "你是小红书合规审核专家。\n"
            "请审核内容是否符合平台规范。\n"
            "只输出 JSON，包含 passed（布尔）和 issues（问题数组）。"
        ),
    ),
    "final_review": AgentDef(
        agent_id="final_review",
        role="终审确认专家",
        llm_model="deepseek-v3",
        executor="single_shot",
        prompt_template=(
            "你是终审确认专家。\n"
            "请确认内容是否可发布。\n"
            "只输出 JSON，包含 review_status（passed 或 rejected）和 feedback。"
        ),
    ),
    "publish": AgentDef(
        agent_id="publish",
        role="发布专家",
        llm_model="deepseek-v3",
        skills=["xhs_publish"],
        executor="loop",
        recovery={"max_attempts": 2, "strategies": ["retry", "refresh_token"]},
    ),
    "explore": AgentDef(
        agent_id="explore",
        role="探索研究专家",
        llm_model="deepseek-r1",
        skills=["trending_search", "vl_analyze", "lively_girl"],
        executor="loop",
    ),
}


def _build_skills(skill_names: list[str]) -> list[Any]:
    """按 skill name 从 SkillRegistry 实例化 Skill。"""
    skills: list[Any] = []
    for name in skill_names:
        skill_cls = get_skill_class_by_name(name)
        if skill_cls is None:
            logger.warning(f"[registry] unknown skill name: {name}")
            continue
        skills.append(skill_cls())
    return skills


class AgentRegistry:
    """Agent 注册表。"""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDef] = dict(BUILTIN_AGENTS)

    def get(self, agent_id: str) -> AgentDef | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentDef]:
        return list(self._agents.values())

    def build_harness(
        self,
        agent_id: str,
        workflow_id: str | None = None,
    ) -> AgentHarness:
        """把 AgentDef 装配成 AgentHarness。

        模型锁定：`agent_def.llm_model` 决定具体模型，harness 的 `llm` 是具体
        BaseLLM，不走 ModelRouter 的 task_type 自动路由。
        """
        agent_def = self._agents[agent_id]

        llm = None
        if agent_def.llm_model:
            # 延迟导入避免与 factory.py 的循环依赖
            from app.engine.factory import get_deepseek_llm

            llm = get_deepseek_llm(model=agent_def.llm_model)

        executor = (
            LoopExecutor(max_iterations=4)
            if agent_def.executor == "loop"
            else SingleShotExecutor()
        )

        # Observer→SSE 桥接：有 workflow_id 时复用 _make_observer，事件走 sse_bus
        observer = Observer()
        if workflow_id:
            from app.engine.factory import _make_observer

            observer = _make_observer(workflow_id)

        # skills 装配；hard_rules / recovery 的装配仍留到后续 Task
        skills = _build_skills(agent_def.skills)
        return AgentHarness(
            agent_id=agent_def.agent_id,
            role=agent_def.role,
            llm=llm,
            skills=skills,
            memory=AgentMemory(),
            prompt_template=agent_def.prompt_template,
            output_schema=None,
            hard_rules=[],
            observer=observer,
            executor=executor,
            recovery_loop=None,
            soft_semantic=agent_def.soft_semantic,
        )


_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 单例。"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
