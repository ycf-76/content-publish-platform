# Chat 驱动 Agent 系统集成需求文档 v2

> **版本**: v2.0.0
> **日期**: 2026-08-20
> **状态**: 待评审
> **优先级**: P0（核心战略功能）
> **核心原则**: 适配层叠加，不动现有基础设施

---

## 文档目录

1. [设计原则](#一设计原则)
2. [现有资产清单与维护策略](#二现有资产清单与维护策略)
3. [适配层架构](#三适配层架构)
4. [Phase 1 实施计划（2 周）](#四phase-1-实施计划2-周)
5. [Phase 2 实施计划（2 周）](#五phase-2-实施计划2-周)
6. [验收标准矩阵](#六验收标准矩阵)
7. [风险与应对](#七风险与应对)

---

## 一、设计原则

| # | 原则 | 含义 | 反例（v1 文档的教训） |
|---|------|------|----------------------|
| P1 | **适配层叠加** | 新功能以薄适配层接入现有系统，不替换、不另起炉灶 | 自创 7 种 SSE 事件替代现有 27 种 |
| P2 | **复用优先** | 能调现有 API/Service 就不新建 | 新建 `start_with_streaming()` 替代现有 `start_workflow()` + SSE 订阅 |
| P3 | **消息模型统一** | Agent 模式和 Chat 模式共享同一消息列表，仅发送端不同 | 新建 `useAgentChat` 独立维护 `messages[]` |
| P4 | **渐进增强** | Phase 1 只做最小桥接，不引入 LLM 意图解析 | Phase 1 同时上规则解析 + LLM 解析 |
| P5 | **边界先于功能** | 先定义所有边界条件（并发/审核/中断/误判），再写功能代码 | Intent Parser 无多意图/空参数处理 |

---

## 二、现有资产清单与维护策略

### 2.1 后端现有资产

| 文件 | 职责 | 维护策略 | 集成点 |
|------|------|---------|--------|
| `api/routers/chat.py` | OpenAI 兼容 Chat 端点，`POST /api/v1/chat/completions`，SSE 流式 | **不改**，保持原有纯 Chat 能力 | 新适配层路由与之并列 |
| `api/routers/workflow.py` | 工作流 REST API，`POST /api/workflows` 启动工作流 | **不改**，Agent Chat 适配层直接调用 `WorkflowService.start_workflow()` | 适配层调用入口 |
| `api/routers/sse.py` | SSE 订阅端点，`GET /api/sse/workflow/{id}`，JWT 鉴权 + Last-Event-ID 续传 | **不改**，Agent 模式复用此端点接收工作流事件 | 前端统一订阅通道 |
| `api/routers/review.py` | 人工审核 API，`POST /api/workflows/{id}/review` | **不改**，Agent 模式下审核仍走此端点 | Chat 内审核卡片调用 |
| `api/routers/rollback.py` | 回退 API | **不改** | — |
| `api/routers/recovery.py` | Recovery API | **不改** | — |
| `services/workflow.py` | `WorkflowService`：`start_workflow()` / `submit_review()` / 并发检查 / 后台 task | **不改**，适配层直接调用 `start_workflow()` | 核心调用目标 |
| `services/sse_bus.py` | `SSEEventBus` 单例：27 种事件、publish/subscribe/心跳/终态清理 | **不改**，可能新增 1-2 种事件类型（见 3.3） | 事件推送通道 |
| `agents/graph.py` | LangGraph 编排层，`build_workflow_graph()` 9 节点硬编码 DAG | **不改** | — |
| `agents/core/harness/runtime.py` | `AgentHarness.run()`：前置规则 → executor → 后置规则 → AgentOutput | **不改** | — |
| `agents/nodes/` | 9 个业务节点实现 | **不改** | — |
| `api/schemas/workflow.py` | `StartWorkflowRequest` / `WorkflowResponse` 等 Pydantic schema | **小改**：新增可选字段 `source: str = "gui"` 标记来源 | 区分 GUI 发起 vs Chat 发起 |
| `main.py` | `app.include_router()` 注册 19 个路由 | **小改**：新增 1 行 `include_router(chat_agent.router)` | 路由注册 |

### 2.2 前端现有资产

| 文件 | 职责 | 维护策略 | 集成点 |
|------|------|---------|--------|
| `components/chat/ChatView.vue` | Chat 主界面：消息渲染、流式、打字机、ExecCell/PlanCell/DiffCell/ThinkingCell、Hero、输入卡 | **小改**：增加模式切换 + 条件渲染适配组件 | 模式入口 |
| `components/chat/cell-types.ts` | `ChatMessage` / `Conversation` / `ToolCall` / `PlanStep` 类型定义 | **小改**：扩展 `ChatMessage` 增加可选 Agent 字段 | 类型扩展 |
| `composables/useChatHistory.ts` | 会话历史管理 | **不改** | — |
| `composables/useTypewriter.ts` | 打字机效果 | **不改** | — |
| `composables/useNotifications.ts` | 通知 | **不改** | — |

### 2.3 现有通信协议（不动）

前后端通信协议定义的 **27 种 SSE 事件**、`SSEEvent<T>` 统一信封、断线续传、心跳机制**全部复用**，不另定义。

Agent 适配层仅新增 **2 种事件类型**（见 3.3），注册到现有 `sse_bus`。

---

## 三、适配层架构

### 3.1 核心思路

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (ChatView.vue)                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  现有 Chat 消息流（ChatMessage[]）                    │    │
│  │  + Agent 适配渲染（WorkflowProgressCard / ReviewCard）│    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                   │
│            ┌────────────┴────────────┐                      │
│            │   模式切换（Chat/Agent）  │ ← 唯一新增 UI       │
│            └────────────┬────────────┘                      │
│                         │                                   │
│       Chat 模式         │         Agent 模式                │
│       ↓                 │         ↓                         │
│  POST /api/v1/chat/     │   POST /api/v1/chat/agent        │
│  completions            │   (适配层新端点)                   │
│                         │         │                         │
│                         │         ↓ 返回 {workflow_id}      │
│                         │         │                         │
│                         │   GET /api/sse/workflow/{id}      │
│                         │   (现有 SSE 订阅，不改)            │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│                                                             │
│  ┌──────────────────────┐                                  │
│  │ chat_agent.py (新建)  │ ← 适配层：意图解析 → 调用现有服务  │
│  │                      │                                  │
│  │  1. IntentParser     │ ← 规则匹配（Phase 1）             │
│  │  2. 调用 WorkflowService.start_workflow()               │
│  │  3. 返回 {workflow_id}                                 │
│  └──────────┬───────────┘                                  │
│             │ 调用                                          │
│             ▼                                               │
│  ┌──────────────────────┐  ┌────────────────────────────┐  │
│  │ WorkflowService      │  │ SSEEventBus                │  │
│  │ (现有，不改)         │  │ (现有，可能+2 事件类型)     │  │
│  └──────────────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**关键设计决策**：

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent Chat 端点返回什么 | `{workflow_id, intent}` | 不自己 yield SSE，复用现有 SSE 订阅 |
| 前端如何接收工作流进度 | 复用 `GET /api/sse/workflow/{id}` | 27 种事件 + 断线续传 + 心跳全部复用 |
| 消息模型 | 扩展现有 `ChatMessage` | 不新建独立消息数组 |
| 意图解析 | Phase 1 规则匹配 | 零 LLM 成本，< 10ms，Phase 2 升级 LLM |
| 人工审核 | 复用现有 `POST /api/workflows/{id}/review` | Chat 内渲染审核卡片，操作走现有 API |

### 3.2 适配层数据流

```
用户输入: "帮我写一篇关于 AI 教育的小红书文章"
  │
  ▼
[ChatView.vue] sendMessage()
  │
  ├─ isAgentMode === false → 走现有 /api/v1/chat/completions（不改）
  │
  └─ isAgentMode === true
       │
       ▼
  [1] POST /api/v1/chat/agent
      Request: { message, mode: "auto", account_id? }
      │
      ▼ 后端适配层
  [2] IntentParser.parse(message)
      → ParsedIntent { action: "full_pipeline", params: { topic: "AI 教育" }, confidence: 0.85 }
      │
      ▼
  [3] WorkflowService.start_workflow(
        user_id, account_id, topic="AI 教育",
        search_keyword=None, creative_brief="",
        model_settings={}, reference={}
      )
      → Workflow { id: "wf_xxx", status: "running" }
      │
      ▼
  [4] sse_bus.publish("intent_parsed", { intent, workflow_id })
      │
      ▼
  [5] Response: { workflow_id: "wf_xxx", intent: { action: "full_pipeline", topic: "AI 教育" } }
      │
      ▼ 前端收到响应
  [6] 在 ChatMessage 中记录 workflow_id
      │
      ▼
  [7] 前端调用现有 SSE 订阅: GET /api/sse/workflow/wf_xxx
      → 接收 27 种现有事件 + intent_parsed 事件
      │
      ▼ 事件驱动渲染
  [8] node_status_changed → 更新 WorkflowProgressCard
      review_required     → 渲染 ReviewCard
      workflow_completed  → 渲染最终结果
      stream_chunk        → 逐字渲染文案
      tool_call_start/end → 渲染 ExecCell
```

### 3.3 新增 SSE 事件类型（仅 2 种，注册到现有 sse_bus）

| 事件类型 | 触发时机 | payload | 优先级 |
|---------|---------|---------|--------|
| `intent_parsed` | IntentParser 解析完成后 | `{ action, params, confidence, workflow_id }` | 中 |
| `agent_chat_error` | Agent Chat 适配层出错（意图解析失败/参数缺失/并发超限） | `{ error_code, message, recoverable }` | 高 |

其余全部复用现有 27 种事件。

### 3.4 ChatMessage 类型扩展

```typescript
// 在现有 cell-types.ts 的 ChatMessage 接口中增加可选字段
export interface ChatMessage {
  // === 现有字段（不动） ===
  role: 'user' | 'assistant' | 'system'
  content: string
  thinking?: string
  isError?: boolean
  cellType?: CellType
  toolCalls?: ToolCall[]
  planSteps?: PlanStep[]
  planExplanation?: string
  diffFile?: string
  diffContent?: string
  diffAddCount?: number
  diffDelCount?: number

  // === Agent 适配层新增字段（全部可选，不影响现有 Chat 模式） ===
  agentMeta?: {
    workflowId: string | null
    intent?: {
      action: string
      params: Record<string, any>
      confidence: number
    }
    workflowStatus?: 'running' | 'awaiting_review' | 'suspended' | 'completed' | 'error'
    currentStep?: string
    steps?: Array<{
      nodeKey: string
      nodeLabel: string
      status: 'pending' | 'running' | 'completed' | 'error' | 'awaiting_review'
      percent: number
    }>
    totalPercent?: number
  }
}
```

---

## 四、Phase 1 实施计划（2 周）

**目标**: 用户在 Chat 中切换 Agent 模式 → 输入自然语言 → 触发完整工作流 → 看到实时进度 → 完成发布

**范围约束**:
- 仅支持 `full_pipeline` 和 `chat` 两种意图（砍掉单步执行，降低复杂度）
- Agent 模式下图片审核自动通过（仅保留终审）
- 不引入 LLM 意图解析

---

### Week 1: 后端适配层

#### Task 1.1: 新建 Intent Parser

**文件**: `backend/app/agents/intent_parser.py`（新建）

```python
"""
Intent Parser v1 — 基于规则的意图解析器

边界条件处理：
- 多规则命中：按优先级排序（full_pipeline > chat）
- 参数缺失：topic 从消息中提取，失败则要求用户补充
- URL 输入：识别小红书链接 → analyze_only（Phase 2）
- confidence < 0.7：标记 needs_confirmation
- 空消息/纯表情：兜底 chat
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re


class ActionType(str, Enum):
    FULL_PIPELINE = "full_pipeline"
    CHAT = "chat"


@dataclass
class ParsedIntent:
    action: ActionType
    params: dict = field(default_factory=dict)
    confidence: float = 0.0
    needs_confirmation: bool = False
    confirmation_prompt: str = ""


# 规则定义：按优先级从高到低
INTENT_RULES = [
    {
        "patterns": [
            r"写.*(?:文章|笔记|内容|帖子)",
            r"发布.*(?:小红书|笔记)",
            r"帮我(?:做|写|生成|创作)",
            r"来一篇",
            r"制作.*(?:内容|笔记)",
        ],
        "action": ActionType.FULL_PIPELINE,
        "confidence": 0.85,
    },
]


class RuleBasedIntentParser:

    async def parse(self, message: str) -> ParsedIntent:
        if not message or not message.strip():
            return ParsedIntent(action=ActionType.CHAT, confidence=0.5)

        for rule in INTENT_RULES:
            for pattern in rule["patterns"]:
                if re.search(pattern, message):
                    params = self._extract_params(message)
                    confidence = rule["confidence"]
                    needs_confirmation = confidence < 0.7
                    return ParsedIntent(
                        action=rule["action"],
                        params=params,
                        confidence=confidence,
                        needs_confirmation=needs_confirmation,
                        confirmation_prompt="确认：要执行完整发布流程吗？" if needs_confirmation else "",
                    )

        return ParsedIntent(action=ActionType.CHAT, confidence=0.6)

    def _extract_params(self, message: str) -> dict:
        """从消息中提取 topic。

        策略：
        1. 匹配 "关于 X 的" / "X 相关" / "X 方面" 模式
        2. 去掉指令词后取剩余文本
        3. 都失败则返回整个消息作为 topic
        """
        patterns = [
            r"(?:关于|有关)(.+?)(?:的|文章|笔记|内容|帖子)",
            r"写(?:一篇|个)?(.+?)(?:的|文章|笔记|内容|帖子|$)",
            r"帮我(?:写|做|生成|创作)(?:一篇|个)?(.+?)(?:的|文章|笔记|内容|帖子|$)",
        ]
        for p in patterns:
            m = re.search(p, message)
            if m:
                topic = m.group(1).strip()
                if topic:
                    return {"topic": topic}

        # fallback：去掉常见指令词
        cleaned = re.sub(r"^(帮我|请|能不能|可以|写|发布|制作|来一篇)", "", message).strip()
        topic = cleaned if cleaned else message
        return {"topic": topic}
```

**验收标准**:
- [ ] "帮我写一篇关于 AI 教育的小红书文章" → `{action: full_pipeline, params: {topic: "AI 教育"}}`
- [ ] "写一篇美食探店笔记" → `{action: full_pipeline, params: {topic: "美食探店"}}`
- [ ] "今天天气怎么样" → `{action: chat, confidence: 0.6}`
- [ ] "" → `{action: chat}`
- [ ] topic 参数永不为空字符串

---

#### Task 1.2: 新建 Agent Chat 适配层端点

**文件**: `backend/app/api/routers/chat_agent.py`（新建）

```python
"""
Agent Chat 适配层 — 连接 Chat 入口与现有 WorkflowService

核心原则：
- 不自己 yield SSE，复用现有 SSE 订阅端点
- 调用现有 WorkflowService.start_workflow()
- 返回 workflow_id，前端自行订阅
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.intent_parser import RuleBasedIntentParser, ActionType
from app.api.deps import get_current_user
from app.db.session import get_db
from app.services.workflow import get_workflow_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat_agent"])

_intent_parser = RuleBasedIntentParser()


class AgentChatRequest(BaseModel):
    message: str = Field(..., max_length=10000)
    mode: str = Field(default="auto", pattern="^(auto|full_pipeline|chat)$")
    account_id: str | None = None
    model_settings: dict = Field(default_factory=dict)


class AgentChatResponse(BaseModel):
    workflow_id: str | None = None
    intent: dict
    needs_confirmation: bool = False
    confirmation_prompt: str = ""
    fallback_reason: str | None = None


@router.post("/agent")
async def agent_chat(
    request: AgentChatRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentChatResponse:
    """
    Agent Chat 入口：解析意图 → 启动工作流 → 返回 workflow_id

    前端收到 workflow_id 后，自行调用 GET /api/sse/workflow/{id} 订阅事件。
    """

    # 1. 解析意图
    intent = await _intent_parser.parse(request.message)

    # 2. mode 覆盖
    if request.mode == "full_pipeline":
        intent.action = ActionType.FULL_PIPELINE
    elif request.mode == "chat":
        intent.action = ActionType.CHAT

    # 3. 纯闲聊 → 不启动工作流
    if intent.action == ActionType.CHAT:
        return AgentChatResponse(
            intent={"action": "chat", "params": {}, "confidence": intent.confidence},
            fallback_reason="未识别到工作流意图，已切换到普通对话",
        )

    # 4. 需要确认 → 不启动，返回确认提示
    if intent.needs_confirmation:
        return AgentChatResponse(
            intent={"action": intent.action.value, "params": intent.params, "confidence": intent.confidence},
            needs_confirmation=True,
            confirmation_prompt=intent.confirmation_prompt,
        )

    # 5. 参数校验
    topic = intent.params.get("topic", "").strip()
    if not topic:
        return AgentChatResponse(
            intent={"action": intent.action.value, "params": intent.params, "confidence": intent.confidence},
            needs_confirmation=True,
            confirmation_prompt="请告诉我你想写什么主题的内容？",
        )

    # 6. 启动工作流（调用现有 WorkflowService）
    try:
        service = get_workflow_service(db)
        account_id = request.account_id or ""

        workflow = await service.start_workflow(
            user_id=user_id,
            account_id=account_id,
            topic=topic,
            search_keyword=None,
            creative_brief="",
            model_settings=request.model_settings,
        )

        logger.info(f"[agent_chat] workflow started: {workflow.id}, topic={topic}")

        return AgentChatResponse(
            workflow_id=workflow.id,
            intent={"action": intent.action.value, "params": intent.params, "confidence": intent.confidence},
        )

    except HTTPException as e:
        # 并发超限 (429) 等业务异常，透传
        raise
    except Exception as e:
        logger.error(f"[agent_chat] start_workflow failed: {e}")
        raise HTTPException(status_code=500, detail=f"启动工作流失败: {e}")
```

**验收标准**:
- [ ] `POST /api/v1/chat/agent` 返回 `AgentChatResponse`
- [ ] 意图为 chat 时 `workflow_id = null`
- [ ] 意图为 full_pipeline 时 `workflow_id` 非空
- [ ] 并发超限时返回 429（由 WorkflowService._check_concurrency_limit 抛出）
- [ ] 未登录时返回 401（由 get_current_user 抛出）

---

#### Task 1.3: 注册新路由

**文件**: `backend/app/main.py`（修改，1 行）

在现有 `include_router` 列表末尾新增：

```python
from app.api.routers import chat_agent
app.include_router(chat_agent.router)  # Agent Chat adapter (v7.0)
```

**验收标准**:
- [ ] `/api/v1/chat/agent` 端点可访问
- [ ] 不影响现有 19 个路由

---

#### Task 1.4: SSE 事件类型扩展

**文件**: `backend/app/services/sse_bus.py`（修改，仅扩展 `_TERMINAL_TYPES`）

在现有 `_TERMINAL_TYPES` 无需改动（`intent_parsed` 和 `agent_chat_error` 都不是终态事件）。新增事件类型通过 `sse_bus.publish()` 的 `event_type` 参数直接使用，无需注册。

**验收标准**:
- [ ] `sse_bus.publish(workflow_id, "intent_parsed", {...})` 正常工作
- [ ] 现有 27 种事件不受影响

---

#### Task 1.5: StartWorkflowRequest 增加 source 字段

**文件**: `backend/app/api/schemas/workflow.py`（修改，1 行）

```python
class StartWorkflowRequest(BaseModel):
    # ... 现有字段不动 ...
    source: str = Field(default="gui", description="发起来源: gui | chat_agent")
```

**文件**: `backend/app/services/workflow.py`（修改，`start_workflow` 签名增加 `source` 参数）

```python
async def start_workflow(
    self,
    # ... 现有参数不动 ...
    source: str = "gui",
) -> Workflow:
```

用于区分工作流来源，方便后续统计和日志排查。

**验收标准**:
- [ ] GUI 发起的工作流 `source = "gui"`（默认值，向后兼容）
- [ ] Agent Chat 发起的 `source = "chat_agent"`

---

### Week 2: 前端适配层

#### Task 1.6: 扩展 ChatMessage 类型

**文件**: `frontend/src/components/chat/cell-types.ts`（修改）

在 `ChatMessage` 接口中增加可选 `agentMeta` 字段（见 3.4 定义）。

**验收标准**:
- [ ] 现有 Chat 消息（无 `agentMeta`）正常渲染
- [ ] Agent 消息（有 `agentMeta`）不报 TypeScript 错误

---

#### Task 1.7: 新建 WorkflowProgressCard 组件

**文件**: `frontend/src/components/chat/WorkflowProgressCard.vue`（新建）

此组件作为 **ChatMessage 的一种内联渲染形态**，不是独立页面组件。

```vue
<!--
  WorkflowProgressCard — 在 Chat 消息流中内联渲染工作流进度

  渲染时机：当 ChatMessage.agentMeta.workflowId 非空时，
  在 assistant 消息气泡内渲染此卡片。

  数据来源：通过 SSE 订阅 /api/sse/workflow/{id} 获取的
  node_status_changed / node_completed 事件驱动更新。
-->
<template>
  <div class="wfp-card">
    <!-- 意图标签 -->
    <div class="wfp-intent">
      <span class="wfp-intent-badge">{{ intentLabel }}</span>
      <span class="wfp-topic">{{ topic }}</span>
    </div>

    <!-- 进度条 -->
    <div class="wfp-bar-track">
      <div class="wfp-bar-fill" :style="{ width: `${totalPercent}%` }"></div>
    </div>

    <!-- 步骤列表 -->
    <div class="wfp-steps">
      <div
        v-for="step in steps"
        :key="step.nodeKey"
        class="wfp-step"
        :class="[`wfp-step-${step.status}`]"
      >
        <span class="wfp-step-icon">
          <template v-if="step.status === 'completed'">✓</template>
          <template v-else-if="step.status === 'running'">◉</template>
          <template v-else-if="step.status === 'awaiting_review'">⏸</template>
          <template v-else-if="step.status === 'error'">✗</template>
          <template v-else>○</template>
        </span>
        <span class="wfp-step-name">{{ step.nodeLabel }}</span>
      </div>
    </div>

    <!-- 当前步骤 -->
    <div class="wfp-current" v-if="currentStep">
      正在执行: {{ currentStep }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  intent: { action: string; params: Record<string, any> }
  steps: Array<{
    nodeKey: string
    nodeLabel: string
    status: string
    percent: number
  }>
  totalPercent: number
  currentStep: string
}>()

const NODE_LABELS: Record<string, string> = {
  search: '搜索爆款',
  analyze: '要素分析',
  image_plan: '图片规划',
  image_gen: '图片生成',
  image_review: '图片审核',
  copywrite: '文案撰写',
  audit: '合规审核',
  final_review: '人工终审',
  publish: '发布',
}

const intentLabel = computed(() => {
  if (props.intent.action === 'full_pipeline') return '完整发布流程'
  return props.intent.action
})

const topic = computed(() => props.intent.params?.topic || '')
</script>
```

**验收标准**:
- [ ] 组件接收 props 正确渲染
- [ ] 进度条宽度随 `totalPercent` 动态变化
- [ ] 步骤列表显示 9 个节点名称和状态图标
- [ ] running 状态步骤有脉动动画

---

#### Task 1.8: 新建 ReviewCard 组件

**文件**: `frontend/src/components/chat/ReviewCard.vue`（新建）

```vue
<!--
  ReviewCard — 在 Chat 消息流中内联渲染人工审核卡片

  当工作流进入 awaiting_review 状态时渲染。
  操作按钮调用现有 POST /api/workflows/{id}/review 端点。
-->
<template>
  <div class="wrc-card">
    <div class="wrc-header">
      <span class="wrc-badge">待审核</span>
      <span class="wrc-type">{{ reviewType === 'image' ? '图片审核' : '发布终审' }}</span>
    </div>

    <!-- 图片审核：缩略图列表 -->
    <div v-if="reviewType === 'image'" class="wrc-images">
      <img v-for="(url, i) in images" :key="i" :src="url" class="wrc-thumb" @click="previewImage(url)" />
    </div>

    <!-- 终审：内容预览 -->
    <div v-if="reviewType === 'final'" class="wrc-preview">
      <h4 class="wrc-title">{{ content?.title }}</h4>
      <p class="wrc-body">{{ content?.body?.slice(0, 200) }}...</p>
    </div>

    <!-- 操作按钮 -->
    <div class="wrc-actions">
      <button class="wrc-btn wrc-btn-pass" @click="submitReview('pass')">
        {{ reviewType === 'image' ? '图片可以' : '通过并发布' }}
      </button>
      <button class="wrc-btn wrc-btn-reject" @click="submitReview('reject')">
        {{ reviewType === 'image' ? '重新生成' : '打回修改' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  workflowId: string
  reviewType: 'image' | 'final'
  images?: string[]
  content?: { title: string; body: string; tags: string[] }
}>()

const emit = defineEmits<{
  reviewed: [action: string]
}>()

async function submitReview(action: 'pass' | 'reject') {
  const token = localStorage.getItem('token')
  await fetch(`/api/workflows/${props.workflowId}/review`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ action, feedback: '' }),
  })
  emit('reviewed', action)
}

function previewImage(url: string) {
  window.open(url, '_blank')
}
</script>
```

**验收标准**:
- [ ] 点击"通过"调用 `POST /api/workflows/{id}/review` action=pass
- [ ] 点击"打回"调用 action=reject
- [ ] 审核后卡片状态变为已处理

---

#### Task 1.9: 修改 ChatView.vue — 模式切换 + Agent 发送 + SSE 订阅

**文件**: `frontend/src/components/chat/ChatView.vue`（修改）

**改动点 1: 新增状态变量**

```typescript
// 在 script setup 中新增
const isAgentMode = ref(false)
const activeWorkflowId = ref<string | null>(null)
const workflowSseController = ref<AbortController | null>(null)
```

**改动点 2: 模式切换按钮（在 header 区域）**

```vue
<header class="dsh-header dsh-header-minimal" v-show="!heroMode">
  <div class="dsh-header-cluster">
    <!-- 新增：模式切换 -->
    <button
      class="dsh-mode-toggle"
      :class="{ 'dsh-mode-active': isAgentMode }"
      @click="isAgentMode = !isAgentMode"
      :title="isAgentMode ? '切换到 Chat 模式' : '切换到 Agent 模式'"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
      <span>{{ isAgentMode ? 'Agent' : 'Chat' }}</span>
    </button>
  </div>
</header>
```

**改动点 3: Agent 模式消息发送**

修改 `sendMessage()` 函数，在 `isAgentMode` 为 true 时走 Agent 通道：

```typescript
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  // ... 现有会话创建逻辑不变 ...

  if (isAgentMode.value) {
    await sendAgentMessage(conv, text)
  } else {
    await sendMessageReal(conv, Date.now())
  }

  // ... 现有 finally 清理逻辑不变 ...
}

async function sendAgentMessage(conv: Conversation, text: string) {
  // 1. 添加用户消息
  conv.messages.push({ role: 'user', content: text })

  // 2. 创建 assistant 占位消息（含 agentMeta）
  const assistantMsg: ChatMessage = {
    role: 'assistant',
    content: '',
    agentMeta: {
      workflowId: null,
      intent: undefined,
      steps: [],
      totalPercent: 0,
      workflowStatus: 'running',
    },
  }
  conv.messages.push(assistantMsg)

  isStreaming.value = true
  startClock()

  try {
    // 3. 调用 Agent Chat 端点
    const token = localStorage.getItem('token')
    const response = await fetch('/api/v1/chat/agent', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message: text,
        mode: 'auto',
        account_id: authStore.accountId || undefined,
      }),
    })

    if (!response.ok) {
      const err = await response.text()
      throw new Error(err || `HTTP ${response.status}`)
    }

    const data = await response.json()

    // 4. 需要确认
    if (data.needs_confirmation) {
      assistantMsg.content = data.confirmation_prompt
      assistantMsg.agentMeta!.workflowStatus = 'error'
      return
    }

    // 5. 纯闲聊
    if (!data.workflow_id) {
      assistantMsg.content = data.fallback_reason || '未识别到工作流意图'
      assistantMsg.agentMeta!.workflowStatus = 'error'
      return
    }

    // 6. 工作流已启动 → 记录 workflow_id，开始 SSE 订阅
    assistantMsg.agentMeta!.workflowId = data.workflow_id
    assistantMsg.agentMeta!.intent = data.intent
    activeWorkflowId.value = data.workflow_id

    // 7. 订阅工作流 SSE（复用现有端点）
    await subscribeWorkflowSSE(data.workflow_id, assistantMsg, conv)

  } catch (err: any) {
    assistantMsg.content = `Agent 执行失败: ${err.message || '未知错误'}`
    assistantMsg.isError = true
    assistantMsg.agentMeta!.workflowStatus = 'error'
  }
}
```

**改动点 4: SSE 订阅工作流事件**

```typescript
async function subscribeWorkflowSSE(
  workflowId: string,
  assistantMsg: ChatMessage,
  conv: Conversation,
) {
  const controller = new AbortController()
  workflowSseController.value = controller

  const token = localStorage.getItem('token')
  const response = await fetch(`/api/sse/workflow/${workflowId}`, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal: controller.signal,
  })

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()

  const NODE_LABELS: Record<string, string> = {
    search: '搜索爆款', analyze: '要素分析', image_plan: '图片规划',
    image_gen: '图片生成', image_review: '图片审核', copywrite: '文案撰写',
    audit: '合规审核', final_review: '人工终审', publish: '发布',
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const text = decoder.decode(value, { stream: true })
      const lines = text.split('\n').filter(l => l.startsWith('data: '))

      for (const line of lines) {
        const jsonStr = line.slice(6)
        if (!jsonStr.trim()) continue

        try {
          const event = JSON.parse(jsonStr)
          handleWorkflowEvent(event, assistantMsg, conv, NODE_LABELS)
        } catch {
          // 忽略非 JSON 行（心跳等）
        }
      }
    }
  } finally {
    workflowSseController.value = null
  }
}

function handleWorkflowEvent(
  event: any,
  assistantMsg: ChatMessage,
  conv: Conversation,
  nodeLabels: Record<string, string>,
) {
  const eventType = event.event_type
  const payload = event.payload || event

  switch (eventType) {
    case 'node_status_changed': {
      const nodeKey = payload.node_id || payload.node_type
      const newStatus = payload.new_status
      const meta = assistantMsg.agentMeta!
      const step = meta.steps!.find(s => s.nodeKey === nodeKey)
      if (step) {
        step.status = newStatus
      } else {
        meta.steps!.push({
          nodeKey,
          nodeLabel: nodeLabels[nodeKey] || nodeKey,
          status: newStatus,
          percent: newStatus === 'completed' ? 100 : 0,
        })
      }
      meta.currentStep = newStatus === 'running' ? nodeLabels[nodeKey] || nodeKey : ''
      const completed = meta.steps!.filter(s => s.status === 'completed').length
      meta.totalPercent = Math.round((completed / 9) * 100)
      break
    }

    case 'node_completed': {
      const nodeKey = payload.node_id || payload.node_type
      const meta = assistantMsg.agentMeta!
      const step = meta.steps!.find(s => s.nodeKey === nodeKey)
      if (step) step.status = 'completed'
      const completed = meta.steps!.filter(s => s.status === 'completed').length
      meta.totalPercent = Math.round((completed / 9) * 100)
      break
    }

    case 'review_required': {
      // 在消息流中插入 ReviewCard
      assistantMsg.agentMeta!.workflowStatus = 'awaiting_review'
      break
    }

    case 'workflow_completed': {
      assistantMsg.agentMeta!.workflowStatus = 'completed'
      assistantMsg.agentMeta!.totalPercent = 100
      assistantMsg.content = `✅ 工作流完成！${payload.post_url ? `[查看笔记](${payload.post_url})` : ''}`
      isStreaming.value = false
      stopClock()
      stopTypewriter()
      break
    }

    case 'workflow_error': {
      assistantMsg.agentMeta!.workflowStatus = 'error'
      assistantMsg.content = `❌ 工作流出错: ${payload.error_message || '未知错误'}`
      assistantMsg.isError = true
      isStreaming.value = false
      stopClock()
      stopTypewriter()
      break
    }

    case 'stream_chunk': {
      // 文案逐字流式
      assistantMsg.content += payload.chunk || ''
      break
    }

    case 'tool_call_start': {
      // 复用现有 ExecCell 渲染
      if (!assistantMsg.toolCalls) assistantMsg.toolCalls = []
      assistantMsg.toolCalls.push({
        id: `tc_${Date.now()}`,
        type: 'exec',
        name: payload.tool_name || 'tool',
        arguments: payload.tool_input || {},
      })
      break
    }

    case 'tool_call_end': {
      if (assistantMsg.toolCalls && assistantMsg.toolCalls.length > 0) {
        const last = assistantMsg.toolCalls[assistantMsg.toolCalls.length - 1]
        last.result = JSON.stringify(payload.tool_output || {}, null, 2)
        last.durationMs = payload.duration_ms
      }
      break
    }

    case 'intent_parsed': {
      // 意图解析结果（可选展示）
      break
    }
  }
}
```

**改动点 5: 条件渲染 WorkflowProgressCard 和 ReviewCard**

在 assistant 消息区域，`agentMeta` 存在时渲染适配组件：

```vue
<!-- 在 AssistantCell 内，Markdown 内容之前 -->
<WorkflowProgressCard
  v-if="msg.agentMeta && msg.agentMeta.workflowId"
  :intent="msg.agentMeta.intent || { action: 'unknown', params: {} }"
  :steps="msg.agentMeta.steps || []"
  :total-percent="msg.agentMeta.totalPercent || 0"
  :current-step="msg.agentMeta.currentStep || ''"
/>

<ReviewCard
  v-if="msg.agentMeta && msg.agentMeta.workflowStatus === 'awaiting_review'"
  :workflow-id="msg.agentMeta.workflowId!"
  :review-type="msg.agentMeta.currentStep === '图片审核' ? 'image' : 'final'"
  @reviewed="onReviewed"
/>
```

**改动点 6: ESC 中断工作流**

```typescript
function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    // 优先中断 Agent SSE
    if (workflowSseController.value) {
      workflowSseController.value.abort()
      workflowSseController.value = null
      isStreaming.value = false
      stopClock()
      stopTypewriter()
      return
    }
    // 原有 Chat 中断
    if (isStreaming.value && abortController) {
      abortController.abort()
      return
    }
  }
  // ... 现有 Enter 逻辑不变 ...
}
```

**验收标准**:
- [ ] 页面显示模式切换按钮（Chat / Agent）
- [ ] Chat 模式下行为完全不变
- [ ] Agent 模式下发送消息 → 调用 `/api/v1/chat/agent`
- [ ] 收到 workflow_id → 自动订阅 SSE → 进度实时更新
- [ ] WorkflowProgressCard 渲染在消息流中
- [ ] 审核节点 → ReviewCard 渲染 → 点击通过调用现有 review API
- [ ] ESC 中断 SSE 订阅
- [ ] 工作流完成 → 显示结果链接

---

## 五、Phase 2 实施计划（2 周）

**目标**: 从"能用"到"好用" — 多轮对话 + LLM 意图解析 + 单步执行

### Task 2.1: LLM Intent Parser（升级替换）

**文件**: `backend/app/agents/intent_parser.py`（修改）

新增 `LLMIntentParser` 类，与 `RuleBasedIntentParser` 实现同一接口 `IntentParserProtocol`。

策略：**规则优先 + LLM 兜底**
1. 规则匹配 confidence > 0.8 → 直接返回
2. 规则匹配 confidence < 0.8 → 调用 LLM 二次解析
3. LLM 解析失败 → 降级回规则结果

**验收标准**:
- [ ] 意图解析准确率 > 95%（50 条测试用例）
- [ ] LLM 调用失败时降级到规则解析
- [ ] 解析延迟 < 500ms（规则 < 10ms，LLM < 500ms）

### Task 2.2: 多轮对话上下文

**文件**: `frontend/src/components/chat/ChatView.vue`（修改）

Agent 模式下维护 conversation history，支持追问：
- "换个风格" → 修改 model_settings.writing_style → 重新启动工作流
- "图片不要了" → 设置 with_images=false → 重新启动

**验收标准**:
- [ ] 追问能关联到上一个工作流的上下文
- [ ] 修改参数后重新启动工作流

### Task 2.3: 单步执行支持

**文件**: `backend/app/agents/intent_parser.py`（修改，增加 `SEARCH_ONLY` / `ANALYZE_ONLY` 等 ActionType）

**文件**: `backend/app/api/routers/chat_agent.py`（修改，单步执行时构建子图或条件入口）

**验收标准**:
- [ ] "搜一下 AI 教育的热点" → 仅执行 search 节点
- [ ] 单步结果在 Chat 中渲染

### Task 2.4: 输入安全防护

**文件**: `backend/app/agents/intent_parser.py`（修改，增加输入清洗层）

```python
def sanitize_input(message: str) -> str:
    """清洗 prompt injection 常见模式"""
    patterns = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now",
        r"system\s*:",
        r"<\|im_start\|>",
    ]
    cleaned = message
    for p in patterns:
        cleaned = re.sub(p, "[filtered]", cleaned, flags=re.IGNORECASE)
    return cleaned
```

**验收标准**:
- [ ] 常见 prompt injection 模式被过滤
- [ ] 正常中文输入不受影响

---

## 六、验收标准矩阵

### 6.1 Phase 1 功能验收

| ID | 验收项 | 验证方法 | 优先级 |
|----|--------|---------|--------|
| F-01 | 模式切换按钮可见且可切换 | UI 截图 | P0 |
| F-02 | Chat 模式行为完全不变 | 回归测试 | P0 |
| F-03 | Agent 模式发送消息 → 后端日志出现 `workflow started` | 日志检查 | P0 |
| F-04 | 返回 workflow_id → 前端自动订阅 SSE | Network 面板 | P0 |
| F-05 | WorkflowProgressCard 渲染 9 个步骤 | 视觉检查 | P0 |
| F-06 | 进度条实时更新（< 1s 延迟） | 录屏对比后端日志 | P0 |
| F-07 | 工作流完成 → 显示结果 | 端到端测试 | P0 |
| F-08 | 工作流出错 → 显示错误 + 重试 | 故障注入 | P0 |
| F-09 | 并发超限 → 429 + 友好提示 | 连续发送 2 条 | P0 |
| F-10 | 未登录 → 401 | 无 token 请求 | P0 |
| F-11 | 意图未识别 → 提示切换到 Chat | 输入"今天天气" | P1 |
| F-12 | ReviewCard 审核操作 | 点击通过/打回 | P1 |
| F-13 | ESC 中断 SSE 订阅 | 快捷键测试 | P1 |
| F-14 | topic 参数永不为空 | 边界测试 | P1 |
| F-15 | 消息 < 10000 字符限制 | 超长输入测试 | P2 |

### 6.2 Phase 1 性能验收

| ID | 指标 | 目标值 | 测试方法 |
|----|------|--------|---------|
| P-01 | 意图解析延迟（规则版） | < 10ms | 计时 |
| P-02 | Agent Chat 端点响应 | < 200ms（到返回 workflow_id） | curl 计时 |
| P-03 | SSE 事件到达延迟 | < 500ms | 端到端计时 |
| P-04 | 进度条帧率 | ≥ 30fps | Performance API |

### 6.3 Phase 1 安全验收

| ID | 检查项 | 要求 | 验证方式 |
|----|--------|------|---------|
| S-01 | JWT 鉴权 | 未登录不能触发工作流 | 无 token 请求 |
| S-02 | 工作流归属校验 | 不能订阅他人工作流 SSE | 伪造 workflow_id |
| S-03 | 输入长度限制 | 单条消息 ≤ 10000 字符 | 超长输入 |
| S-04 | 并发限制 | 复用现有 MAX_CONCURRENT_WORKFLOWS | 连续启动 |

### 6.4 Phase 1 兼容性验收

| ID | 环境 | 要求 |
|----|------|------|
| C-01 | Chrome 90+ | 正常运行 |
| C-02 | 现有 GUI 工作流页面 | 不受影响 |

### 6.5 Phase 2 验收

| ID | 验收项 | 目标值 |
|----|--------|--------|
| F-21 | LLM 意图解析准确率 | > 95% |
| F-22 | LLM 解析降级到规则 | 失败时无报错 |
| F-23 | 多轮追问关联上下文 | "换个风格" 能修改参数 |
| F-24 | 单步执行 | "搜一下" 仅执行 search |
| F-25 | Prompt injection 过滤 | 常见模式被拦截 |

---

## 七、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Intent Parser 误判 | 中 | 中 | Phase 1 规则版 + needs_confirmation 机制；Phase 2 LLM 升级 |
| SSE 订阅中断 | 中 | 中 | 现有 sse_bus 已实现 Last-Event-ID 续传 + 心跳，无需额外处理 |
| 工作流并发超限 | 低 | 中 | 复用现有 _check_concurrency_limit，429 + 前端友好提示 |
| 人工审核在 Chat 中体验差 | 中 | 中 | Phase 1 图片审核自动通过；终审渲染 ReviewCard |
| 前端状态管理复杂度 | 低 | 低 | agentMeta 全部在 ChatMessage 内，不引入独立 store |

### 应急预案

**Scenario A: Agent Chat 端点 5xx**
```
前端 catch → assistantMsg.isError = true → 显示"Agent 服务暂时不可用"
→ 用户可切回 Chat 模式继续使用
```

**Scenario B: 工作流卡死**
```
现有 30 分钟超时挂起机制生效 → workflow_suspended 事件 → 前端显示"工作流已挂起"
→ 用户可手动恢复或终止
```

**Scenario C: SSE 断线**
```
浏览器 fetch AbortController 中断 → 前端显示"连接中断"
→ 用户点击重试 → 重新订阅（Last-Event-ID 续传）
```

---

## 附录 A: 文件变更清单

### 新增文件（4 个）

```
backend/
  app/api/routers/chat_agent.py          # Agent Chat 适配层端点
  app/agents/intent_parser.py            # 意图解析器

frontend/src/
  components/chat/WorkflowProgressCard.vue  # 工作流进度卡片
  components/chat/ReviewCard.vue            # 人工审核卡片
```

### 修改文件（4 个）

```
backend/
  app/main.py                            # +1 行 include_router
  app/api/schemas/workflow.py            # +1 字段 source

frontend/src/
  components/chat/cell-types.ts          # ChatMessage 增加 agentMeta
  components/chat/ChatView.vue           # 模式切换 + Agent 发送 + SSE 订阅 + 条件渲染
```

### 不改文件（全部现有基础设施）

```
backend/app/services/workflow.py         # 被调用，不被修改
backend/app/services/sse_bus.py          # 被使用，不被修改
backend/app/api/routers/sse.py           # 被复用，不被修改
backend/app/api/routers/review.py        # 被复用，不被修改
backend/app/api/routers/chat.py          # 并列存在，不被修改
backend/app/agents/graph.py              # 不被修改
backend/app/agents/core/harness/         # 不被修改
frontend/src/composables/useChatHistory.ts  # 不被修改
```

---

## 附录 B: 端到端验收流程

```
1. 用户打开 Chat 页面
2. 点击模式切换按钮 → 显示 "Agent"
3. 输入 "帮我写一篇关于 AI 教育的小红书文章"
4. 点击发送
5. 验证：
   a. 消息流中出现用户消息
   b. 消息流中出现 assistant 消息 + WorkflowProgressCard
   c. 进度条从 0% 开始
   d. 步骤列表显示 9 个节点
   e. "搜索爆款" 状态变为 running（◉）
   f. 搜索完成后变为 completed（✓），进度 ~11%
   g. 依次推进：分析 → 图片规划 → 图片生成 → ...
   h. 到达终审节点 → ReviewCard 渲染
   i. 点击"通过并发布" → 工作流继续
   j. 发布完成 → 进度 100% → 显示笔记链接
6. 按 ESC → SSE 中断（如工作流仍在运行）
7. 切回 Chat 模式 → 原有功能正常
```

---

## 附录 C: 依赖清单

**无需新依赖**，全部基于现有技术栈：

| 技术 | 用途 | 现状 |
|------|------|------|
| FastAPI | 后端框架 | ✅ |
| Vue 3 | 前端框架 | ✅ |
| LangGraph | 工作流引擎 | ✅ |
| SSEEventBus | 事件推送 | ✅ |
| WorkflowService | 工作流服务 | ✅ |
| Pydantic | 数据验证 | ✅ |

---

*文档结束。*