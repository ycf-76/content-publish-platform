# Agent 核心收敛与 Chat 驱动 Agent 集成方案（校准版）

> 版本: v2.1.0
> 日期: 2026-08-21
> 状态: 已完成（Phase 0 / 1 / 2 / 3）
> 优先级: P0
> 目标: 收敛能力底座，补齐 Chat 所需的 Session / Prompt / Agent 注册，让 Chat 与 DAG 共享同一套能力层

---

## 一、背景与关键结论

经过代码核实，项目的真实状态是：

1. 生产工作流（DAG）实际走的是 `nodes/*.py`：9 个节点直接调 `get_deepseek_llm()` + 直接调 `Skill`，没有走 `AgentHarness` / `LoopExecutor`。`copywrite.py` 明确注释「不走完整 harness」，`publish.py` 明确注释「不走 LLM Loop」。
2. `core/harness/` 是半闲置的并行架构：`AgentHarness` / `LoopExecutor` / `recovery` / `observer` / `harnesses/factory.py` 设计正确，但 `_run_node_harness()`、`build_search_harness()`、`build_publish_harness()` 全项目无调用方，只有 `get_deepseek_llm()` 被实际使用。
3. `configs/*.yaml` 的 Agent 注册是死代码：没有 yaml loader，只覆盖 7 个节点，且中文内容已损坏为 `??????`。
4. 存在多套重叠体系：模型层（`adapters/` vs `core/sandbox/model_router.py`）、安全层（`permission_gate` vs `sandbox_workflow_bridge`）、记忆层（`AgentMemory` vs `agent_memory`）。
5. **关键事实**：DAG 节点不依赖 LangChain 调用接口。`get_deepseek_llm()` 返回 `DeepSeekAdapter(BaseLLM)`，其 `chat(messages) -> dict` / `stream_chat(...) -> AsyncIterator[dict]` 与 `LLMProtocol` 签名完全一致。`BaseLLM` 的 Semaphore 并发控制也是项目自建的，不依赖 LangChain。LangChain 依赖仅存在于 `ModelRouter._get_adapter()` 的死代码内部（ChatOpenAI / ChatAnthropic / ChatTongyi wrapper），Phase 3 清理时一并移除。

因此，本方案的前提是：不把 harness 当 DAG 的运行时（它不是），而是把 harness 定位成 Chat 的 agentic 运行时，同时让 DAG 和 Chat 共享一套能力底座。

---

## 二、目标架构：两个编排层，一个能力底座

```
            能力底座（共享，唯一出口）
   LLMProvider(ModelRouter) / SkillRegistry / permission_gate
              / Observer->SSE / Memory
                      |
        +-------------+-------------+
        v                           v
  DAG 编排层                    Chat 编排层
  LangGraph + nodes/*.py        AgentHarness + LoopExecutor
  （硬编码路由，确定性管线）      （ReAct，自由 agentic 循环）
```

- DAG 保持现状（生产稳定，不动）。
- Chat 用 harness 的 `LoopExecutor`，这是 harness 真正的用武之地。
- 两者共享能力底座，不共享编排层。

---

## 三、四个待办模块的归属

| 模块 | 现状 | 结论 | 归属 |
|---|---|---|---|
| 上下文系统 | 已有 3 层（任务级 / 任务内 / 长期） | 不新建，补第 4 层「会话级」 | Phase 2 |
| Session 会话日志 | 前端内存态、后端无表 | 真缺，新建 `Session` + `Message` | Phase 2 |
| System Prompt 组装 | 散落在多处 + 死代码 | 缺统一 `PromptAssembler` | Phase 1 |
| Agent 注册与接口 | `configs/*.yaml` 未接线、损坏、缺失 | 用 Python `AgentDef` 定义，yaml 降级为可选覆盖 | Phase 1 |

### 3.1 三个记忆层级（命名统一）

| 层级 | 现名 | 建议名 | 生命周期 |
|---|---|---|---|
| 任务级上下文 | `WorkflowContext` | `TaskContext` | 单次节点执行 |
| 会话级上下文 | 无 | `SessionContext` | 一次 Chat 会话 |
| 长期记忆 | `agent_memory` | `UserMemory` | 跨工作流持久化 |

