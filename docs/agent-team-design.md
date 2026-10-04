# Agent Team 设计哲学与改造方案

> 基于 Claude Code 和 Codex CLI 的子 Agent 架构研究，结合本项目现状的改造方案。

---

## 一、行业标杆研究

### 1.1 Claude Code 三层架构

Claude Code 的多 Agent 系统是三层递进的：

```
┌─────────────────────────────────────────────────┐
│  Layer 3: Coordinator Mode (团队级)              │
│  一个 lead 指挥 N 个 worker，4 阶段流水线        │
│  特征：lead 不干活，只规划+分派+汇总               │
│  触发：CLAUDE_CODE_COORDINATOR_MODE=1            │
├─────────────────────────────────────────────────┤
│  Layer 2: Custom Subagents (角色级)              │
│  .claude/agents/*.md 声明式角色定义               │
│  特征：description 字段驱动自动路由               │
├─────────────────────────────────────────────────┤
│  Layer 1: Task/Agent Tool (原子级)               │
│  主对话中 LLM 自主调用 Agent tool spawn           │
│  特征：3 个抽象信号驱动判断                        │
└─────────────────────────────────────────────────┘
```

### 1.2 Layer 1：三个抽象信号（核心设计哲学）

Claude Code 不给 LLM 写死场景，而是给 3 个抽象判断维度：

| 信号 | 判断问题 | 本质 | 典型但不限于 |
|------|----------|------|-------------|
| **Context Gathering** | 搜索空间大、答案小？ | 子 Agent 吸收大量原始信息，返回摘要 | 读 50 个文件理解架构、探索代码库 |
| **Multiple Independent Tasks** | 子任务之间无依赖？ | 并行执行，3 个同时跑 ≈ 快 3 倍 | 多文件修 bug、多组件更新模式 |
| **Fresh Perspective** | 需要无偏见的独立视角？ | 子 Agent 不继承主对话的假设和偏见 | 代码审核、方案验证、第二意见 |

**关键设计决策**：
- 这 3 个信号是**维度**不是**场景**。"无依赖的并行子任务"适用于任何领域
- LLM 自己判断当前任务命中了哪个维度，**不是规则引擎替它决策**
- 子 Agent **不继承对话历史**，只拿 task description + 工具集 + 干净的 system prompt

### 1.3 Layer 2：Custom Subagents — 声明式角色 + description 驱动路由

这是 Claude Code 最精妙的设计——**触发机制是语义匹配，不是规则触发**。

#### 定义格式

```markdown
---
name: security-reviewer
description: Security vulnerabilities and dependency risks. Use proactively after significant code changes.
tools: Read, Grep, Glob
model: haiku
permissionMode: plan
---

You are a security reviewer. Focus on:
- Input validation gaps
- Dependency vulnerabilities
- Authentication bypass risks
Return a structured finding list.
```

#### 触发机制

```
用户输入 → LLM 读取所有 subagent 的 description 字段
         → 语义匹配：当前任务是否命中某个 description？
         → 命中 → 自动 spawn 该 subagent
         → 未命中 → 主对话自己处理
```

**核心洞察**：
- `description` 字段是**路由规则**，不是文档注释。LLM 拿它做语义匹配来决定是否委托
- **"Use proactively"** 这种显式提示词会显著提高自动触发率
- 模糊的 description（如"helps with code"）几乎不会触发；精确的 description（如"security vulnerabilities after dependency changes"）会可靠触发
- **定义的角色越多、description 越精确，LLM 的委托路由就越智能**

#### 角色的 6 个约束维度

| 维度 | 作用 | 设计哲学 |
|------|------|----------|
| `name` | 唯一标识 | LLM 用它引用角色 |
| `description` | 路由规则 | 语义匹配的输入 |
| `tools` | 能力边界 | 最小权限原则——explorer 不该有 Write |
| `disallowedTools` | 显式禁止 | 黑名单补充白名单 |
| `model` | 成本控制 | 探索用 haiku 省钱，推理用 opus 质量高 |
| `permissionMode` | 安全沙箱 | plan=只读, dontAsk=静默拒绝, acceptEdits=自动写 |

### 1.4 Layer 3：Coordinator Mode — 4 阶段流水线

