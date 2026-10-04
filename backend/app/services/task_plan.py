"""任务清单服务（多日定时发布）。

无缝切入现有模块，不引入新调度/审核/渲染体系：
- 调度：复用 pool_monitor/scheduler 的 APScheduler 单例（main.py lifespan 注册）
- 执行：复用 WorkflowService.start_workflow（source="task_plan" + definition「定时发布流水线」）
- 审核：复用 LangGraph interrupt/resume（submit_review pass/reject）
- 出图：复用 services/card_renderer.render_card_set（服务端渲染）
        + inject_card_images 的注入机制（save_workflow_images + aupdate_state）
- 通知：复用 adapters/feishu.FeishuClient + notification_bus（降级站内通知）

三层模型：
TaskPlan（清单，用户一句话意图）→ TaskItem（逐日子任务）→ TaskRun（单日执行现场）

job 入口 run_task_scan() 由 main.py lifespan 注册（每分钟），模式同 workflow_cleanup。
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    TaskItem,
    TaskItemStatus,
    TaskPlan,
    TaskPlanStatus,
    TaskRun,
    TaskRunStatus,
    Workflow,
    WorkflowStatus,
    WorkflowDefinition,
)
from app.db.session import AsyncSessionLocal
from app.services.notification_bus import notification_bus

logger = logging.getLogger(__name__)

# 上海时区（plan_time 的 HH:MM 按此时区解释）
_TZ_SH = timezone(timedelta(hours=8))

# 每轮最多执行几个到期任务（防积压雪崩）
_SCAN_BATCH_LIMIT = 5

# 「定时发布流水线」内置定义名（seed_workflow_definitions.py）
_TASK_PIPELINE_DEF_NAME = "定时发布流水线"

# quality_gate 自动通过分数阈值（0-10，偏保守）
_QUALITY_GATE_THRESHOLD = 7.0


def _now() -> datetime:
    return datetime.now(UTC)


# ============================================================================
# 拆解器：用户一句话意图 → 结构化逐日清单
# ============================================================================

_DECOMPOSE_SYSTEM_PROMPT = """你是小红书内容排期助手。把用户的发布意图拆解成逐日清单。

要求：
1. 输出严格 JSON，不要任何其他文字。结构：
{"title": "清单标题", "daily_time": "HH:MM", "total_days": N,
 "items": [{"day_index": 1, "topic": "当天发布主题", "keyword": "搜索关键词"}],
 "warnings": ["需要提醒用户的事项"]}
