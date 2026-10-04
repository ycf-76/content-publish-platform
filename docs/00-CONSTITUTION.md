# 项目宪法

> 纯粹从代码提取。不可变决策改 = 项目重新设计；可变决策改 = 局部重构。

| 版本 | v2.0 |
|------|------|
| 生效 | 2026-09-18 |

---

## 不可变决策

| # | 决策 | 代码锚点 | 锁定理由 |
|---|------|---------|---------|
| C1 | **双模式运行**：DAG 流水线 + ReAct 自主循环 | `services/workflow.py` + `agents/chat_agent.py` | 两种模式满足不同交互场景，共享底层 |
| C2 | DAG 模式 = LangGraph StateGraph 固定拓扑 | `agents/graph.py` → `build_workflow_graph()` | 绑定 checkpoint/interrupt/conditional_edge |
| C3 | ReAct 模式 = LoopExecutor LLM 自主决策 | `agents/chat_agent.py` → `_agentic_loop()` + `engine/harness/executor/loop.py` | LLM 自己选 Skill、调、观察、再思考 |
| C4 | 双模式共享 Harness 执行层 | `engine/harness/runtime.py` → `AgentHarness` | DAG 节点和 ReAct Loop 都通过 Harness 统一调 LLM/Skills |
| C5 | 能力层 = Skills + Adapters 解耦 | `tools/base.py` → `Skill(ABC)` + `adapters/llm_base.py` → `BaseLLM(ABC)` | 新增能力 = 加子类 + @register |
| C6 | DAG 路由 = 三层路由 + 信念系统 | `agents/nodes/smart_routing.py` + `agents/belief.py` | 确定性规则(0 LLM) → 信心路由(0 LLM) → 协商路由(1 LLM) |
| C7 | SSE 实时推送 | `services/sse_bus.py` → `SSEEventBus` | 工作流 5-15 分钟，不能绑页面 |
| C8 | 回退 = LangGraph checkpoint 恢复 | `graph.py` → `AsyncSqliteSaver` + `interrupt_before` | 与 LangGraph 语义对齐 |
| C9 | Agent = 配置驱动 | `agents/registry.py` → `AgentDef` + `BUILTIN_AGENTS` | 新增 Agent = 加 AgentDef |
| C10 | 插件可替换内置节点 | `core/plugin_node_bridge.py` + `core/node_registry.py` | 插件注册同名节点 → `graph.py` 的 `_resolve_node()` 自动替换 |
| C11 | Token AES-GCM 加密 | `db/models.py` → `FeishuOAuthConnection.access_token_encrypted` | 安全红线 |
| C12 | 前端 Vue3 + TypeScript | `frontend/package.json` | 已深度绑定 |

---

## 双模式架构

```
                     ┌──────────────────────────────────┐
                     │          前端 (Vue3 + TS)         │
                     │  Workbench ── DAG │ Chat ── ReAct │
                     └─────┬──────────────────┬─────────┘
                           │ SSE              │ SSE
                 ┌─────────▼─────────┐  ┌────▼──────────────┐
                 │   DAG 模式         │  │   ReAct 模式       │
                 │                   │  │                   │
                 │ services/         │  │ agents/           │
                 │  workflow.py      │  │  chat_agent.py    │
                 │      │            │  │      │            │
                 │ agents/graph.py   │  │ input_rules.py    │
                 │  (StateGraph)     │  │  (守卫)           │
                 │      │            │  │      │            │
                 │ agents/nodes/     │  │ executor/loop.py  │
                 │  (12个节点函数)   │  │  (ReAct循环)      │
                 │ smart_routing.py  │  │ top_planner.py    │
                 │ belief.py         │  │  (LLM不可用兜底)  │
                 └────────┬─────────┘  └────────┬──────────┘
                          │                       │
                 ┌────────▼───────────────────────▼────────┐
                 │            共享 Harness 执行层           │
                 │  runtime.py → AgentHarness              │
                 │  ├── executor/single_shot.py  (DAG用)  │
                 │  ├── executor/loop.py         (ReAct用) │
                 │  ├── recovery/  (RecoveryLoop×3+熔断)  │
                 │  ├── governance/ (guardian/budget/...)  │
                 │  └── memory/ + observer/               │
                 └────────────────┬───────────────────────┘
                                  │
                 ┌────────────────▼───────────────────────┐
                 │         共享能力层                      │
                 │  tools/*.py (Skills) + adapters/*.py   │
                 └────────────────────────────────────────┘
```

### DAG 模式调用链