---

## 四、三条收敛动作

### 收敛 1：模型层二合一

关键事实：
- `BaseLLM.chat(messages) -> dict` 与 `LLMProtocol.chat(messages) -> dict` 签名完全一致。
- 9 个 DAG 节点已是 dict 风格调用（`llm.chat(messages)` → `resp.get("content")`），不依赖 LangChain `ainvoke`，因此不需要 LangChain 桥接。
- LangChain 依赖仅存在于 `ModelRouter._get_adapter()` 死代码内部，Phase 3 清理。

收敛方式：
- `get_deepseek_llm()` 签名不变，内部委托 `ModelRouter.resolve_llm(model, temperature)`。
- `resolve_llm()` 返回具体的 `BaseLLM`（如 `DeepSeekAdapter`），不是 router 本身。
- 顺手修 `_get_adapter()` 中 `DeepSeekAdapter(model=...)` 未传 `api_key` 的 bug。
- 保留无 `api_key` 时返回 `None` 的降级行为。

`DeepSeekAdapter` / `QwenVLAdapter` / `ImageGenAdapter` 降级为 router 内部 provider，统一由 `ModelRouter` 解析。

### 收敛 2：工具层三合一

`Skill` 增加 `execution_policy: direct | mcp | sandbox`，`SkillRegistry` 统一登记内置 / MCP / 第三方插件三类能力。

### 收敛 3：安全层二合一

沙箱/信任决策并入 `permission_gate.require()`，删除 `sandbox_workflow_bridge` 的独立判断。

---

## 五、分阶段执行计划

### Phase 0 — 契约固化（行为不变，约 1 周）

目标：纯接口对齐，不改变 DAG 行为。拆成 3 个子步骤，每步只动一个子系统，每步跑回归。

- Phase 0a（模型层，已落地）：`model_router.py` 实现 `LLMProtocol`
- Phase 0b（工具层，已落地）：`skills/base.py` 增加 `execution_policy`
- Phase 0c（安全层，移至 Phase 3）：`permission_gate` 并入沙箱/信任决策

验收：
- 0a：`ModelRouter` 作为 `LLMProtocol` 跑通单测（`isinstance(ModelRouter(), LLMProtocol)` 为真）
- 0b：`Skill.execution_policy` 默认 `direct`，子类可覆盖
- `app.agents.nodes` / `app.agents.harnesses.factory` 正常 import（DAG 行为不变）

### Phase 1 — Agent 注册 + Prompt 组装 + 输入理解（约 1-2 周）

目标：把死代码接上电，为 Chat 提供 Agent 定义、Prompt 组装、意图解析与输入守卫。

关键决策：
- Agent 定义用 Python `AgentDef`（Pydantic），`configs/*.yaml` 降级为可选覆盖层，不修损坏的中文 yaml。
- `IntentParser`（理解，返回 `ParsedIntent`）与 `ChatInputRule(HardRule)`（守卫，返回 bool）分离，不混用。
- Observer→SSE 桥接复用现有 `harnesses/factory.py::_make_observer()`，不新建事件类型。
- 模型路由与 Prompt 组装分离：`AgentRegistry.build_harness()` 通过 `agent_def.llm_model` 锁定具体模型，harness 的 `llm` 是具体 `BaseLLM`，不存在 `task_type` 丢失问题；`ModelRouter` 的自动路由（按 `task_type`）只留给 Phase 2 无 `AgentDef` 的通用 chat 场景；`PromptAssembler` 只管拼 prompt 字符串，与模型路由无关。

#### Task 1：`get_deepseek_llm()` 收敛到 `ModelRouter.resolve_llm()`

- 改动：`get_deepseek_llm()` 签名不变，内部委托 `ModelRouter.resolve_llm(model, temperature)`，返回具体 `BaseLLM`（不是 router）。
- 改动：`ModelRouter` 新增 `resolve_llm()`，修 `_get_adapter()` 中 `DeepSeekAdapter` 缺 `api_key` 的 bug。
- 验收：9 个 DAG 节点零改动；`None` 降级保留；`resolve_llm()` 返回具体 `BaseLLM` 单测通过。

