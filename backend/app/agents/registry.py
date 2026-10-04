"""Agent 注册表：用 Python 定义内置 Agent，替代损坏的 configs/*.yaml。

设计：
- `AgentDef` 用 Pydantic 定义（类型安全、IDE 可跳转）。
- `BUILTIN_AGENTS` 用 Python dict 定义内置 Agent。
- `configs/*.yaml` 降级为可选覆盖层（Phase 3 再实现）。
- `AgentRegistry.build_harness()` 把 `AgentDef` 装配成 `AgentHarness`。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.engine.harness.executor.loop import LoopExecutor
from app.engine.harness.executor.single_shot import SingleShotExecutor
from app.engine.harness.memory.memory import AgentMemory
from app.engine.harness.observer.observer import Observer
from app.engine.harness.runtime import AgentHarness
from app.tools.registry import (
    SkillRegistry,
    ensure_builtin_skills_registered,
    get_skill_class_by_name,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_prompt(name: str) -> str:
    """从 prompts/ 目录加载 prompt 文件。"""
    p = PROMPTS_DIR / f"{name}.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    logger.warning(f"[registry] prompt file not found: {p}")
    return ""


def _load_prompt_stack(*names: str) -> str:
    """按 Prompt Stack 顺序拼接多个 prompt 文件。

    SOUL.md（人格）→ AGENTS.md（分工）→ 其他按需层。
    层之间用双换行分隔。
    """
    parts: list[str] = []
    for name in names:
        content = _load_prompt(name)
        if content:
            parts.append(content.strip())
    return "\n\n".join(parts)


class AgentDef(BaseModel):
    """Agent 的声明式定义。"""

    agent_id: str
    role: str = ""
    description: str = ""
    llm_model: str | None = None
    skills: list[str] | None = Field(default=None)
    disallowed_skills: list[str] = Field(default_factory=list)
    executor: str = "single_shot"
    hard_rules: list[str] = Field(default_factory=list)
    soft_semantic: dict[str, Any] | None = None
    recovery: dict[str, Any] = Field(default_factory=dict)
    max_iterations: int = 4
    prompt_template: str = ""


# 内置 Agent 定义（与 DAG 9 节点对齐；llm_model 使用前端展示名，由 get_deepseek_llm 归一化）
BUILTIN_AGENTS: dict[str, AgentDef] = {
    "search": AgentDef(
        agent_id="search",
        role="爆款搜索专家",
        description="搜索小红书热点、趋势、爆款笔记。当需要搜索、查找、调研信息时主动使用。",
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
        description="分析爆款规律、选题方向、数据趋势。当需要数据分析、趋势洞察、竞品对比时主动使用。",
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
        description="创作小红书笔记文案。当需要写文案、创作内容、生成标题和正文时主动使用。",
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
        description="规划小红书卡片配图方案。当需要图片排版、视觉规划时主动使用。",
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
        description="生成图片方案描述。当需要 AI 生图、图片创作时主动使用。",
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
        description="审核图片方案是否符合小红书规范。当需要图片合规检查时主动使用。",
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
        description="审核内容合规性，提供独立无偏见的审核视角。当需要检查、审核、验证内容时主动使用。",
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
        description="终审确认内容是否可发布。当需要最终发布前确认时主动使用。",
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
        description="发布内容到平台（小红书发布已移除）。",
        llm_model="deepseek-v3",
        skills=[],
        executor="loop",
        recovery={"max_attempts": 2, "strategies": ["retry"]},
    ),
    "explore": AgentDef(
        agent_id="explore",
        role="探索研究专家",
        description="综合搜索+分析+文案的探索研究。当需要深度研究某个主题的全链路时主动使用。",
        llm_model="deepseek-r1",
        skills=["trending_search", "vl_analyze", "lively_girl"],
        executor="loop",
    ),
    "chat_agent": AgentDef(
        agent_id="chat_agent",
        role="小红书运营搭档",
        description="主对话 Agent，协调所有子 Agent 完成用户任务。",
        llm_model="deepseek-v3",
        skills=None,
        executor="loop",
        max_iterations=20,
         prompt_template=_load_prompt_stack("SOUL", "AGENTS"),
        recovery={
            "max_attempts": 3,
            "strategies": ["retry", "simplify_prompt", "switch_model:deepseek-v3"],
        },
    ),
}


_skills_cache: list[Any] | None = None

CREATION_TYPE_SKILLS: dict[str, dict[str, list[str]]] = {
    "image_text": {
        "produce":   ["xhs_note_creator", "copywriting", "social_content",
                      "card_xiaohongshu", "card_quote", "card_design", "infographic",
                      "poster_hero", "comparison_card", "style_transfer"],
        "plan":      ["content_matrix", "topic_evaluator", "hook_generator", "carousel_planner",
                      "voice_builder", "positioning_analysis"],
        "publish":   ["publish_checklist", "quality_gate", "risk_scanner", "content_repurposing"],
        "discover":  ["trending_topics", "competitor_analysis", "content_gap_analysis"],
        "attribute": ["data_tracker", "comment_insights", "strategy_advisor", "content_postmortem"],
        "refine":    ["text_polisher", "text_condenser", "caption_hashtag", "post_formatter",
                      "persona_check"],
        "copywrite": ["casual", "elegant", "lively_girl", "professional"],
        "search":    ["trending_search", "xhs_search"],
    },
    "voiceover": {
        "produce":   ["copywriting", "social_content", "style_transfer"],
        "plan":      ["content_matrix", "hook_generator", "voice_builder"],
        "publish":   ["publish_checklist", "quality_gate"],
        "discover":  ["trending_topics"],
        "attribute": ["data_tracker", "comment_insights"],
        "refine":    ["text_polisher", "caption_hashtag"],
        "search":    ["trending_search", "xhs_search"],
    },
    "short_video": {
        "produce":   ["copywriting", "card_xiaohongshu", "card_quote", "style_transfer"],
        "plan":      ["content_matrix", "hook_generator", "carousel_planner"],
        "publish":   ["publish_checklist", "quality_gate"],
        "discover":  ["trending_topics"],
        "attribute": ["data_tracker", "comment_insights"],
        "refine":    ["caption_hashtag"],
        "search":    ["trending_search", "xhs_search"],
    },
    "ai_edit": {
        "produce":   ["style_transfer", "text_polisher", "text_condenser"],
        "plan":      ["voice_builder", "positioning_analysis"],
        "publish":   ["publish_checklist", "quality_gate", "risk_scanner"],
        "attribute": ["data_tracker", "comment_insights", "strategy_advisor"],
        "refine":    ["persona_check"],
    },
    "long_article": {
        "produce":   ["copywriting", "social_content", "style_transfer"],
        "plan":      ["content_matrix", "topic_evaluator", "hook_generator", "voice_builder"],
        "publish":   ["publish_checklist", "quality_gate"],
        "discover":  ["trending_topics", "competitor_analysis"],
        "attribute": ["data_tracker", "comment_insights", "strategy_advisor"],
        "refine":    ["text_polisher", "caption_hashtag", "post_formatter"],
        "search":    ["trending_search", "xhs_search"],
    },
    "live_clip": {
        "produce":   ["copywriting", "card_xiaohongshu", "caption_hashtag"],
        "plan":      ["hook_generator"],
        "publish":   ["publish_checklist"],
        "attribute": ["data_tracker"],
        "search":    ["trending_search", "xhs_search"],
    },
}

ALWAYS_LOAD_SKILLS: list[str] = [
    "bash", "file_read", "file_edit", "file_write", "glob", "grep",
    "start_workflow",
]


def _resolve_creation_type_skills(creation_type: str | None) -> list[str] | None:
    """按创作类型解析需要的Skill name列表。返回None表示全量加载。"""
    if creation_type is None:
        return None
    mapping = CREATION_TYPE_SKILLS.get(creation_type)
    if mapping is None:
        logger.warning(f"[registry] unknown creation_type={creation_type}, falling back to full skill set")
        return None
    names: list[str] = []
    for group in mapping.values():
        names.extend(group)
    for name in ALWAYS_LOAD_SKILLS:
        if name not in names:
            names.append(name)
    return names


def _build_skills(skill_names: list[str] | None, creation_type: str | None = None) -> list[Any]:
    """按 skill name 从 SkillRegistry 实例化 Skill。

    若 skill_names 为 None 且 creation_type 为 None，动态装载全部已注册 Skill。
    若 creation_type 有值，按 CREATION_TYPE_SKILLS 映射表过滤，只加载该类型需要的子集。
    若 skill_names 显式指定（白名单模式），忽略 creation_type。

    缓存：全量 Skill 无状态，实例化一次后缓存复用；
    按 creation_type 过滤时不走缓存，每次从全量缓存中筛选。
    """
    global _skills_cache

    if skill_names is not None:
        skills: list[Any] = []
        for name in skill_names:
            skill_cls = get_skill_class_by_name(name)
            if skill_cls is None:
                logger.warning(f"[registry] unknown skill name: {name}")
                continue
            skills.append(skill_cls())
        return skills

    resolved = _resolve_creation_type_skills(creation_type)
    if resolved is not None:
        if _skills_cache is None:
            registry = SkillRegistry.instance()
            ensure_builtin_skills_registered()
            registry.scan_third_party(force=False)
            _skills_cache = [cls() for cls in registry.all_skill_classes()]
        name_set = set(resolved)
        filtered = [s for s in _skills_cache if s.name in name_set]

        from app.tools.skill_router import infer_priority, infer_category, SkillPriority, SkillCategory
        _hot_create_names: set[str] = set()
        for s in _skills_cache:
            pri = infer_priority(s)
            cat = infer_category(s)
            if pri == SkillPriority.HOT and cat == SkillCategory.CREATE:
                _hot_create_names.add(s.name)
        existing_names = {s.name for s in filtered}
        for s in _skills_cache:
            if s.name in _hot_create_names and s.name not in existing_names:
                filtered.append(s)

        logger.info(f"[registry] creation_type={creation_type}, skills={len(filtered)}/{len(_skills_cache)}")
        return filtered

    if _skills_cache is not None:
        return _skills_cache
    registry = SkillRegistry.instance()
    ensure_builtin_skills_registered()
    registry.scan_third_party(force=False)
    _skills_cache = [cls() for cls in registry.all_skill_classes()]
    return _skills_cache


class AgentRegistry:
    """Agent 注册表。"""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDef] = dict(BUILTIN_AGENTS)

    def get(self, agent_id: str) -> AgentDef | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentDef]:
        return list(self._agents.values())

    def register(self, agent_def: AgentDef) -> None:
        """注册或覆盖一个 Agent 定义（运行时动态注册）。"""
        existing = self._agents.get(agent_def.agent_id)
        if existing is not None and existing is not agent_def:
            logger.info(
                f"[AgentRegistry] override existing agent: "
                f"{agent_def.agent_id}"
            )
        self._agents[agent_def.agent_id] = agent_def
        logger.debug(f"[AgentRegistry] registered: {agent_def.agent_id}")

    def unregister(self, agent_id: str) -> bool:
        """注销一个运行时注册的 Agent。内置 Agent 不可注销。

        Returns True if successfully removed, False if not found or builtin.
        """
        if agent_id in BUILTIN_AGENTS:
            logger.warning(f"[AgentRegistry] cannot unregister builtin agent: {agent_id}")
            return False
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        logger.info(f"[AgentRegistry] unregistered: {agent_id}")
        return True

    def build_harness(
        self,
        agent_id: str,
        workflow_id: str | None = None,
        creation_type: str | None = None,
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
            LoopExecutor(max_iterations=agent_def.max_iterations)
            if agent_def.executor == "loop"
            else SingleShotExecutor()
        )

        # Observer→SSE 桥接：有 workflow_id 时复用 _make_observer，事件走 sse_bus
        observer = Observer()
        if workflow_id:
            from app.engine.factory import _make_observer

            observer = _make_observer(workflow_id)

        # skills 装配；hard_rules / recovery 的装配仍留到后续 Task
        skills = _build_skills(agent_def.skills, creation_type=creation_type)
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