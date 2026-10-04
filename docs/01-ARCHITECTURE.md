# 架构文档

> 从代码现状提取，不参考任何旧文档。单一真相源 = 代码。

---

## 一、双模式架构

项目有**两种运行模式**，共享同一套执行层和能力层：

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
                │  ├── collab/    (多Agent协作)           │
                │  └── memory/ + observer/               │
                └────────────────┬───────────────────────┘
                                 │
                ┌────────────────▼───────────────────────┐
                │         共享能力层                      │
                │  tools/*.py (Skills) + adapters/*.py   │
                └────────────────────────────────────────┘
```

### DAG 模式 vs ReAct 模式

| 维度 | DAG 模式 | ReAct 模式 |
|------|---------|-----------|
| 入口 | `services/workflow.py` → `WorkflowService` | `agents/chat_agent.py` → `ChatAgent` |
| 图定义 | `agents/graph.py` → `StateGraph` | 无固定图，LLM 自主决策 |
| 执行器 | `SingleShotExecutor` (单次 LLM + Skills) | `LoopExecutor` (多轮 LLM↔Tool) |
| 路由 | `smart_routing.py` 三层路由 + `belief.py` 信念系统 | LLM 自己选 Skill |
| 状态 | `WorkflowState` (TypedDict, LangGraph 管理) | `messages` 列表 (LLM 对话格式) |
| 人工审核 | `interrupt_before` + `Command(resume)` | `LoopState` 持久化 + confirm |
| 回溯 | 信心不足时回溯上游节点 (有 loop_counters 防死循环) | LLM 自己决定重试 |
| 适用场景 | 确定性生产流程 (搜索→分析→文案→图片→审核→发布) | 开放式对话 (用户自由提问) |

---

## 二、模块地图

```
backend/app/
├── main.py                          # FastAPI 入口: CORS + 路由注册 + lifespan
├── config.py                        # pydantic-settings: 全局配置
│
├── api/routers/                     # HTTP 路由层 (29个)
│   ├── workflow.py                  #   DAG 工作流 CRUD + 启动/审核/注入
│   ├── chat_agent.py                #   ReAct Chat 消息收发
│   ├── chat_session.py              #   Chat 会话管理
│   ├── sse.py                       #   SSE 事件流
│   ├── agents.py                    #   Agent 列表/详情
│   ├── skills.py                    #   Skill 列表
│   ├── plugins.py                   #   插件管理
│   ├── profile.py                   #   创作者画像
│   ├── review.py                    #   人工审核
│   ├── search.py                    #   搜索
│   ├── my_works.py                  #   我的作品
│   ├── workspace.py                 #   工作空间
│   ├── topic_pool.py                #   选题池
│   ├── creative_artifact.py         #   创作对象
│   ├── assets.py                    #   资产库
│   ├── auth.py                      #   认证
│   ├── feishu_oauth.py              #   飞书 OAuth
│   ├── feishu_bot.py                #   飞书机器人
│   ├── wechat_bot.py                #   微信机器人
│   ├── browser.py                   #   浏览器自动化
│   ├── config.py                    #   前端配置
│   ├── proxy.py                     #   API 代理
│   ├── quality_gate.py              #   质量门
│   ├── governance.py                #   治理监控
│   ├── chat.py                      #   旧版 Chat (兼容)
│   ├── chat_file.py                 #   Chat 文件
│   ├── codex.py                     #   Codex 集成
│   ├── task_plan.py                 #   任务计划
│   └── memory.py                    #   Agent 记忆
│
├── agents/                          # ── DAG 模式核心 ──
│   ├── graph.py                     #   LangGraph StateGraph 构建 + checkpointer
│   ├── nodes/                       #   12 个节点函数
│   │   ├── _base.py                 #     WorkflowState + NodeStatus + SSE helpers
│   │   ├── search.py                #     搜索节点 (小红书/抖音/微博)
│   │   ├── analyze.py               #     三层分析 (规则→粗分析→深度归因)
│   │   ├── copywrite.py             #     文案生成
│   │   ├── image_plan.py            #     图片规划 + 创作对象构建
│   │   ├── image_plan_planner.py    #     ContentPlanner (图片策略)
│   │   ├── image_gen.py             #     图片生成 (通义万相/Pollinations)
│   │   ├── image_review.py          #     图片人工审核 (interrupt)
│   │   ├── audit.py                 #     合规审核
│   │   ├── final_review.py          #     终审 (interrupt + 仲裁)
│   │   ├── publish.py               #     发布 (小红书/微信/飞书)
│   │   ├── card_gen.py              #     卡片生成 (降级模式)
│   │   ├── wechat_push.py           #     微信推送
│   │   ├── feishu_push.py           #     飞书推送
│   │   └── smart_routing.py         #     三层路由 (确定性→信心→协商)
│   ├── belief.py                    #   AgentBelief 信念系统
│   ├── chat_agent.py                # ── ReAct 模式入口 ──
│   ├── input_rules.py               #   Chat 输入守卫
│   ├── top_planner.py               #   LLM 不可用 fallback (正则匹配)
│   └── registry.py                  #   AgentDef 配置 + AgentRegistry
│
├── engine/                          # ── 共享执行层 ──
│   ├── schemas.py                   #   LLMProtocol + WorkflowContext + AgentOutput + HardRule
│   ├── harness/
│   │   ├── runtime.py               #   AgentHarness (运行时容器)
│   │   ├── executor/
│   │   │   ├── base.py              #     ExecutorBase (ABC)
│   │   │   ├── single_shot.py       #     SingleShotExecutor (DAG 用)
│   │   │   ├── loop.py              #     LoopExecutor (ReAct 用)
│   │   │   └── loop_state.py        #     LoopState 持久化
│   │   ├── recovery/
│   │   │   ├── loop.py              #     RecoveryLoop (max=3)
│   │   │   ├── strategies.py        #     恢复策略
│   │   │   ├── supervisor.py        #     恢复监督
│   │   │   ├── circuit_breaker.py   #     熔断器
│   │   │   └── backoff.py           #     退避算法
│   │   ├── governance/              #     (见下文治理层)
│   │   ├── collab/                  #     多 Agent 协作
│   │   │   ├── agent_manager.py     #       AgentManager + AgentHandle
│   │   │   ├── message_bus.py       #       InterAgentBus
│   │   │   ├── concurrency_pool.py  #       ConcurrencyPool
│   │   │   ├── tools.py             #       CollaborationTools (spawn/send/wait)
│   │   │   └── persistence.py       #       协作持久化
│   │   ├── memory/
│   │   │   └── memory.py            #     AgentMemory
│   │   └── observer/
│   │       └── observer.py          #     Observer (SSE 回调)
│   └── governance/                  #   治理层 (Codex 风格)
│       ├── guardian.py              #     Guardian (权限门控)
│       ├── token_budget.py          #     TokenBudget (预算控制)
│       ├── context_window.py        #     ContextWindowTracker
│       ├── context_compact.py       #     ContextCompactor (上下文压缩)
│       ├── request_queue.py         #     LLMRequestQueue (速率控制)
│       ├── stream_retry.py          #     StreamRetryState (流式重试)
│       ├── llm_circuit.py           #     LLMCircuit (LLM 级熔断)
│       ├── thread_store.py          #     ThreadStore (事件日志+checkpoint)
│       ├── hooks.py                 #     HookRegistry (生命周期回调)
│       └── time_reminder.py         #     TimeReminder (时间感知注入)
│
├── tools/                           # ── 共享能力层: Skills ──
│   ├── base.py                      #   Skill(ABC) + SkillRegistry
│   ├── registry.py                  #   get_skill_class() + @register
│   ├── permissions.py               #   Permission 枚举
│   ├── xhs_search.py                #   小红书搜索 Skill
│   ├── trending_search.py           #   热搜 Skill
│   ├── viral_analyzer.py            #   爆点分析 Skill
│   ├── copywrite_builder.py         #   文案构建 Skill
│   ├── vl_analyze.py                #   视觉理解 Skill (Qwen-VL)
│   ├── browser_skill.py             #   浏览器自动化 Skill
│   ├── file_tools.py                #   文件读写 Skill
│   ├── dev_tools.py                 #   开发工具 Skill
│   ├── workflow_skill.py            #   工作流 Skill
│   ├── context_vars.py              #   上下文变量
│   ├── wechat_send_text_skill.py    #   微信发文本 Skill
│   ├── wechat_send_file_skill.py    #   微信发文件 Skill
│   ├── feishu_file_ops_skill.py     #   飞书文件操作 Skill
│   ├── feishu_wiki_doc_skill.py     #   飞书文档 Skill
│   └── github_plugin_skill.py       #   GitHub 插件 Skill
│
├── adapters/                        # ── 共享能力层: LLM/平台适配器 ──
│   ├── llm_base.py                  #   BaseLLM(ABC) + Semaphore 并发控制
│   ├── deepseek.py                  #   DeepSeekAdapter (V3 + R1)
│   ├── qwen_vl.py                   #   QwenVLAdapter (图理解)
│   ├── image_gen.py                 #   ImageGenAdapter (通义万相 + Pollinations)
│   └── feishu.py                    #   FeishuClient (飞书 API)
│
├── services/                        # 业务服务层
│   ├── workflow.py                  #   WorkflowService (DAG 启动/审核/注入/恢复)
│   ├── chat_session.py              #   ChatSessionService
│   ├── sse_bus.py                   #   SSEEventBus (发布/订阅)
│   ├── profile_service.py           #   创作者画像
│   ├── agent_memory.py              #   Agent 长期记忆
│   ├── creative_artifact.py         #   创作对象
│   ├── image_store.py               #   图片存储
│   ├── asset_library.py             #   资产库
│   ├── topic_pool.py                #   选题池
│   ├── quality_gate.py              #   质量门
│   ├── task_plan.py                 #   任务计划
│   ├── plugin_service.py            #   插件服务
│   ├── github_installer.py          #   GitHub 插件安装
│   ├── feishu_oauth.py              #   飞书 OAuth
│   ├── chat_file.py                 #   Chat 文件
│   ├── work_collector.py            #   作品收集
│   ├── self_attribution.py          #   自归因
│   ├── performance_collector.py     #   性能收集
│   ├── notification_bus.py          #   通知总线
│   ├── workflow_events.py           #   工作流事件
│   ├── workflow_cleanup.py          #   工作流清理
│   └── context.py                   #   上下文工具
│
├── core/                            # 插件系统
│   ├── base_interfaces.py           #   BasePlugin + BaseWorkflowNodePlugin + PluginEventBus
│   ├── plugin_types.py              #   PluginManifest + PluginCategory + PluginStatus
│   ├── plugin_manager.py            #   PluginManager (发现/加载/执行/卸载/重载)
│   ├── node_registry.py             #   NodeRegistry (内置+插件节点统一管理)
│   ├── plugin_node_bridge.py        #   插件→工作流节点桥接
│   ├── sync_builtin_plugins.py      #   内置插件同步
│   └── event_bus.py                 #   EventBus
│
└── db/                              # 数据层
    ├── session.py                   #   SQLAlchemy async session
    ├── models.py                    #   ORM 模型
    ├── plugin_models.py             #   插件 ORM
    └── seed_workflow_definitions.py #   工作流定义种子
```

---

## 三、依赖规则

### DAG 模式

```
api/routers/workflow.py
  → services/workflow.py
    → agents/graph.py
      → agents/nodes/*.py
        → engine/harness/runtime.py (AgentHarness)
          → engine/harness/executor/single_shot.py
          → engine/governance/*
          → tools/*.py (Skills)
          → adapters/*.py (LLM)
    → agents/belief.py (AgentBelief)
    → agents/nodes/smart_routing.py (三层路由)
```

### ReAct 模式

```
api/routers/chat_agent.py
  → agents/chat_agent.py
    → agents/input_rules.py (守卫)
    → agents/registry.py (build_harness)
    → engine/harness/executor/loop.py (LoopExecutor)
      → engine/harness/runtime.py (AgentHarness)
        → engine/governance/*
        → tools/*.py (Skills)
        → adapters/*.py (LLM)
    → agents/top_planner.py (fallback)
```

### 禁止方向

| 禁止 | 原因 |
|------|------|
| `engine/` → `langgraph` | Harness 不依赖 LangGraph |
| `engine/` → `fastapi` | Harness 不依赖 Web 框架 |
| `tools/` → `agents/nodes/` | Skills 不依赖节点实现 |
| `adapters/` → `agents/` | 适配器不依赖业务逻辑 |
| `agents/chat_agent.py` → `agents/graph.py` | ReAct 不依赖 DAG 图定义 |
| `agents/chat_agent.py` → `agents/nodes/` | ReAct 不依赖具体节点函数 |
| `services/` → `engine/harness/executor/` | 服务层不直接用执行器，经 Harness |

---

## 四、DAG 模式图拓扑 (从 graph.py 提取)

```
search ──→ analyze ──→ copywrite ──→ image_plan ──→ image_gen
  │           │            │                            │
  │←──────────┘            │                            │
  │ (信心不足回溯)          │                            │
  │                         │←───────────────────────────┘
  │                         │ (image_gen 失败回退)
  │                         │
  │                         ▼
  │                    image_review ──→ audit ──→ final_review ──→ publish
  │                         │              │            │              │
  │                         │              │            │←─────────────┘
  │                         │              │            │ (打回回溯)
  │                         │              │            │
  │                         ▼              ▼            ▼
  │                    image_gen      copywrite     search/analyze/
  │                    (拒绝重做)    (需修改)      copywrite/image_gen
  │
  └──→ END (搜索失败)

publish ──→ card_gen ──→ wechat_push ──→ feishu_push ──→ END
                │              │
                └──→ feishu_push   └──→ END
```

### interrupt_before (5 个人工审核点)

| 节点 | 暂停时机 | 用户操作 |
|------|---------|---------|
| copywrite | analyze 完成后 | 选方向/调性 |
| image_gen | image_plan 完成后 | 卡片编辑器加载 card_draft，编辑出图后 inject |
| image_review | image_gen 完成后 | 调图片 |
| final_review | audit 完成后 | 手机预览+终审确认 |
| publish | final_review 通过后 | 确认发布 |

### 三层路由 (从 smart_routing.py 提取)

| 层 | 机制 | LLM 成本 | 示例 |
|----|------|---------|------|
| Layer 1 | 确定性规则 | 0 | search 失败 → END; image_gen 失败 → 回退 image_plan |
| Layer 2 | 信心路由 (AgentBelief) | 0 | analyze 信心不足 → 回 search 补数据; audit 需修改 → 回 copywrite |
| Layer 3 | 协商路由 | 1 | audit 拒绝 vs copywrite 信心高 → final_review 仲裁 |

### 回溯保护

| 节点 | 最大回溯次数 | 代码锚点 |
|------|------------|---------|
| search | 4 | `smart_routing.py` → `_MAX_LOOP_COUNTS` |
| analyze | 3 | 同上 |
| copywrite | 2 | 同上 |
| image_gen | 2 | 同上 |
| 其他 | 3 | `_DEFAULT_MAX_LOOP` |

---

## 五、ReAct 模式详解 (从 chat_agent.py + loop.py 提取)

### 执行流程

```
用户消息
  │
  ▼
ChatInputRule.check_pre()          # 守卫: prompt injection / 长度 / 敏感词
  │ blocked → 返回 ChatResult(status="blocked")
  ▼ passed
AgentRegistry.build_harness()      # 按 agent_id 装配 Harness
  │
  ▼
_agentic_loop():
  LoopExecutor.execute():
    │
    ├── 构建 messages:
    │     system prompt (role + skills 列表 + 输出格式)
    │     + work_context_prompt (当前作品上下文)
    │     + profile_prompt (创作者画像)
    │     + creative_state_prompt (创作状态)
    │     + fork_context (分叉上下文)
    │     + 对话历史 (summary + recent)
    │     + 用户消息
    │
    ├── for iteration in 1..12:
    │     ├── TokenBudget 检查 (超预算 → 压缩/告警)
    │     ├── LLMRequestQueue 排队
    │     ├── LLM.chat() (流式) → 解析 JSON
    │     │     期望: { thought, tool_calls, final }
    │     ├── if final=true → 返回 output
    │     ├── for each tool_call:
    │     │     ├── Guardian.permission_gate() (权限门控)
    │     │     ├── Skill.execute() → observation
    │     │     └── 喂回 LLM: [observation] skill_name -> {json}
    │     └── ThreadStore 记录 checkpoint
    │
    └── 超时/超迭代 → 用已有进度兜底返回
```

### 关键参数

| 参数 | 值 | 代码锚点 |
|------|---|---------|
| max_iterations | 12 | `executor/loop.py` → `_DEFAULT_MAX_ITER` |
| total_timeout | 240s | `executor/loop.py` → `_DEFAULT_TOTAL_TIMEOUT` |
| stream_idle_timeout | 120s | `executor/loop.py` → `_STREAM_IDLE_TIMEOUT` |
| llm_call_timeout | 120s | `executor/loop.py` → `_LLM_CALL_TIMEOUT` |
| llm_stream_ceiling | 1200s | `executor/loop.py` → `_LLM_STREAM_CEILING` |
| max_input_length | 10000 | `input_rules.py` → `MAX_INPUT_LENGTH` |

### LLM 不可用 fallback

当 LLM 完全不可用时，`top_planner.py` 的 `_keyword_fallback()` 用正则匹配用户消息中的关键词，映射到预定义的 Skill 调用链。这是兜底路径，主流程走 LLM 自主决策。

### 会话记忆

- 短期：最近 10 条消息完整保留
- 长期：超过 10 条的早期消息由 LLM 压缩为摘要（300-500字），存入 `ChatSession.summary`
- 创作状态：`creative_state` 跟踪当前文案/草稿/阶段，跨消息保持连续性
- 创作者画像：`profile_prompt` 软注入，LLM 回复带画像调性

---

## 六、治理层 (从 engine/governance/ 提取)

| 组件 | 文件 | 职责 |
|------|------|------|
| Guardian | `guardian.py` | 工具调用安全门控 (policy → confirm → validate) |
| TokenBudget | `token_budget.py` | Token 预算控制 + 超预算告警/压缩 |
| LLMCircuit | `llm_circuit.py` | LLM 级熔断器 |
| StreamRetry | `stream_retry.py` | 流式调用重试策略 |
| LLMRequestQueue | `request_queue.py` | LLM 请求排队 (速率控制) |
| ContextWindow | `context_window.py` | 上下文窗口 token 精确追踪 |
| ContextCompactor | `context_compact.py` | 上下文压缩 (预算耗尽时触发) |
| ThreadStore | `thread_store.py` | 事件日志 + checkpoint/rollback |
| HookRegistry | `hooks.py` | 生命周期回调 (tool/LLM 事件) |
| TimeReminder | `time_reminder.py` | 周期性时间感知注入 |

---

## 七、多 Agent 协作 (从 engine/collab/ 提取)

| 组件 | 文件 | 职责 |
|------|------|------|
| AgentManager | `agent_manager.py` | 子 Agent 注册/调度/状态管理 |
| InterAgentBus | `message_bus.py` | Agent 间消息传递 |
| ConcurrencyPool | `concurrency_pool.py` | 并发槽位控制 |
| CollaborationTools | `tools.py` | spawn_agent / send_message / wait_agent |
| Persistence | `persistence.py` | 协作状态持久化 |

协作模式 (`CollabMode`): DISABLED / REACTIVE / PROACTIVE

---

## 八、插件系统 (从 core/ 提取)

```
PluginManager (发现/加载/执行/卸载/重载)
    │
    ▼
plugin_node_bridge.py (扫描 workflow_node 类型插件)
    │
    ▼
NodeRegistry (内置节点 + 插件节点统一管理)
    │
    ▼
graph.py → _resolve_node() (插件同名 → 自动替换内置节点)
```

插件类型 (`PluginCategory`): datasource / platform / workflow_node / tool / ui

---

## 九、SSE 事件流 (从 sse_bus.py 提取)

| 事件类型 | 方向 | 用途 |
|---------|------|------|
| node_started | 后→前 | 节点开始执行 |
| node_completed | 后→前 | 节点执行完成 |
| node_error | 后→前 | 节点执行出错 |
| review_required | 后→前 | 需要人工审核 (interrupt) |
| supervisor_suggestion | 后→前 | 监督 Agent 建议 |
| workflow_completed | 后→前 | 工作流完成 (终态) |
| workflow_error | 后→前 | 工作流出错 (终态) |
| workflow_suspended | 后→前 | 工作流挂起 (终态) |
| workflow_failed | 后→前 | 工作流失败 (终态) |
| workflow_cancelled | 后→前 | 工作流取消 (终态) |
| workflow_terminated | 后→前 | 工作流终止 (终态) |
| intent_parsed | 后→前 | 意图解析完成 (Chat Agent) |
| draft_patch | 后→前 | 草稿增量更新 (Chat Agent) |
| card_draft_ready | 后→前 | 卡片草稿就绪 (Chat Agent) |
| shortcut_completed | 后→前 | 快捷流程完成 (终态) |
| heartbeat | 后→前 | 15s 心跳保活 |

特性: Last-Event-ID 续传 | 终态事件后 300s 延迟清理 | 单进程部署 (多 worker 需 Redis Pub/Sub)

---

## 十、前端结构 (从 frontend/src/ 提取)

```
frontend/src/
├── views/                           # 页面
│   ├── WorkbenchView.vue            #   DAG 工作台 (主页面)
│   ├── WorkflowEditorView.vue       #   工作流编辑器
│   ├── WorkflowTemplatesView.vue    #   工作流模板
│   ├── TopicPoolView.vue            #   选题池
│   ├── MyWorksView.vue              #   我的作品
│   ├── SettingsView.vue             #   设置
│   ├── LoginView.vue                #   登录
│   └── ...                          #   Landing/Eco/McpBridge/ParticleHome
│
├── components/
│   ├── workbench/                   #   DAG 工作台组件
│   │   ├── SearchCard.vue           #     搜索节点卡片
│   │   ├── AnalyzeCard.vue          #     分析节点卡片
│   │   ├── CopywriteCard.vue       #     文案节点卡片
│   │   ├── ImagePlanCard.vue       #     图片规划卡片
│   │   ├── ImageGenCard.vue        #     图片生成卡片
│   │   ├── ImageReviewCard.vue     #     图片审核卡片
│   │   ├── FinalReviewCard.vue     #     终审卡片
│   │   ├── PublishCard.vue         #     发布卡片
│   │   ├── RightPanel.vue          #     右侧配置面板
│   │   └── ...                     #     Config/History/Sidebar/Welcome
│   │
│   ├── chat/                        #   ReAct Chat 组件
│   │   ├── ChatView.vue            #     Chat 主视图
│   │   ├── AssistantMessageCell.vue #     助手消息
│   │   ├── UserMessageCell.vue     #     用户消息
│   │   ├── ChatReviewCard.vue      #     审核卡片
│   │   ├── ChatConfirmCard.vue     #     确认卡片
│   │   ├── AgentProgressCard.vue   #     Agent 进度
│   │   ├── PhoneFrame.vue          #     手机预览框
│   │   ├── composables/            #     Chat 组合式函数
│   │   │   ├── useChatAgent.ts     #       Agent 交互
│   │   │   ├── useChatSSE.ts       #       SSE 连接
│   │   │   ├── useChatSend.ts      #       发送消息
│   │   │   ├── useChatStream.ts    #       流式响应
│   │   │   └── ...                 #       useChatActions/Init/Interactions/...
│   │   └── ...                     #     BrowserSidePanel/WorkDetailPanel/...
│   │
│   ├── workflow/                    #   工作流编辑器组件
│   ├── card-editor/                 #   卡片编辑器
│   ├── settings/                    #   设置组件
│   ├── plugins/                     #   插件管理组件
│   └── common/                      #   通用组件
│
├── stores/                          # Pinia 状态
│   ├── workflow.ts                  #   工作流状态
│   ├── work.ts                      #   作品状态
│   ├── auth.ts                      #   认证状态
│   └── ...                          #   account/creativeArtifact/files/plugin/templates/workspace
│
├── api/                             # API 客户端
│   ├── client.ts                    #   axios 实例
│   ├── workflow.ts                  #   工作流 API
│   ├── chatSessions.ts              #   Chat 会话 API
│   └── ...                          #   agents/assets/auth/browser/...
│
├── adapters/                        # 平台适配器 (发布格式)
│   ├── xiaohongshu.ts               #   小红书
│   ├── wechat-mp.ts                 #   微信公众号
│   ├── weibo.ts                     #   微博
│   └── pack-builder.ts              #   打包构建器
│
└── composables/                     # 通用组合式函数
    ├── useCardEditor.ts             #   卡片编辑器
    ├── useSearchFlow.ts             #   搜索流程
    └── ...                          #   useChatHistory/useConfirm/useTypewriter/...
```

---

## 十一、WorkflowState 字段 (从 _base.py 提取)

| 字段 | 类型 | 用途 |
|------|------|------|
| workflow_id | str | 工作流 ID |
| user_id | str | 用户 ID |
| account_id | str | 小红书账号 ID |
| topic | str | 主题 |
| search_keyword | str | 搜索关键词 |
| creative_brief | str | 创作要求 |
| current_node | str | 当前节点 |
| node_statuses | dict[str, str] | 节点状态 (Annotated merge) |
| node_outputs | dict[str, dict] | 节点输出 (Annotated merge) |
| node_errors | dict[str, dict] | 节点错误 (Annotated merge) |
| recovery_attempts | dict[str, int] | 恢复尝试次数 (Annotated merge) |
| pending_reviews | list[dict] | 待审核列表 |
| pending_suggestions | list[dict] | 监督建议 |
| suspended_until | str \| None | 挂起时间 |
| model_settings | dict | 模型/温度/风格配置 |
| reference | dict | 选题池参考素材 |
| user_memory | dict | 用户长期记忆 |
| image_assets | list[dict] | 本地图片资产 |
| asset_mode | bool | 无模板图片模式 |
| platform | str | 目标平台 |
| format_name | str | 输出比例 |
| agent_beliefs | dict[str, dict] | 信念快照 (Annotated merge) |
| negotiations | list[dict] | 协商记录 |
| loop_counters | dict[str, int] | 回溯计数 (Annotated merge) |
| user_profile | dict \| None | 创作者画像 (启动时注入，节点禁止读 DB) |
| experience_hints | dict \| None | 预留恒 None (红线：禁止实现) |

---

## 十二、Skill 智能路由架构 (从 skill_router.py + loop.py 提取)

### 问题

当 Skills 数量增长到 60+ 时，全量注入 LLM 会导致：
- **Token 开销**：每个 Skill 的 description + parameters 占 200-500 token，67 个 Skill 约 2 万 token
- **选择干扰**：LLM 在 67 个 function 中选对的概率下降，误调率上升
- **延迟**：tools schema 越大，LLM 首 token 延迟越高

### 三层路由策略

```
用户消息
  │
  ▼
SkillRouter.select_skills(all_skills, user_message)
  │
  ├── 层C 分组加载 ──────────────────────────────────────────
  │   HOT  → 始终注入（创作/核心运营）
  │   WARM → 按类别命中才注入（分析/审核/排期）
  │   COLD → 仅触发词命中才注入（开发/平台）
  │
  ├── 层B trigger_words 预筛 ────────────────────────────────
  │   精确匹配：trigger_word ∈ user_message
  │   模糊匹配：trigger_word 汉字与 user_message 重叠率 ≥ 60%
  │   匹配后：提升对应 Skill 所在类别为 active
  │
  └── 层A 两级路由 ──────────────────────────────────────────
      system prompt 注入分类摘要表（●=命中 ○=未命中）
      LLM 按类别决策，缩小选择空间
```

### 分类定义

| 分类 | 枚举 | 图标 | 默认优先级 | 说明 |
|------|------|------|-----------|------|
| 创作 | `create` | 🎨 | hot | 文案/卡片/图文/视频脚本 |
| 分析 | `analyze` | 🔍 | warm | 诊断/复盘/数据/竞品分析 |
| 运营 | `operate` | 📊 | hot | 画像/排期/热点/策略 |
| 审核 | `audit` | 🛡 | warm | 风险/合规/质量门禁 |
| 开发 | `dev` | 🛠 | cold | 文件/浏览器/工作流 |
| 平台 | `platform` | 🔌 | cold | 微信/飞书等外部平台 |

### 优先级定义

| 优先级 | 枚举 | 加载规则 |
|--------|------|---------|
| 热 | `hot` | 始终注入，无需触发 |
| 温 | `warm` | 本类别被 trigger 命中时注入 |
| 冷 | `cold` | 仅自身被 trigger 命中时注入 |

### 路由效果（67 个 Skill 实测）

| 用户请求 | 选中数 | 触发匹配 | 命中类别 |
|---------|--------|---------|---------|
| 帮我写一篇种草文案 | 31/67 | copywriting | 创作 |
| 诊断一下我的账号 | 43/67 | account_diagnosis | 分析 |
| 今天热点是什么 | 46/67 | trending_topics, trend_rider | 分析+运营 |
| 帮我建个画像 | 34/67 | profile_builder, profile_manager | 运营 |
| 做一张小红书卡片 | 31/67 | card_design, card_xiaohongshu | 创作 |
| 发到微信 | 33/67 | wechat_send_file, wechat_send_text | 平台 |
| 润色一下这段话 | 31/67 | text_polisher | 创作 |
| 帮我排个内容日历 | 34/67 | content_calendar | 运营 |
| 分析竞品 | 43/67 | competitor_analysis | 分析 |

### 集成点

| 位置 | 作用 |
|------|------|
| `LoopExecutor.__init__` | 初始化 `SkillRouter(max_tools=50)` |
| `LoopExecutor._system_prompt` | 调用 `select_skills` → 注入路由表 + 仅活跃 skill 的 guidance |
| `LoopExecutor._build_tools_schema` | 仅暴露选中 skill 的 tool schema |
| `skill_map` 构建 | 仅选中 skill 参与执行循环 |

### 新建 Skill 规范（必读）

创建新 Skill 时，**必须**在 `.md` frontmatter 中设置 `category` 和 `priority`，否则默认归入 `operate/hot`。

```yaml
---
node_type: plan            # Skill 层级：plan/produce/discover/attribute/...
name: my_new_skill         # 唯一标识（snake_case）
category: create           # 分类：create/analyze/operate/audit/dev/platform
priority: hot              # 优先级：hot/warm/cold
display_name: 我的技能      # 中文显示名
description: >-            # 功能描述（≤200字）
  描述这个 Skill 做什么。
trigger_words:             # 触发词（至少2个，用于预筛匹配）
  - 触发词1
  - 触发词2
---
```

#### category 选择指南

| 你的 Skill 做什么 | 选哪个 category |
|-------------------|----------------|
| 生成内容（文案/卡片/图片/视频脚本/大纲/钩子） | `create` |
| 分析数据（诊断/复盘/竞品/趋势/评估） | `analyze` |
| 管理运营（画像/排期/热点/策略/发布） | `operate` |
| 审核把关（质量门禁/合规/风险） | `audit` |
| 开发工具（文件/浏览器/工作流/脚本） | `dev` |
| 外部平台（微信/飞书/抖音API） | `platform` |

#### priority 选择指南

| 使用频率 | 选哪个 priority | 效果 |
|---------|----------------|------|
| 高频核心，几乎每次都要 | `hot` | 始终注入，零延迟 |
| 中频，按需调用 | `warm` | 用户提到相关词时才注入 |
| 低频，很少用 | `cold` | 只有精确触发才注入 |

#### node_type → category 自动映射

如果 `.md` 中没有显式设置 `category`，`SkillRouter` 会按 `node_type` 自动推断：

| node_type | → category |
|-----------|-----------|
| produce, copywrite, format, caption_hashtag, card_design, social_content, condense, polish | create |
| analyze, attribute, discover, topic_evaluator | analyze |
| plan, search, publish | operate |
| quality_gate, audit | audit |
| dev, file, workflow, browser | dev |
| wechat*, feishu* | platform |

> **建议**：即使有自动映射，也显式设置 `category`，避免 `plan` 类 Skill 被统一归入 `operate`。

### 文件清单

| 文件 | 职责 |
|------|------|
| `backend/app/tools/skill_router.py` | 核心路由器：分类枚举、优先级枚举、模糊匹配、路由表生成 |
| `backend/app/tools/base.py` | Skill 基类：`skill_category` / `skill_priority` 属性 |
| `backend/app/tools/prompt_skills.py` | 解析 frontmatter 中 `category` / `priority` |
| `backend/app/engine/harness/executor/loop.py` | 集成点：路由选择 → system prompt → tools schema → skill_map |