#### Task 2：`AgentRegistry` + `AgentDef`

- 改动：新 `backend/app/agents/registry.py`，用 Python `AgentDef`（Pydantic）定义 `BUILTIN_AGENTS`，yaml 降级为可选覆盖。
- 验收：`AgentRegistry` 能按 `agent_id` 构建任意 agent；`build_harness()` 通过 `agent_def.llm_model` 锁定具体模型。

#### Task 3：`PromptAssembler`

- 改动：新 `backend/app/agents/prompt_assembler.py`，统一组装 persona + mode + user_memory + session context + skill 描述。
- 验收：`PromptAssembler` 能产出完整 system prompt 单测通过；不涉及模型路由。

#### Task 4：输入理解（`IntentParser` + `ChatInputRule`）

- 改动：新 `intent_parser.py`（理解，返回 `ParsedIntent`）+ 新 `input_rules.py`（`ChatInputRule(HardRule)`，做 prompt injection / 长度 / 敏感词守卫）。
- 验收：`IntentParser` 与 `ChatInputRule` 职责分离，接口不混用。

#### Task 5：Observer→SSE 桥接

- 改动：复用 `harnesses/factory.py::_make_observer()`，把 Observer 事件接到 `sse_bus.publish()`。
- 验收：`agent_thinking` / `tool_call` / `recovery` / `circuit_open` 事件流向前端。

### Phase 2 — Session + 上下文 + Chat 最小闭环（约 1-2 周）

目标：Chat 具备持久化会话、多轮上下文、可运行的 agentic 循环。

关系模型（先定）：
```
Session 1──* Message 1──0..1 Workflow
                        (message.agent_meta.workflow_id)
```
- 一个 Session 可触发多个 Workflow；关系通过 Message 间接建立，不加 `workflow.session_id` 外键。
- 追问时，从上一条 assistant Message 的 workflow_id 查 `WorkflowState.outputs`，注入新 Workflow 的 `WorkflowContext.upstream_outputs`。

改动文件：
- 新 `Session` / `Message` 数据表 + `api/routers/session.py`
- 新 `backend/app/agents/context.py`：`SessionContext`（会话级上下文，第 4 层）
- 新 `backend/app/agents/chat_agent.py`：`ChatAgent = AgentHarness(executor=LoopExecutor, ...)`
- 新 `backend/app/api/routers/chat_agent.py`：薄封装
- 改 `backend/app/services/sse_bus.py`：+2 事件 `intent_parsed` / `agent_chat_error`
- 新前端 `RecoveryStatusCard` / `RecoveryDecisionCard`

验收：
- 自然语言「帮我写一篇关于 AI 教育的小红书文章」跑通
- `tool_call_start/end`、`decision_made`、`agent_thinking` 流式到前端
- `recovery_attempt` 显示「正在重试」，`circuit_open` 显示「服务过载」，`Supervisor` 结构性恢复显示决策卡
- 会话刷新后可恢复
- LoopExecutor 用 mock LLM 冒烟跑通（失败 → 重试 → 切模型 → 兜底）

### Phase 3 — 多轮 + 单步 + 清理重复（约 1-2 周）

目标：支持追问、单步复用，删除重复入口。

改动文件：
- 改 `backend/app/agents/context.py`：会话级记忆打通 `WorkflowState.user_memory`
- 改 `backend/app/agents/skills/registry.py`：注册单步 Skill
- 改 `backend/app/agents/chat_agent.py`：`ChatAgent` 作为 single_step 入口（LoopExecutor）
- 改 `backend/app/api/routers/chat_agent.py`：统一 chat 分支响应格式（SSE 流 vs JSON）
- 改 `backend/app/agents/registry.py`：`build_harness()` 装配已有 Skill（trending_search / xhs_search / xhs_publish / vl_analyze）
- 改 `backend/app/agents/skills/permissions.py`：并入沙箱/信任决策
- 改 `backend/app/core/sandbox/sandbox_workflow_bridge.py`：移除独立信任判断
- 改 `backend/app/core/sandbox/` + `node_registry` + `plugin_manager`：执行路径合并