```
POST /api/workflows
  → services/workflow.py → WorkflowService.start_workflow()
    → 画像校验 (fail-fast)
    → 并发检查 (MAX_CONCURRENT_WORKFLOWS=10)
    → agents/graph.py → build_workflow_graph()
      → StateGraph(WorkflowState)
      → add_node × 12 (支持插件替换: _resolve_node)
      → add_conditional_edges (smart_routing 三层路由)
      → compile(interrupt_before=[copywrite, image_gen, image_review, final_review, publish])
    → graph.astream(initial_state)
      → search_node → analyze_node → [interrupt] → copywrite_node
        → image_plan_node → [interrupt] → image_gen_node
        → [interrupt] → image_review_node → audit_node
        → [interrupt] → final_review_node → [interrupt] → publish_node
      每个节点: _run_node_harness() → AgentHarness → SingleShotExecutor → Skills
      路由: route_after_*() 读 AgentBelief → 决定下一步或回溯
      审核: interrupt → POST /api/workflows/{id}/review → Command(resume)
```

### ReAct 模式调用链

```
POST /api/v1/chat/sessions/{id}/messages
  → agents/chat_agent.py → ChatAgent.process()
    → input_rules.py → ChatInputRule.check_pre() (prompt injection/长度/敏感词)
    → registry.py → AgentRegistry.build_harness("chat_agent")
    → _agentic_loop():
        LoopExecutor.execute():
          构建 messages (system + profile + creative_state + history + user)
          for i in 1..12:
            TokenBudget 检查
            LLMRequestQueue 排队
            LLM.chat() (流式) → 解析 {thought, tool_calls, final}
            if final → return output
            for each tool_call:
              Guardian.permission_gate()
              Skill.execute() → observation
              喂回 LLM
          超时/超迭代 → 兜底返回
    → SSE 流式: intent_parsed → draft_patch → card_draft_ready
```

---

## 可变决策

| # | 决策 | 当前值 | 代码锚点 | 变更影响 |
|---|------|-------|---------|---------|
| V1 | 文案模型 | DeepSeek-R1 | `registry.py` → copywrite `llm_model="deepseek-r1"` | `adapters/deepseek.py` |
| V2 | 通用文本模型 | DeepSeek-V3 | `registry.py` → 各 agent `llm_model="deepseek-v3"` | `adapters/deepseek.py` |
| V3 | 图理解模型 | Qwen-VL-Max | `config.py` → `qwen_vl_model` | `adapters/qwen_vl.py` |
| V4 | 生图模型 | wanx2.1-t2i-turbo | `config.py` → `wanx_model` | `adapters/image_gen.py` |
| V5 | 备用生图 | Pollinations | `adapters/image_gen.py` → `PollinationsAdapter` | 同上 |
| V6 | LLM 并发 | Semaphore(5) | `adapters/llm_base.py` → `LLM_CONCURRENCY_LIMIT` | 全局 |
| V7 | DAG 执行模式 | sequential | `db/models.py` → `Workflow.execution_mode` | `services/workflow.py` |
| V8 | ReAct 最大迭代 | 12 | `executor/loop.py` → `_DEFAULT_MAX_ITER` | Chat Agent |
| V9 | ReAct 总超时 | 240s | `executor/loop.py` → `_DEFAULT_TOTAL_TIMEOUT` | Chat Agent |
| V10 | 工作流并发上限 | 10 | `services/workflow.py` → `MAX_CONCURRENT_WORKFLOWS` | 全局 |
| V11 | 数据库 | SQLite(dev)/MySQL(prod) | `config.py` → `database_url` | `db/session.py` |
| V12 | SSE 扩展 | 单进程内存 | `sse_bus.py` | 需 Redis Pub/Sub |

---

## 核心路径 (DAG 模式)

```
search → analyze → copywrite → image_plan → image_gen → image_review → audit → final_review → publish
```

任何改动后必须验证此路径跑通。

---

## 术语

| 术语 | 定义 | 代码锚点 |
|------|------|---------|
| DAG 模式 | LangGraph 固定流水线 | `agents/graph.py` + `agents/nodes/` |
| ReAct 模式 | LLM 自主决策循环 | `agents/chat_agent.py` + `executor/loop.py` |
| Agent | 基于 LLM 的单一职责智能单元 | `agents/registry.py` → `AgentDef` |
| Skill | Agent 可调用的能力 | `tools/base.py` → `Skill(ABC)` |
| Harness | Agent 运行时容器，双模式共享 | `engine/harness/runtime.py` → `AgentHarness` |
| SingleShotExecutor | 单次 LLM + Skills 集中执行 (DAG) | `executor/single_shot.py` |
| LoopExecutor | ReAct 循环执行器 (Chat) | `executor/loop.py` |
| WorkflowState | DAG 节点间 TypedDict | `agents/nodes/_base.py` → `WorkflowState` |
| AgentBelief | 节点信心快照，驱动三层路由 | `agents/belief.py` → `AgentBelief` |
| RecoveryLoop | Agent 内恢复循环 (max=3) | `engine/harness/recovery/loop.py` |
| Guardian | 工具调用安全门控 | `engine/governance/guardian.py` |
| ChatInputRule | Chat 输入守卫 | `agents/input_rules.py` |
| 三层路由 | 确定性→信心→协商 | `agents/nodes/smart_routing.py` |
| interrupt | LangGraph 人工审核暂停 | `graph.py` → `interrupt_before` |
| _resolve_node | 插件替换内置节点 | `graph.py` → `_resolve_node()` |