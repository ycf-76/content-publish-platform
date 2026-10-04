"""D18 用户画像注入链路验收测试（核心验收标准）。

验收链路：
1. 无画像 → start_workflow 拒绝启动（400 + PROFILE_NOT_FOUND，fail-fast）
2. 有画像 → 画像 dict 注入 _execute_graph_safely（→ initial_state → state）
3. initial_state 含 user_profile + experience_hints 恒 None（D19 边界）
4. copywrite prompt 全量含画像（主领域/调性/禁忌）
5. audit prompt 含用户禁忌词/话题
6. 画像注入位置在 start_workflow 入口（节点内不查 DB）

不依赖真实数据库/LLM（AsyncMock + patch）。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.agents.nodes._base import initial_state
from app.db.models import (
    CreatorTone,
    PrimaryDomain,
    UserProfile as UserProfileORM,
    VisualStyle,
    User,
)
from app.services.workflow import WorkflowService


# ----------------------------------------------------------------------
# Mock 基础设施
# ----------------------------------------------------------------------

_PROFILE_DICT = {
    "primary_domain": "tech",
    "sub_domain": "AI编程",
    "tone": "professional",
    "visual_style": "warm",
    "taboo_topics": ["政治"],
    "taboo_words": ["绝对"],
}


def _make_orm_profile(user_id: str = "user_1") -> UserProfileORM:
    return UserProfileORM(
        id="prof_001",
        user_id=user_id,
        primary_domain=PrimaryDomain.TECH,
        sub_domain="AI编程",
        tone=CreatorTone.PROFESSIONAL,
        visual_style=VisualStyle.WARM,
        taboo_topics=["政治"],
        taboo_words=["绝对"],
    )


def _make_service(orm_profile: UserProfileORM | None, user_exists: bool = True):
    """构造 WorkflowService + mock db。

    db.scalar 的返回值按查询实体分发：
    - count(*) → 0（并发检查）
    - User → 已存在用户（或 None 触发自动创建）
    - XhsAccount → None (removed)
    db.execute 的画像查询返回 orm_profile。
    """
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=lambda stmt: _dispatch_scalar(stmt, user_exists))
    db.execute = AsyncMock(
        side_effect=lambda stmt: _dispatch_execute(stmt, orm_profile)
    )
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    svc = WorkflowService(db)
    # 并发检查依赖 redis + DB count，patch 掉减少 mock 面
    svc._check_concurrency_limit = AsyncMock()
    return svc, db


def _dispatch_scalar(stmt, user_exists: bool):
    """db.scalar(side_effect=...)：按查询实体分发返回值。"""
    stmt_str = str(stmt)
    if "users" in stmt_str:
        return User(id="user_1", email="u@x.com", nickname="u1") if user_exists else None
    return 0  # count / 其他


def _dispatch_execute(stmt, orm_profile):
    result = MagicMock()
    # 画像查询：返回给定 ORM 行（None 表示无画像）
    if "user_profiles" in str(stmt):
        result.scalar_one_or_none.return_value = orm_profile
        return result
    result.scalar_one_or_none.return_value = None
    return result


# ----------------------------------------------------------------------
# 验收1: 无画像 → 拒绝启动
# ----------------------------------------------------------------------

def test_start_workflow_without_profile_rejected():
    """无画像 → HTTPException 400, code=PROFILE_NOT_FOUND（fail-fast）。"""
    svc, _db = _make_service(orm_profile=None)

    async def run():
        with patch("app.services.agent_memory.load_for_workflow", new=AsyncMock(return_value={})):
            with pytest.raises(HTTPException) as exc_info:
                await svc.start_workflow(
                    user_id="user_1",
                    account_id="",
                    topic="AI编程",
                )
        return exc_info

    exc_info = asyncio.run(run())
    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert detail["code"] == "PROFILE_NOT_FOUND"
    assert detail["message"] == "请先在设置页完善创作者画像"
    assert detail["detail"]["reason"] == "profile_not_found"
    # fail-fast：Workflow 记录不应被创建
    assert not _db.add.called


# ----------------------------------------------------------------------
# 验收2: 有画像 → 注入 _execute_graph_safely（→ initial_state）
# ----------------------------------------------------------------------

def test_start_workflow_with_profile_injected():
    """有画像 → 启动成功，画像 dict 传入 _execute_graph_safely。"""
    svc, _db = _make_service(orm_profile=_make_orm_profile())
    svc._execute_graph_safely = AsyncMock()

    async def run():
        with patch("app.services.agent_memory.load_for_workflow", new=AsyncMock(return_value={})):
            with patch("app.services.workflow.sse_bus") as mock_bus:
                mock_bus.publish = AsyncMock()
                workflow = await svc.start_workflow(
                    user_id="user_1",
                    account_id="",
                    topic="AI编程",
                )
                # 让后台 task（asyncio.create_task）执行完
                await asyncio.sleep(0.05)
        return workflow

    workflow = asyncio.run(run())
    # 工作流记录创建成功
    assert workflow is not None
    # 核心断言：画像注入图执行链路
    svc._execute_graph_safely.assert_awaited_once()
    kwargs = svc._execute_graph_safely.await_args.kwargs
    assert kwargs["user_profile"] is not None
    assert kwargs["user_profile"]["primary_domain"] == "tech"
    assert kwargs["user_profile"]["sub_domain"] == "AI编程"
    assert kwargs["user_profile"]["taboo_words"] == ["绝对"]


def test_start_workflow_injection_at_entry_not_in_nodes():
    """注入逻辑在 start_workflow 入口：画像查询只发生 1 次（execute 调用计数）。"""
    svc, db = _make_service(orm_profile=_make_orm_profile())
    svc._execute_graph_safely = AsyncMock()

    async def run():
        with patch("app.services.agent_memory.load_for_workflow", new=AsyncMock(return_value={})):
            with patch("app.services.workflow.sse_bus") as mock_bus:
                mock_bus.publish = AsyncMock()
                await svc.start_workflow(user_id="user_1", account_id="", topic="AI编程")
                await asyncio.sleep(0.05)

    asyncio.run(run())
    # 画像相关查询（select UserProfileORM）只执行 1 次
    profile_queries = [
        call for call in db.execute.await_args_list
        if "user_profiles" in str(call.args[0])
    ]
    assert len(profile_queries) == 1


# ----------------------------------------------------------------------
# 验收3: initial_state 含画像 + D19 边界
# ----------------------------------------------------------------------

def test_initial_state_contains_profile():
    state = initial_state(
        workflow_id="wf_1",
        user_id="user_1",
        account_id="",
        topic="AI编程",
        user_profile=_PROFILE_DICT,
    )
    assert state["user_profile"] == _PROFILE_DICT
    # D19 边界：experience_hints 恒 None，无任何注入逻辑
    assert state["experience_hints"] is None


def test_initial_state_without_profile_keeps_none():
    """老链路（无画像参数）state 画像为 None，字段存在且可读。"""
    state = initial_state(
        workflow_id="wf_1",
        user_id="user_1",
        account_id="",
        topic="AI编程",
    )
    assert state.get("user_profile") is None
    assert state.get("experience_hints") is None


# ----------------------------------------------------------------------
# 验收4: copywrite prompt 全量含画像
# ----------------------------------------------------------------------

def test_copywrite_prompt_contains_full_profile():
    from app.tools.copywrite_builder import (
        CopywriteSkillBase,
        LivelyGirlCopywriteSkill,
        _build_profile_section,
    )

    # 4a: 段落构建函数（schema 路径）
    section = _build_profile_section(_PROFILE_DICT)
    assert "【创作者画像】" in section
    assert "主领域" in section and "科技" in section and "AI编程" in section
    assert "调性: 专业" in section
    assert "视觉风格: 暖色调" in section
    assert "禁忌话题: 政治" in section
    assert "禁忌用词: 绝对" in section

    # 4b: 降级路径（非法枚举值走原始键值渲染，不中断文案生成）
    fallback_section = _build_profile_section({
        "primary_domain": "tech",
        "tone": "not_a_tone",  # 非法枚举 → schema 校验失败 → 降级
        "taboo_words": ["绝对"],
    })
    assert "主领域: tech" in fallback_section
    assert "禁忌用词: 绝对" in fallback_section

    # 4c: 空画像 → 空段落
    assert _build_profile_section({}) == ""
    assert _build_profile_section(None) == ""  # type: ignore[arg-type]

    # 4d: 完整 prompt 模板渲染（streaming + json 两条路径）
    skill = LivelyGirlCopywriteSkill()
    assert isinstance(skill, CopywriteSkillBase)
    streaming_prompt = skill._build_streaming_prompt(
        topic="AI编程",
        insights={},
        patterns={},
        execution_brief={},
        image_details=[],
        image_style="",
        user_profile=_PROFILE_DICT,
    )
    assert "【创作者画像】" in streaming_prompt
    assert "科技" in streaming_prompt
    assert "调性: 专业" in streaming_prompt

    json_prompt = skill.build_prompt(
        topic="AI编程",
        insights={},
        patterns={},
        execution_brief={},
        image_details=[],
        image_style="",
        user_profile=_PROFILE_DICT,
    )
    assert "【创作者画像】" in json_prompt
    assert "禁忌用词: 绝对" in json_prompt


def test_copywrite_prompt_without_profile_unchanged():
    """无画像时 prompt 不含画像段落（老工作流回放不受影响）。"""
    from app.tools.copywrite_builder import LivelyGirlCopywriteSkill

    skill = LivelyGirlCopywriteSkill()
    prompt = skill._build_streaming_prompt(
        topic="AI编程",
        insights={},
        patterns={},
        execution_brief={},
        image_details=[],
        image_style="",
        user_profile=None,
    )
    assert "【创作者画像】" not in prompt


def test_copywrite_node_extracts_profile_from_state():
    """copywrite 节点从 state 提取画像并传给 skill inputs。"""
    from app.agents.nodes.copywrite import CopywriteContext

    state = {
        "workflow_id": "wf_1",
        "user_id": "user_1",
        "account_id": "",
        "topic": "AI编程",
        "node_outputs": {},
        "user_profile": _PROFILE_DICT,
    }
    ctx = CopywriteContext.from_state(state)
    assert ctx.user_profile["primary_domain"] == "tech"
    assert ctx.user_profile["taboo_words"] == ["绝对"]


# ----------------------------------------------------------------------
# 验收5: audit prompt 含用户禁忌
# ----------------------------------------------------------------------

def test_audit_prompt_contains_taboo():
    from app.tools.audit_skill import StandardAuditSkill, _build_audit_profile_section

    # 5a: 段落构建
    section = _build_audit_profile_section(_PROFILE_DICT)
    assert "用户禁忌" in section
    assert "绝对" in section
    assert "政治" in section

    # 空画像 → 空段落（审核维度只有4条）
    assert _build_audit_profile_section({}) == ""
    assert _build_audit_profile_section(None) == ""  # type: ignore[arg-type]

    # 5b: 完整审核 prompt
    skill = StandardAuditSkill()
    template = (
        "## 审核维度\n\n1. 合规\n2. 平台\n3. 质量\n4. 品牌\n{user_profile_section}\n"
    )
    prompt = skill.build_prompt(
        topic="AI编程",
        copywrite={"title": "t", "content": "c", "tags": []},
        template=template,
        user_profile=_PROFILE_DICT,
    )
    assert "用户禁忌" in prompt
    assert "禁忌用词（标题/正文/标签中严禁出现）: 绝对" in prompt
    assert "禁忌话题（内容不得涉及）: 政治" in prompt

    # 5c: 无画像时模板占位符渲染为空串
    prompt_no_profile = skill.build_prompt(
        topic="AI编程",
        copywrite={"title": "t", "content": "c", "tags": []},
        template=template,
        user_profile=None,
    )
    assert "用户禁忌" not in prompt_no_profile


def test_real_audit_md_template_has_placeholder():
    """真实 prompts/audit.md 模板含 {user_profile_section} 占位符。"""
    from app.tools.audit_skill import _load_audit_prompt

    template = _load_audit_prompt()
    assert template, "audit.md 模板应存在且非空"
    assert "{user_profile_section}" in template


# ----------------------------------------------------------------------
# 验收6: 画像经 WorkflowContext 透传 harness
# ----------------------------------------------------------------------

def test_workflow_context_carries_profile():
    from app.engine.schemas import WorkflowContext

    ctx = WorkflowContext(
        workflow_id="wf_1",
        node_id="search",
        user_id="user_1",
        account_id="",
        user_profile=_PROFILE_DICT,
    )
    assert ctx.user_profile is not None
    assert ctx.user_profile["primary_domain"] == "tech"

    # 默认 None（老调用方兼容）
    ctx_default = WorkflowContext(workflow_id="wf_1", node_id="search", user_id="u", account_id="")
    assert ctx_default.user_profile is None