```
Research ──→ Synthesis ──→ Implementation ──→ Verification
(并行探索)    (汇总理解)    (并行实现)       (并行验证)
```

| 阶段 | 谁干 | 怎么干 |
|------|------|--------|
| Research | N 个 worker 并行 | 各自独立探索不同区域 |
| Synthesis | coordinator 独自 | 读取所有 worker 的发现，合成精确规格 |
| Implementation | N 个 worker 并行 | 按 coordinator 的规格各自实现 |
| Verification | N 个 worker 并行 | 证明代码能跑，不是走过场 |

**3 个关键设计**：
1. **Hub-and-Spoke**：coordinator 是中心，worker 之间**互相不可见**，只能跟 coordinator 通信
2. **编排逻辑是 prompt 不是代码**：coordinator 的行为完全由 system prompt 定义，不是硬编码的 DAG
3. **Git Worktree 隔离**：每个 worker 在独立的 git worktree 里干活，不会互相冲突

### 1.5 安全门控：3 层检查

```
Spawn 时 → 评估 task description，危险任务直接拒绝
运行中 → 每个动作过分类器，和主会话同规则
返回时 → 分类器审查完整操作历史，有疑虑则拦截
```

### 1.6 成本哲学

Claude Code 的设计隐含了一个成本不等式：

```
spawn 开销 = 新上下文构建 + token 消耗 + 延迟 + 上下文切换
收益     = 并行加速 + 上下文隔离 + 新视角

只有 收益 >> 开销 时，才值得 spawn
```

不该 spawn 的信号：
- 单一工具能完成的小任务
- 严格顺序依赖的流水线
- 任务已经足够简单，串行更快
- 上下文窗口还有余量，不需要隔离

---

### 1.7 Codex CLI 对比

Codex 的设计更工程化，核心差异：