2. 单词/知识点类清单：每天换不同角度（单词卡/联想记忆/真题例句/易混对比），topic 要具体到当天内容。
3. 禁止编造用户没有给出的条目；用户给了 10 个单词就拆 10 天，每天对应一个。
4. 用户未指定发布时间时 daily_time 用 "09:00"，并在 warnings 里说明。
5. total_days 不超过 60。topic 80 字以内。"""


def _parse_daily_time(value: str | None) -> str:
    """校验 HH:MM，非法回退 09:00。"""
    if not value:
        return "09:00"
    try:
        h, m = value.strip().split(":")
        if 0 <= int(h) <= 23 and 0 <= int(m) <= 59:
            return f"{int(h):02d}:{int(m):02d}"
    except Exception:
        pass
    return "09:00"


def _rule_based_decompose(intent_text: str, daily_time: str) -> dict[str, Any]:
    """dry-run 规则拆解：不调 LLM，按行/分隔符切条目。用于零 token 测试与 LLM 失败降级。"""
    lines = [ln.strip(" \t-•0123456789.、") for ln in intent_text.splitlines()]
    entries = [ln for ln in lines if ln]
    if len(entries) <= 1:
        # 单行内的顿号/逗号/分号列表（中英文均支持）
        single = entries[0] if entries else intent_text.strip()
        normalized = (
            single.replace("；", ";").replace("、", ";")
            .replace("，", ";").replace(",", ";")
        )
        entries = [e.strip() for e in normalized.split(";") if e.strip()]
    warnings: list[str] = []
    if not entries:
        entries = [intent_text.strip()[:80] or "未命名主题"]
        warnings.append("未能从意图中识别出多条目，已按单日任务处理，请手动补充清单")
    items = [
        {"day_index": i + 1, "topic": e[:500], "keyword": e[:200]}
        for i, e in enumerate(entries[:60])
    ]
    return {
        "title": (entries[0][:40] + ("…" if len(entries[0]) > 40 else "")) or "任务清单",
        "daily_time": daily_time,
        "total_days": len(items),
        "items": items,
        "warnings": warnings + ["dry-run 规则拆解结果（未调用 LLM）"],
    }


def _validate_decompose(data: dict[str, Any]) -> list[str]:
    """拆解结果结构性校验，返回错误列表（空 = 合法）。"""
    errors: list[str] = []
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return ["items 为空"]
    if len(items) > 60:
        errors.append("条目数超过 60")
    day_indexes: list[int] = []
    for i, it in enumerate(items):
        di = it.get("day_index")
        topic = str(it.get("topic", "")).strip()
        if not isinstance(di, int) or di < 1:
            errors.append(f"第 {i+1} 条 day_index 非法: {di!r}")
        else:
            day_indexes.append(di)
        if not topic:
            errors.append(f"第 {i+1} 条 topic 为空")
    if day_indexes and sorted(day_indexes) != list(range(1, len(day_indexes) + 1)):
        errors.append("day_index 不连续（必须从 1 开始逐日递增）")
    return errors


async def _call_llm_json(system: str, user: str, timeout: int = 40) -> dict[str, Any] | None:
    """轻量 LLM 调用（OpenAI 兼容协议，同 monitor_agent._classify_with_llm 模式）。

    失败返回 None（调用方降级），不抛异常。
    """
    settings = get_settings()
    api_key = (settings.deepseek_api_key or "").strip()
    base_url = (settings.deepseek_base_url or "https://api.deepseek.com").rstrip("/")
    if not api_key:
        logger.warning("[task_plan] LLM 调用跳过：未配置 deepseek_api_key")
        return None
    payload = {
        "model": settings.deepseek_model_v3 or "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return json.loads(text)
    except Exception as e:
        logger.warning(f"[task_plan] LLM 调用失败: {e}")
        return None


async def decompose_intent(
    intent_text: str,
    daily_time: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """把用户意图拆解为逐日清单预览（无副作用，不落库）。

    dry_run=True 时不调 LLM（零 token 测试路径），用规则拆解。
    LLM 失败/校验失败时自动降级规则拆解，并在 warnings 说明。
    """
    dt = _parse_daily_time(daily_time)
    if dry_run:
        return _rule_based_decompose(intent_text, dt)

    result = await _call_llm_json(
        _DECOMPOSE_SYSTEM_PROMPT,
        f"每日发布时间偏好：{dt}\n用户意图：\n{intent_text}",
    )
    if result is not None:
        errors = _validate_decompose(result)
        if not errors:
            result["daily_time"] = _parse_daily_time(result.get("daily_time") or dt)
            return result
        # 校验失败重试一次
        logger.warning(f"[task_plan] 拆解校验失败，重试一次: {errors}")
        result = await _call_llm_json(
            _DECOMPOSE_SYSTEM_PROMPT,
            f"上一次输出未通过校验（错误：{errors}），请修正后重新输出严格 JSON。\n"
            f"每日发布时间偏好：{dt}\n用户意图：\n{intent_text}",
        )
        if result is not None and not _validate_decompose(result):
            result["daily_time"] = _parse_daily_time(result.get("daily_time") or dt)
            return result

    fallback = _rule_based_decompose(intent_text, dt)
    fallback["warnings"] = fallback.get("warnings", []) + [
        "LLM 拆解失败，已降级为规则拆解，请手动核对清单"
    ]
    return fallback


# ============================================================================
# 核心服务
# ============================================================================

class TaskPlanService:
    """任务清单 CRUD + 到期执行 + 挂起处理 + 状态收敛。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 查询 ----------

    async def list_plans(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.db.scalars(
            select(TaskPlan)
            .where(TaskPlan.user_id == user_id)
            .order_by(TaskPlan.created_at.desc())
        )
        return [self._plan_to_dict(p) for p in rows]

    async def get_plan_detail(self, user_id: str, plan_id: str) -> dict[str, Any] | None:
        plan = await self.db.scalar(
            select(TaskPlan).where(
                TaskPlan.id == plan_id, TaskPlan.user_id == user_id
            )
        )
        if not plan:
            return None
        items = await self.db.scalars(
            select(TaskItem)
            .where(TaskItem.plan_id == plan_id)
            .order_by(TaskItem.day_index)
        )
        runs = await self.db.scalars(
            select(TaskRun)
            .where(TaskRun.plan_id == plan_id)
            .order_by(TaskRun.created_at.desc())
            .limit(200)
        )
        run_map: dict[str, dict] = {}
        for r in runs:
            run_map.setdefault(r.task_item_id, self._run_to_dict(r))
        return {
            **self._plan_to_dict(plan),
            "items": [
                {**self._item_to_dict(it), "latest_run": run_map.get(it.id)}
                for it in items
            ],
        }

    # ---------- 创建 / 生命周期 ----------

    async def create_plan(
        self,
        user_id: str,
        intent_text: str,
        items: list[dict[str, Any]],
        plan_config: dict[str, Any] | None = None,
        account_id: str | None = None,
        title: str = "",
    ) -> TaskPlan:
        """落库并激活清单（前端已确认过拆解预览）。

        items 为用户编辑后的最终清单：[{day_index, topic, keyword?}]。
        plan_time 按 today + day_index - 1 的 daily_time（Asia/Shanghai）回填。
        """
        config = dict(plan_config or {})
        daily_time = _parse_daily_time(config.get("daily_time"))
        config["daily_time"] = daily_time
        # 默认质量门审核 + 自动发布
        config.setdefault("review_mode", "quality_gate")
        config.setdefault("model_settings", {})
        config["model_settings"]["auto_publish"] = True
        config.setdefault("confirm_timeout_min", 30)
        config.setdefault("max_retry", 1)

        plan = TaskPlan(
            user_id=user_id,
            account_id=account_id or None,
            title=(title or intent_text.strip()[:100])[:200],
            intent_text=intent_text,
            status=TaskPlanStatus.ACTIVE,
            plan_config=config,
            total_days=len(items),
        )
        self.db.add(plan)
        await self.db.flush()

        base_date = datetime.now(_TZ_SH).date()
        hh, mm = daily_time.split(":")
        for it in items:
            plan_time = datetime(
                base_date.year, base_date.month, base_date.day,
                int(hh), int(mm), tzinfo=_TZ_SH,
            ) + timedelta(days=max(int(it.get("day_index", 1)) - 1, 0))
            self.db.add(
                TaskItem(
                    plan_id=plan.id,
                    day_index=int(it.get("day_index", 1)),
                    topic=str(it.get("topic", ""))[:500],
                    keyword=(str(it["keyword"])[:200] if it.get("keyword") else None),
                    plan_time=plan_time,
                    status=TaskItemStatus.PENDING,
                )
            )
        await self.db.commit()
        await self.db.refresh(plan)
        logger.info(
            f"[task_plan] plan created: {plan.id}, days={plan.total_days}, "
            f"daily_time={daily_time}, review_mode={config['review_mode']}"
        )
        return plan

    async def pause_plan(self, user_id: str, plan_id: str) -> bool:
        plan = await self.db.scalar(
            select(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id)
        )
        if not plan or plan.status != TaskPlanStatus.ACTIVE:
            return False
        plan.status = TaskPlanStatus.PAUSED
        await self.db.commit()
        return True

    async def resume_plan(self, user_id: str, plan_id: str) -> bool:
        plan = await self.db.scalar(
            select(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id)
        )
        if not plan or plan.status != TaskPlanStatus.PAUSED:
            return False
        plan.status = TaskPlanStatus.ACTIVE
        await self.db.commit()
        return True

    async def cancel_plan(self, user_id: str, plan_id: str) -> bool:
        """取消清单：pending 条目全部置 cancelled，running 条目保持（执行中不动）。"""
        plan = await self.db.scalar(
            select(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id)
        )
        if not plan or plan.status in (TaskPlanStatus.CANCELLED, TaskPlanStatus.COMPLETED):
            return False
        plan.status = TaskPlanStatus.CANCELLED
        await self.db.execute(
            sa_update(TaskItem)
            .where(TaskItem.plan_id == plan_id, TaskItem.status == TaskItemStatus.PENDING)
            .values(status=TaskItemStatus.CANCELLED)
        )
        await self.db.commit()
        return True

    # ---------- 到期执行 ----------

    async def scan_and_execute(self) -> dict[str, int]:
        """捞到期任务并执行（每分钟 job 调用）。返回统计。"""
        result = {"executed": 0, "failed": 0}
        now = _now()
        # 只扫 active plan 下到期 pending 条目
        rows = await self.db.execute(
            select(TaskItem, TaskPlan)
            .join(TaskPlan, TaskItem.plan_id == TaskPlan.id)
            .where(
                TaskItem.status == TaskItemStatus.PENDING,
                TaskItem.plan_time <= now,
                TaskPlan.status == TaskPlanStatus.ACTIVE,
            )
            .order_by(TaskItem.plan_time)
            .limit(_SCAN_BATCH_LIMIT)
        )
        for item, plan in rows.all():
            ok = await self._execute_item(item, plan)
            if ok:
                result["executed"] += 1
            else:
                result["failed"] += 1
        if result["executed"] or result["failed"]:
            await self.db.commit()
        return result

    async def _execute_item(self, item: TaskItem, plan: TaskPlan) -> bool:
        """执行单个到期条目：原子翻转 → 账号预检 → 拉起工作流。"""
        # 原子防重：仅当仍为 pending 时翻转（与扫描 job 的 max_instances=1 双保险）
        flip = await self.db.execute(
            sa_update(TaskItem)
            .where(TaskItem.id == item.id, TaskItem.status == TaskItemStatus.PENDING)
            .values(status=TaskItemStatus.RUNNING)
        )
        if flip.rowcount != 1:
            return False

        # 账号预检：掉线直接失败 + plan 暂停 + 通知，不烧生成 token
        if plan.account_id:
            account = None  # XhsAccount removed
            if not account or account.status.value != "active":
                await self._fail_item(
                    item, plan,
                    reason=f"小红书账号不可用（status={account.status.value if account else 'missing'}）",
                    pause_plan=True,
                )
                await self._notify_feishu_or_fallback(
                    plan, "任务清单已暂停：小红书账号失效",
                    f"清单「{plan.title}」Day {item.day_index} 发布前检测到账号不可用，"
                    f"已暂停全部后续任务。请重新登录后手动恢复。",
                )
                return False

        definition_id = await self._get_pipeline_definition_id()

        # 拉起工作流（复用 start_workflow，source 标记来源）
        from app.services.workflow import WorkflowService

        try:
            svc = WorkflowService(self.db)
            model_settings = dict((plan.plan_config or {}).get("model_settings") or {})
            model_settings["auto_publish"] = True  # publish 节点不挂起
            # 发布策略：manual（默认，半自动等手动点击）| auto（实验性自动点击）
            model_settings.setdefault(
                "publish_strategy",
                (plan.plan_config or {}).get("publish_strategy", "manual"),
            )
            workflow = await svc.start_workflow(
                user_id=plan.user_id,
                account_id=plan.account_id or "",
                topic=item.topic,
                search_keyword=item.keyword or None,
                model_settings=model_settings,
                definition_id=definition_id,
                source="task_plan",
            )
        except Exception as e:
            logger.exception(f"[task_plan] start_workflow failed for item {item.id}: {e}")
            await self._fail_item(item, plan, reason=f"工作流启动失败: {e}")
            return False

        item.workflow_id = workflow.id
        self.db.add(
            TaskRun(
                task_item_id=item.id,
                plan_id=plan.id,
                workflow_id=workflow.id,
                status=TaskRunStatus.RUNNING,
            )
        )
        logger.info(
            f"[task_plan] item executed: plan={plan.id} day={item.day_index} "
            f"workflow={workflow.id}"
        )
        return True

    async def _get_pipeline_definition_id(self) -> str | None:
        """查「定时发布流水线」内置定义 id（进程内缓存）。"""
        global _PIPELINE_DEF_CACHE
        if _PIPELINE_DEF_CACHE:
            return _PIPELINE_DEF_CACHE
        row = await self.db.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.name == _TASK_PIPELINE_DEF_NAME,
                WorkflowDefinition.is_builtin == True,  # noqa: E712
            )
        )
        if row:
            _PIPELINE_DEF_CACHE = row.id
        return row.id if row else None

    # ---------- 运行状态收敛 ----------

    async def sync_running_runs(self) -> dict[str, int]:
        """把 running TaskRun 按对应 Workflow 终态收敛。"""
        result = {"published": 0, "failed": 0, "unchanged": 0}
        runs = await self.db.scalars(
            select(TaskRun).where(TaskRun.status == TaskRunStatus.RUNNING).limit(50)
        )
        for run in runs:
            if not run.workflow_id:
                continue
            wf = await self.db.get(Workflow, run.workflow_id)
            if not wf:
                continue
            status = wf.status.value if hasattr(wf.status, "value") else str(wf.status)
            item = await self.db.get(TaskItem, run.task_item_id)
            plan = await self.db.get(TaskPlan, run.plan_id)
            if not item or not plan:
                continue

            if status == "completed":
                run.status = TaskRunStatus.SUCCEEDED
                run.finished_at = _now()
                item.status = TaskItemStatus.PUBLISHED
                plan.published_days += 1
                await self._maybe_complete_plan(plan)
                result["published"] += 1
            elif status in ("failed", "terminated", "cancelled", "suspended"):
                await self._fail_item(item, plan, reason=f"工作流终态 {status}", run=run)
                result["failed"] += 1
            else:
                # running / paused：paused 由 handle_paused_workflows 处理
                result["unchanged"] += 1
        await self.db.commit()
        return result

    async def _maybe_complete_plan(self, plan: TaskPlan) -> None:
        """所有条目终态后置 completed。"""
        pending_cnt = await self.db.scalar(
            select(TaskItem.id)
            .where(
                TaskItem.plan_id == plan.id,
                TaskItem.status.in_([
                    TaskItemStatus.PENDING, TaskItemStatus.RUNNING,
                ]),
            )
            .limit(1)
        )
        if not pending_cnt:
            plan.status = TaskPlanStatus.COMPLETED

    async def _fail_item(
        self,
        item: TaskItem,
        plan: TaskPlan,
        reason: str,
        run: TaskRun | None = None,
        pause_plan: bool = False,
    ) -> None:
        """失败处理：当日重试一次（30 分钟后重扫），超限置 failed 并通知。

        连续 2 日失败或显式要求 → plan 自动暂停 + 通知（防持续烧 token）。
        """
        config = plan.plan_config or {}
        max_retry = int(config.get("max_retry", 1))
        if item.retry_count < max_retry:
            # 回置 pending，30 分钟后重扫
            item.retry_count += 1
            item.status = TaskItemStatus.PENDING
            item.plan_time = _now() + timedelta(minutes=30)
            item.last_error = {"reason": reason[:500], "at": _now().isoformat()}
            logger.warning(
                f"[task_plan] item retry {item.retry_count}/{max_retry}: "
                f"plan={plan.id} day={item.day_index} reason={reason[:120]}"
            )
            return

        item.status = TaskItemStatus.FAILED
        item.last_error = {"reason": reason[:500], "at": _now().isoformat()}
        plan.failed_days += 1
        if run:
            run.status = TaskRunStatus.FAILED
            run.failure_reason = reason[:500]
            run.finished_at = _now()

        should_pause = pause_plan or plan.failed_days >= 2
        if should_pause and plan.status == TaskPlanStatus.ACTIVE:
            plan.status = TaskPlanStatus.PAUSED
        await self._notify_feishu_or_fallback(
            plan,
            f"定时任务失败（Day {item.day_index}）",
            f"清单「{plan.title}」Day {item.day_index} 执行失败：{reason[:300]}\n"
            + ("连续失败已达 2 天，清单已自动暂停。" if should_pause else "将在下个周期重试。"),
        )
        logger.error(
            f"[task_plan] item failed: plan={plan.id} day={item.day_index} reason={reason[:200]}"
        )

    # ---------- 挂起工作流处理（审核三档 + 服务端渲染） ----------

    async def handle_paused_workflows(self) -> dict[str, int]:
        """处理 source=task_plan 且 PAUSED 的挂起工作流（每分钟 job 调用）。

        挂起点分派（按 LangGraph next 节点）：
        - image_gen：卡片编辑挂起 → 服务端渲染出图 → 注入 → resume
        - image_review / final_review / publish：按 plan_config.review_mode
          - auto：直接 pass
          - quality_gate：轻量 LLM 评分，≥阈值 pass，否则发飞书卡片等人
          - manual：发飞书卡片等人
        - 确认超时：TaskRun.awaiting_confirmation 超 confirm_timeout_min →
          跳过本条 + 终止工作流 + 通知
        """
        result = {"auto_passed": 0, "rendered": 0, "card_sent": 0, "timeout": 0, "unchanged": 0}

        # 等确认超时的 run（先处理超时，避免继续等）
        await self._handle_confirm_timeouts(result)

        rows = await self.db.execute(
            select(TaskRun, Workflow, TaskPlan)
            .join(Workflow, TaskRun.workflow_id == Workflow.id)
            .join(TaskPlan, TaskRun.plan_id == TaskPlan.id)
            .where(
                TaskRun.status.in_([TaskRunStatus.RUNNING, TaskRunStatus.AWAITING_CONFIRMATION]),
                Workflow.status == WorkflowStatus.PAUSED,
                Workflow.source == "task_plan",
            )
            .limit(20)
        )
        for run, wf, plan in rows.all():
            try:
                await self._process_one_paused(run, wf, plan, result)
            except Exception as e:
                logger.exception(f"[task_plan] handle paused workflow {wf.id} failed: {e}")
        await self.db.commit()
        return result

    async def _process_one_paused(
        self, run: TaskRun, wf: Workflow, plan: TaskPlan, result: dict[str, int]
    ) -> None:
        from app.services.workflow import WorkflowService

        svc = WorkflowService(self.db)
        # 同 inject_card_images 的 rebuild 路径：按 definition 重建 graph 以访问 checkpoint
        graph, _ = await svc._get_graph_for_workflow(wf)  # noqa: SLF001
        if graph is None:
            logger.warning(f"[task_plan] rebuild graph failed for {wf.id}, skip")
            result["unchanged"] += 1
            return
        config = {
            "configurable": {"thread_id": wf.id},
            "recursion_limit": 50,
            "metadata": {"workflow_id": wf.id},
        }
        graph_state = await graph.aget_state(config)
        next_nodes = list(getattr(graph_state, "next", None) or ())
        if not next_nodes:
            result["unchanged"] += 1
            return
        next_node = next_nodes[0]
        state_values = graph_state.values or {}

        # 已在等确认：不重复发卡
        if run.status == TaskRunStatus.AWAITING_CONFIRMATION:
            result["unchanged"] += 1
            return

        review_mode = (plan.plan_config or {}).get("review_mode", "quality_gate")

        # 1. 卡片编辑挂起 → 服务端渲染注入（无人值守生图的关键路径）
        if next_node == "image_gen":
            injected = await self._render_and_inject(wf, state_values, config, graph)
            if injected:
                result["rendered"] += 1
                await svc.submit_review(workflow_id=wf.id, action="pass", user_id=plan.user_id)
            else:
                # 渲染失败 → 按失败处理（会重试/通知）
                item = await self.db.get(TaskItem, run.task_item_id)
                if item:
                    await self._fail_item(item, plan, reason="服务端卡片渲染失败", run=run)
            return

        # 2. 审核类挂起点
        if next_node in ("image_review", "final_review", "publish"):
            if review_mode == "auto":
                await svc.submit_review(workflow_id=wf.id, action="pass", user_id=plan.user_id)
                result["auto_passed"] += 1
                return
            if review_mode == "quality_gate":
                passed = await self._quality_gate_check(wf, state_values)
                if passed:
                    await svc.submit_review(workflow_id=wf.id, action="pass", user_id=plan.user_id)
                    result["auto_passed"] += 1
                    return
            # manual 或 quality_gate 未通过 → 发飞书卡片等人
            sent = await self._send_confirm_card(run, wf, plan, next_node, state_values)
            if sent:
                run.status = TaskRunStatus.AWAITING_CONFIRMATION
                detail = dict(run.detail or {})
                detail["confirm_sent_at"] = _now().isoformat()
                detail["confirm_node"] = next_node
                run.detail = detail
                result["card_sent"] += 1
            else:
                # 通知不可达（未配置飞书）→ 保守失败并记录
                item = await self.db.get(TaskItem, run.task_item_id)
                if item:
                    await self._fail_item(
                        item, plan,
                        reason=f"需要人工确认（{next_node}）但飞书通知不可达，请检查飞书配置",
                        run=run,
                    )
            return

        # 3. 其他挂起点（如 copywrite 方向选择兜底）：auto/quality_gate 模式直接 pass
        if review_mode in ("auto", "quality_gate"):
            await svc.submit_review(workflow_id=wf.id, action="pass", user_id=plan.user_id)
            result["auto_passed"] += 1
        else:
            result["unchanged"] += 1

    async def _render_and_inject(
        self, wf: Workflow, state_values: dict, config: dict, graph: Any
    ) -> bool:
        """服务端渲染卡片并注入 image_gen（复用 inject_card_images 机制）。"""
        try:
            from app.services.card_renderer import render_card_set
            from app.services.image_store import save_workflow_images

            node_outputs = state_values.get("node_outputs") or {}
            copy_out = node_outputs.get("copywrite") or {}
            plan_out = node_outputs.get("image_plan") or {}
            # 文案来源：copywrite 输出（各字段容错）
            title = (
                copy_out.get("title")
                or (copy_out.get("content_plan") or {}).get("title")
                or wf.topic
            )
            content = copy_out.get("content") or copy_out.get("body") or ""
            tags = copy_out.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            style = (plan_out.get("content_plan") or {}).get("image_style") \
                or ((state_values.get("model_settings") or {}).get("image_style")) \
                or "fresh_natural"

            rendered = await render_card_set(
                title=str(title)[:20],  # 小红书标题 20 字限制
                content=str(content),
                tags=[str(t)[:30] for t in tags[:5]],
                topic=wf.topic,
                style_name=str(style),
            )
            images_base64 = rendered.get("images_base64") or []
            if not images_base64:
                return False

            image_urls = save_workflow_images(wf.id, images_base64)
            from app.agents.graph import NodeStatus

            update_payload = {
                "node_statuses": {"image_gen": NodeStatus.COMPLETED.value},
                "node_outputs": {
                    "image_gen": {
                        "image_urls": image_urls,
                        "image_count": len(images_base64),
                        "image_details": rendered.get("image_details", []),
                        "style": rendered.get("style", "服务端渲染"),
                        "plan_context": {},
                    }
                },
            }
            await graph.aupdate_state(config, update_payload, as_node="image_gen")
            logger.info(
                f"[task_plan] server-side rendered {len(images_base64)} cards "
                f"and injected into {wf.id}"
            )
            return True
        except Exception as e:
            logger.exception(f"[task_plan] render_and_inject failed for {wf.id}: {e}")
            return False

    async def _quality_gate_check(self, wf: Workflow, state_values: dict) -> bool:
        """轻量 LLM 质量门：文案+图片张数 → 0-10 分。LLM 不可用视为不通过（保守转人工）。"""
        node_outputs = state_values.get("node_outputs") or {}
        copy_out = node_outputs.get("copywrite") or {}
        image_out = node_outputs.get("image_gen") or {}
        title = str(copy_out.get("title") or "")[:100]
        content = str(copy_out.get("content") or copy_out.get("body") or "")[:600]
        image_count = image_out.get("image_count", 0)

        if not title.strip() and not content.strip():
            return False
        if not image_count:
            return False

        verdict = await _call_llm_json(
            "你是小红书内容质量审核员。对以下待发布内容打分（0-10 整数）。"
            "评分标准：标题吸引力(3分)、正文完整性与可读性(4分)、与主题相关性(3分)。"
            '输出严格 JSON：{"score": N, "reason": "一句话理由"}。7 分及以上视为通过。',
            f"主题：{wf.topic}\n标题：{title}\n正文：{content}\n图片张数：{image_count}",
            timeout=20,
        )
        if verdict is None:
            return False  # LLM 不可用 → 保守转人工
        try:
            score = float(verdict.get("score", 0))
        except (TypeError, ValueError):
            return False
        logger.info(f"[task_plan] quality_gate {wf.id}: score={score}")
        return score >= _QUALITY_GATE_THRESHOLD

    async def _handle_confirm_timeouts(self, result: dict[str, int]) -> None:
        """确认超时：跳过本条 + 终止工作流 + 通知。"""
        runs = await self.db.scalars(
            select(TaskRun).where(
                TaskRun.status == TaskRunStatus.AWAITING_CONFIRMATION
            ).limit(20)
        )
        for run in runs:
            plan = await self.db.get(TaskPlan, run.plan_id)
            if not plan:
                continue
            timeout_min = int((plan.plan_config or {}).get("confirm_timeout_min", 30))
            sent_at = (run.detail or {}).get("confirm_sent_at")
            if not sent_at:
                continue
            try:
                sent_dt = datetime.fromisoformat(sent_at)
            except ValueError:
                continue
            if _now() - sent_dt < timedelta(minutes=timeout_min):
                continue

            item = await self.db.get(TaskItem, run.task_item_id)
            if item:
                item.status = TaskItemStatus.SKIPPED
                item.last_error = {"reason": "人工确认超时，已跳过", "at": _now().isoformat()}
            run.status = TaskRunStatus.TIMEOUT
            run.finished_at = _now()
            if run.workflow_id:
                wf = await self.db.get(Workflow, run.workflow_id)
                if wf and wf.status == WorkflowStatus.PAUSED:
                    wf.status = WorkflowStatus.TERMINATED
            result["timeout"] += 1
            await self._notify_feishu_or_fallback(
                plan, "定时任务确认超时",
                f"清单「{plan.title}」有任务等待确认超过 {timeout_min} 分钟，已自动跳过。",
            )

    async def handle_card_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        """处理飞书确认卡片回调（card.action.trigger，由 feishu_bot 路由转入）。

        action 三分支：
        - approve → submit_review(pass) resume，run 回 RUNNING
        - regenerate → submit_review(reject) 回退上游重做（图片/文案）
        - skip → 终止工作流 + 当日条目/执行记 skipped，清单继续下一天

        幂等：仅处理 AWAITING_CONFIRMATION 的 run，重复点击返回已处理。
        """
        action = str(payload.get("action", ""))
        plan_id = str(payload.get("plan_id", ""))
        workflow_id = str(payload.get("workflow_id", ""))

        if action not in ("approve", "regenerate", "skip"):
            return {"success": False, "message": f"未知操作: {action}"}

        plan = await self.db.get(TaskPlan, plan_id)
        if not plan:
            return {"success": False, "message": "清单不存在或已删除"}

        run = (await self.db.execute(
            select(TaskRun).where(
                TaskRun.workflow_id == workflow_id,
                TaskRun.status == TaskRunStatus.AWAITING_CONFIRMATION,
            ).limit(1)
        )).scalar_one_or_none()
        if run is None:
            return {"success": False, "message": "该任务不在等待确认状态（可能已处理过）"}

        from app.services.workflow import WorkflowService

        svc = WorkflowService(self.db)
        if action == "approve":
            await svc.submit_review(
                workflow_id=workflow_id, action="pass", user_id=plan.user_id
            )
            run.status = TaskRunStatus.RUNNING
            message = "已确认，任务继续执行"
        elif action == "regenerate":
            await svc.submit_review(
                workflow_id=workflow_id,
                action="reject",
                user_id=plan.user_id,
                feedback="用户在飞书卡片打回重做",
            )
            run.status = TaskRunStatus.RUNNING
            message = "已打回，正在重新生成"
        else:  # skip
            wf = await self.db.get(Workflow, workflow_id)
            if wf and wf.status == WorkflowStatus.PAUSED:
                wf.status = WorkflowStatus.TERMINATED
            item = await self.db.get(TaskItem, run.task_item_id)
            if item:
                item.status = TaskItemStatus.SKIPPED
                item.last_error = {"reason": "用户在飞书卡片选择跳过", "at": _now().isoformat()}
            run.status = TaskRunStatus.SKIPPED
            run.finished_at = _now()
            message = "已跳过本条，下一条按计划继续"

        detail = dict(run.detail or {})
        detail["confirm_action"] = action
        detail["confirmed_at"] = _now().isoformat()
        run.detail = detail

        await self._maybe_complete_plan(plan)
        await self.db.commit()
        logger.info(f"[task_plan] card action {action}: plan={plan.id} wf={workflow_id}")
        return {"success": True, "message": message}

    # ---------- 飞书通知 ----------

    async def _send_confirm_card(
        self, run: TaskRun, wf: Workflow, plan: TaskPlan, node: str, state_values: dict
    ) -> bool:
        """发飞书确认卡片（三按钮：确认发布/打回重做/跳过本条）。

        卡片回调（card.action.trigger）在 api/routers/feishu_bot.py 处理。
        未配置飞书或发送失败返回 False（调用方降级处理）。
        """
        settings = get_settings()
        if not (settings.feishu_app_id and settings.feishu_app_secret):
            return False
        open_id = (plan.plan_config or {}).get("feishu_open_id")
        if not open_id:
            return False
        try:
            from app.adapters.feishu import FeishuClient
            from app.rpa.feishu_agent_bridge import BlockKitBuilder

            node_outputs = state_values.get("node_outputs") or {}
            copy_out = node_outputs.get("copywrite") or {}
            item = await self.db.get(TaskItem, run.task_item_id)
            day_index = item.day_index if item else 0
            card = BlockKitBuilder.task_confirm_card(
                plan_title=plan.title,
                day_index=day_index,
                node=node,
                title=str(copy_out.get("title") or wf.topic)[:50],
                content_preview=str(copy_out.get("content") or "")[:150],
                value={
                    "biz": "task_plan",
                    "workflow_id": wf.id,
                    "task_item_id": run.task_item_id,
                    "plan_id": plan.id,
                },
            )
            client = FeishuClient(
                app_id=settings.feishu_app_id,
                app_secret=settings.feishu_app_secret,
            )
            await client.send_card(open_id, card, receive_id_type="open_id")
            return True
        except Exception as e:
            logger.warning(f"[task_plan] send confirm card failed: {e}")
            return False

    async def _notify_feishu_or_fallback(self, plan: TaskPlan, title: str, message: str) -> None:
        """飞书文本通知，不可达时降级站内 SSE 通知。"""
        settings = get_settings()
        open_id = (plan.plan_config or {}).get("feishu_open_id")
        if settings.feishu_app_id and settings.feishu_app_secret and open_id:
            try:
                from app.adapters.feishu import FeishuClient

                client = FeishuClient(
                    app_id=settings.feishu_app_id,
                    app_secret=settings.feishu_app_secret,
                )
                await client.send_text(open_id, f"【{title}】\n{message}", receive_id_type="open_id")
                return
            except Exception as e:
                logger.warning(f"[task_plan] feishu notify failed, fallback to SSE: {e}")
        await notification_bus.publish(
            "task_plan_event",
            {"plan_id": plan.id, "title": title, "message": message},
        )

    # ---------- 重启恢复 ----------

    async def recover_orphans(self) -> dict[str, int]:
        """服务重启后收敛 in-flight 条目（lifespan 启动时调用）。

        running 的 TaskItem：对应 workflow 已终态 → 按结果收敛；
        workflow 不存在/仍挂 → 回置 pending（retry+1，5 分钟后重扫）。
        """
        result = {"converged": 0, "requeued": 0}
        items = await self.db.scalars(
            select(TaskItem).where(TaskItem.status == TaskItemStatus.RUNNING)
        )
        for item in items:
            plan = await self.db.get(TaskPlan, item.plan_id)
            if not plan:
                continue
            if not item.workflow_id:
                item.status = TaskItemStatus.PENDING
                item.retry_count += 1
                item.plan_time = _now() + timedelta(minutes=5)
                result["requeued"] += 1
                continue
            wf = await self.db.get(Workflow, item.workflow_id)
            if not wf:
                item.status = TaskItemStatus.PENDING
                item.retry_count += 1
                item.plan_time = _now() + timedelta(minutes=5)
                result["requeued"] += 1
                continue
            status = wf.status.value if hasattr(wf.status, "value") else str(wf.status)
            if status == "completed":
                item.status = TaskItemStatus.PUBLISHED
                plan.published_days += 1
                await self._maybe_complete_plan(plan)
                result["converged"] += 1
            elif status in ("failed", "terminated", "cancelled", "suspended"):
                item.status = TaskItemStatus.FAILED
                plan.failed_days += 1
                result["converged"] += 1
            # running / paused 的留给 scan / handle_paused 处理
        await self.db.commit()
        if result["converged"] or result["requeued"]:
            logger.info(f"[task_plan] recover_orphans: {result}")
        return result

    # ---------- 序列化 ----------

    @staticmethod
    def _plan_to_dict(p: TaskPlan) -> dict[str, Any]:
        return {
            "id": p.id,
            "title": p.title,
            "intent_text": p.intent_text,
            "status": p.status.value,
            "account_id": p.account_id,
            "plan_config": p.plan_config or {},
            "total_days": p.total_days,
            "published_days": p.published_days,
            "failed_days": p.failed_days,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }

    @staticmethod
    def _item_to_dict(it: TaskItem) -> dict[str, Any]:
        return {
            "id": it.id,
            "day_index": it.day_index,
            "topic": it.topic,
            "keyword": it.keyword,
            "plan_time": it.plan_time.isoformat() if it.plan_time else None,
            "status": it.status.value,
            "retry_count": it.retry_count,
            "last_error": it.last_error,
            "workflow_id": it.workflow_id,
        }

    @staticmethod
    def _run_to_dict(r: TaskRun) -> dict[str, Any]:
        return {
            "id": r.id,
            "status": r.status.value,
            "workflow_id": r.workflow_id,
            "failure_reason": r.failure_reason,
            "detail": r.detail or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }


# 「定时发布流水线」definition id 进程内缓存
_PIPELINE_DEF_CACHE: str | None = None


# ============================================================================
# 调度 job 入口（main.py lifespan 注册，模式同 workflow_cleanup.cleanup_stale_workflows）
# ============================================================================

async def run_task_scan() -> dict[str, int]:
    """每分钟执行：到期任务扫描执行 → 运行状态收敛 → 挂起工作流处理。

    自开 session（AsyncSessionLocal），不依赖请求上下文。
    """
    result: dict[str, int] = {}
    try:
        async with AsyncSessionLocal() as db:
            svc = TaskPlanService(db)
            result.update(await svc.scan_and_execute())
            sync = await svc.sync_running_runs()
            result["sync_published"] = sync["published"]
            result["sync_failed"] = sync["failed"]
            paused = await svc.handle_paused_workflows()
            for k, v in paused.items():
                result[f"paused_{k}"] = v
    except Exception as e:
        logger.exception(f"[task_plan] scan job failed: {e}")
    if any(v for v in result.values()):
        logger.info(f"[task_plan] scan: {result}")
    return result


async def recover_on_startup() -> None:
    """lifespan 启动时收敛重启前 in-flight 的任务（不阻塞启动）。"""
    try:
        async with AsyncSessionLocal() as db:
            await TaskPlanService(db).recover_orphans()
    except Exception as e:
        logger.warning(f"[task_plan] recover_on_startup failed: {e}")