验收：
- 「换个风格」读上下文重跑
- 单步 Skill 在 DAG 与 Chat 两处复用
- 模型/工具/安全/记忆各只有一条唯一出口

---

## 六、红线（不可违背）

1. 重试/路由/最大迭代次数硬编码，不让 LLM 决策。
2. Harness 不 import LangGraph / FastAPI，只依赖协议，保持可独立测试。
3. 每次 `build_*_harness` 返回新实例，避免跨 workflow 共享 memory。
4. DAG 的确定性节点（copywrite/publish）不引入 LLM Loop。

---

## 七、验收标准矩阵

| 维度 | 标准 |
|---|---|
| 协议内聚 | 新增模型 / Skill / Agent / 插件，只改注册表，不改主流程 |
| 单一出口 | 模型只走 `LLMProtocol`，能力只走 `Skill`，安全只走 `permission_gate` |
| 行为不变 | Phase 0 前后 9 节点 DAG 回归一致 |
| 会话持久 | Session 刷新可恢复，多轮可关联 |
| 可回滚 | 每阶段独立提交，可单独 revert |

---

## 八、测试策略

1. 单元：协议契约（`ModelRouter` 实现 `LLMProtocol`、`ModelRouter.resolve_llm()` 返回 `BaseLLM`、`Skill.execution_policy`、`AgentRegistry` 加载、`PromptAssembler` 组装、`permission_gate` 沙箱决策）。
2. 集成：mock LLM 跑通 search -> analyze -> copywrite -> publish。
3. 端到端：Chat 自然语言触发，验证流式事件与发布。
4. 回归：每阶段跑全量现有测试。

---

## 九、风险与回滚

| 风险 | 应对 |
|---|---|
| 收敛破坏现有工作流 | Phase 0 行为不变，回归测试为门禁 |
| harness 定位错误 | 明确 harness 只服务 Chat，不碰 DAG |
| yaml 中文损坏 | 不修 yaml，用 Python `AgentDef` 替代，yaml 降级为可选覆盖 |
| Session 与 workflow/memory 混淆 | 三个生命周期分表，不合并 |

每阶段单独分支，验收失败即回滚该阶段。

---

## 十、里程碑

| 阶段 | 周期 | 交付物 | 状态 |
|---|---|---|---|
| Phase 0 契约固化 | 1 周 | 四条协议 + 单测 | ✅ 已完成 |
| Phase 1 Agent + Prompt | 1-2 周 | AgentRegistry + PromptAssembler | ✅ 已完成 |
| Phase 2 Chat 底座 | 1-2 周 | Session + SessionContext + ChatAgent + 端到端闭环 | ✅ 已完成 |
| Phase 3 清理 + 多轮 | 1-2 周 | 唯一出口 + 单步复用 | ✅ 已完成 |

---

## 十一、遗留项（不阻塞）

| # | 遗留项 | 状态 | 说明 |
|---|---|---|---|
| 1 | `docker_sandbox.py` | ✅ 已删 | 孤儿死代码 + 语法错误，已随 `sandbox_workflow_bridge.py` 一并清理 |
| 2 | 纯 chat 兜底前端接线 | ✅ 已完成 | 前端 Agent 模式收到 `status=chat` 时移除占位并走 `/chat/completions` 流式 |
| 3 | DB 集成测试 | 缺 | `get_last_workflow_id()` 等持久化逻辑在真实 MySQL 下未验证（当前 40 个单测是纯逻辑） |
| 4 | 前端 RecoveryStatusCard / RecoveryDecisionCard | ✅ 已完成 | 组件、条件渲染、Agent 模式开关、SSE 订阅、`handleWorkflowEvent`（含 recovery_attempt / circuit_open 等映射）均已接 |
| 5 | full_pipeline 双路径 | ✅ 已实现 | `full_pipeline` 走 DAG；`explore` 走多 Skill LoopExecutor（search + analyze）。`CopywriteSkill` 留 Phase 4 |

---

*文档结束。*