| 维度 | Claude Code | Codex CLI |
|------|-------------|-----------|
| 触发判断 | LLM 自主（3 个抽象信号） | LLM 自主 + 角色匹配 |
| 委托模式 | 隐式（description 语义匹配） | 显式 3 档（disabled / explicit / proactive） |
| 角色定义 | .claude/agents/*.md 声明式 | agents/*.toml 声明式 |
| 内置角色 | 无（用户自定义） | default / worker / explorer |
| 并发控制 | 无显式限制 | max_threads=6, max_depth=1 |
| 隔离方式 | 独立对话链 | 独立线程 + 独立 git worktree |
| 编排方式 | prompt 驱动 | prompt 驱动 + token budget |

**Codex proactive 模式的触发条件**：
1. 任务匹配了某个已定义 Agent 的 description → spawn 那个 Agent
2. 批量任务可并行化 → spawn worker 池
3. **parallel work would materially improve speed or quality** — 核心词是 materially（显著地），不是微小的优化

---

## 二、本项目现状

### 2.1 已有的基础设施

| 组件 | 文件 | 状态 |
|------|------|------|
| AgentManager | engine/collab/agent_manager.py | ✅ 层级树、spawn、状态追踪 |
| InterAgentBus | engine/collab/message_bus.py | ✅ 消息总线、收件箱 |
| ConcurrencyPool | engine/collab/concurrency_pool.py | ✅ asyncio.Semaphore 并发控制 |
| CollaborationTools | engine/collab/tools.py | ✅ 6 个 LLM 可调用工具 |
| CollabMode | agent_manager.py | ✅ EXPLICIT / PROACTIVE / DISABLED |
| AgentRegistry | agents/registry.py | ✅ 声明式 AgentDef + BUILTIN_AGENTS |
| Persistence | engine/collab/persistence.py | ✅ Redis 持久化 |

### 2.2 当前 AgentDef 定义

```python
class AgentDef(BaseModel):
    agent_id: str
    role: str = ""
    llm_model: str | None = None
    skills: list[str] | None = Field(default=None)
    executor: str = "single_shot"
    hard_rules: list[str] = Field(default_factory=list)
    soft_semantic: dict[str, Any] | None = None
    recovery: dict[str, Any] = Field(default_factory=dict)
    max_iterations: int = 4
    prompt_template: str = ""
```

### 2.3 当前 spawn_agent 工具

```python
class SpawnAgentInput(BaseModel):
    task_name: str
    task_description: str
    role: str | None = None
    agent_id: str | None = None  # 引用已注册智能体 ID
```

### 2.4 当前协作 prompt（chat_agent.md 末尾）

```
协作：多主题 spawn 并行 + wait_agent，单任务直接用工具。
可引用：search/analyze/copywrite/explore/publish
```

---

## 三、Gap 分析

对比 Claude Code 的设计哲学，逐项找差距：

### 3.1 触发机制：硬编码 vs 抽象维度

| Claude Code | 本项目 | 差距 |
|-------------|--------|------|
| 3 个抽象信号维度（Context Gathering / Independent Tasks / Fresh Perspective） | 一句"多主题 spawn 并行" | **没有给 LLM 判断维度**，LLM 不知道什么时候该 spawn |
| LLM 自主判断命中哪个维度 | 无判断框架 | LLM 要么不 spawn，要么乱 spawn |

**结论**：需要给 LLM 3 个抽象判断维度，而不是写死场景。

### 3.2 角色路由：description 驱动 vs 手动指定

| Claude Code | 本项目 | 差距 |
|-------------|--------|------|
| 每个 subagent 有 `description` 字段，LLM 语义匹配自动路由 | AgentDef 只有 `role`（中文角色名），无 description | **LLM 无法自动判断该委托给谁** |
| description 是路由规则 | agent_id 需要手动传参 | spawn_agent 的 agent_id 靠 LLM 猜或用户指定 |

**结论**：AgentDef 需要加 `description` 字段，spawn_agent 工具需要把所有可用角色的 description 注入 LLM 上下文。

### 3.3 工具约束：最小权限 vs 全继承

| Claude Code | 本项目 | 差距 |
|-------------|--------|------|
| 每个 subagent 声明 `tools` 白名单 + `disallowedTools` 黑名单 | 子 Agent 继承父 Agent 的全部工具 | **没有能力边界**，搜索 Agent 能发布，发布 Agent 能搜索 |
| explorer 只有 Read/Grep/Glob | 无约束 | 违反最小权限原则 |

**结论**：AgentDef 已有 `skills` 字段，但 spawn 临时子 Agent 时没有约束机制。需要加 `allowed_skills` / `disallowed_skills`。

### 3.4 模型选择：per-agent model vs 继承父模型

| Claude Code | 本项目 | 差距 |
|-------------|--------|------|
| 每个 subagent 可指定 model（haiku/opus/inherit） | 引用已注册智能体时用其 llm_model；临时子 Agent 继承父模型 | **临时子 Agent 无法指定模型** |
| 探索用 haiku 省钱，推理用 opus | 无成本分层 | 简单探索任务也在用大模型 |

**结论**：spawn_agent 需要加 `model` 参数，临时子 Agent 也应能指定模型。

### 3.5 安全门控：3 层检查 vs 无

| Claude Code | 本项目 | 差距 |
|-------------|--------|------|
| spawn 时评估 → 运行中监控 → 返回时审计 | 无 | **子 Agent 无安全边界** |
| permissionMode: plan/dontAsk/acceptEdits | 无 | 任何子 Agent 都能调任何工具 |

**结论**：至少需要 spawn 时的任务评估 + 工具权限约束。

### 3.6 协作模式：默认值

| Claude Code | 本项目 | 差距 |
|-------------|--------|------|
| 默认就是可 spawn 的（Task 工具始终可用） | 默认 EXPLICIT（保守） | **LLM 被告知"只在用户明确要求时才 spawn"** |
| Proactive 是 Codex 的概念 | PROACTIVE 模式存在但未启用 | 需要讨论：默认改 PROACTIVE 还是保持 EXPLICIT |

**结论**：需要拍板——默认模式选哪个。

### 3.7 声明式定义：.md 文件 vs Python dict

| Claude Code | 本项目 | 差距 |
|-------------|--------|------|
| .claude/agents/*.md 文件，可团队共享、版本控制 | BUILTIN_AGENTS Python dict | **用户无法在运行时定义新角色** |
| 前端创建的 Agent 存 DB | 前端已支持创建，但无 description 字段 | 需要前后端都加 description |

**结论**：前端创建 Agent 的表单需要加 `description` 字段。

---

## 四、改造方案（待拍板）

### 4.1 AgentDef 加 description 字段

```python
class AgentDef(BaseModel):
    agent_id: str
    role: str = ""
    description: str = ""  # ← 新增：路由规则，LLM 语义匹配用
    llm_model: str | None = None
    skills: list[str] | None = Field(default=None)
    disallowed_skills: list[str] = Field(default_factory=list)  # ← 新增
    executor: str = "single_shot"
    ...
```

**BUILTIN_AGENTS 需要补 description**，例如：

```python
"search": AgentDef(
    agent_id="search",
    role="爆款搜索专家",
    description="搜索小红书热点、趋势、爆款笔记。当用户需要搜索、查找、调研信息时主动使用。",
    ...
),
"audit": AgentDef(
    agent_id="audit",
    role="合规审核专家",
    description="审核内容合规性，提供独立无偏见的审核视角。当需要检查、审核、验证内容时主动使用。",
    ...
),
```

### 4.2 spawn_agent 工具增强

**SpawnAgentInput 加 model 参数**：

```python
class SpawnAgentInput(BaseModel):
    task_name: str
    task_description: str
    role: str | None = None
    agent_id: str | None = None
    model: str | None = None  # ← 新增：指定子 Agent 模型
```

**spawn_agent 的 description 注入可用角色清单**：

不再硬编码角色列表，而是从 AgentRegistry 动态生成，包含每个角色的 description：

```
Available agents for delegation:
- search: 搜索小红书热点、趋势、爆款笔记。当用户需要搜索、查找、调研信息时主动使用。
- analyze: 分析爆款规律和选题方向。当需要数据分析、趋势洞察时主动使用。
- copywrite: 小红书文案创作。当需要写文案、创作内容时主动使用。
- audit: 审核内容合规性。当需要检查、审核、验证时主动使用。
...
```

### 4.3 chat_agent.md 协作指引重写

用 3 个抽象维度替代场景枚举：

```markdown
## 子 Agent 协作

你拥有 spawn_agent / wait_agent / list_agents 等协作工具。根据以下三个维度自主判断是否需要 spawn 子 Agent：

1. **上下文隔离**：任务需要探索大量信息，但主对话只需要摘要结果？→ spawn 一个子 Agent 去探索，返回精炼结论
2. **并行独立**：任务可拆为多个无依赖的子任务？→ 并行 spawn 多个子 Agent，各自完成后再汇总
3. **独立视角**：需要无偏见的审核或验证？→ spawn 一个子 Agent 从零开始独立判断

成本意识：spawn 有开销（token、延迟、上下文切换）。只有收益显著大于开销时才 spawn。
单一工具能完成的小任务、严格顺序依赖的流水线，不要拆。

委托时：优先引用已注册智能体（agent_id 参数），参考上方可用角色清单。
spawn 后必须 wait_agent 收集结果。
```

### 4.4 协作模式默认值

两个选项：

| 选项 | 行为 | 风险 |
|------|------|------|
| **A: 默认 PROACTIVE** | LLM 主动判断是否 spawn | 可能过度 spawn，token 消耗增加 |
| **B: 默认 EXPLICIT，用户可切换** | 保守，用户明确要求才 spawn | 复杂任务不会自动拆分 |

### 4.5 前端 AgentManager 加 description 字段

创建/编辑 Agent 的表单加一行 `description` 输入框，placeholder 提示"描述何时应委托给此智能体，LLM 会据此自动路由"。

---

## 五、拍板清单

需要确认以下决策点：

1. **AgentDef 加 description？** — 建议加，这是 Claude Code 路由机制的核心
2. **AgentDef 加 disallowed_skills？** — 建议加，最小权限原则
3. **spawn_agent 加 model 参数？** — 建议加，成本控制
4. **协作指引用 3 抽象维度？** — 建议用，替代场景枚举
5. **默认协作模式？** — A (PROACTIVE) 还是 B (EXPLICIT + 可切换)？
6. **前端加 description 输入？** — 建议加
7. **是否需要 Coordinator Mode（Layer 3）？** — 当前建议暂不实现，Layer 1+2 已足够