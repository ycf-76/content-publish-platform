# 渐进式澄清协议（Progressive Clarification Protocol）

> 让 LLM 在拿不准时主动向用户提问，拿到确凿数据再创作——减少返工、节约 token、逼近用户预期。

| 版本 | v2.2-final |
|------|-----------|
| 状态 | 终审通过（事实性错误已修正，设计细节已补全） |
| 日期 | 2026-09-23 |
| 作者 | AI + 产品负责人 |
| 宪法对齐 | C3(ReAct), C5(Skills), C7(SSE) |

---

## 零、问题陈述

### 现状痛点

1. **LLM 自由发挥，用户不知道要什么**：用户说"帮我做一篇小红书图文"，LLM 猜风格、猜受众、猜调性——猜错就返工
2. **返工浪费 token**：一次完整创作链（搜索→分析→文案→图片→审核）消耗大量 token，返工等于全扔
3. **用户参与感弱**：创作过程是黑盒，用户只能等结果出来再改，改了又改
4. **不同领域需求差异大**：小红书图文问"风格调性"，代码生成问"语言框架"，数据分析问"维度指标"——不能硬编码一套问题

### 设计目标

| # | 目标 | 验收标准 |
|---|------|---------|
| G1 | LLM 拿不准时主动问，不猜 | Clarify 门控在 auto-allow 工具上也能正确触发 |
| G2 | 问题由 Skill 自己声明，不硬编码 | 新增 Skill 只需补 clarify 元数据即自动获得澄清能力 |
| G3 | 分批提问，不一次问完 | 每批 3-5 题，按字段依赖图自动分组 |
| G4 | 用户可跳过，不强制 | "跳过"按钮始终可用，走 model_settings → default_config 降级链 |
| G5 | 澄清结果影响创作 | clarification_result 优先级 > model_settings > default_config（仅限当前会话） |
| G6 | 可拓展到任意领域 | 代码生成/数据分析/视频脚本等 Skill 声明 clarify 即可 |
| G7 | LLM 创作中途也能问 | ReAct Loop 中 LLM 可输出 `<needs_clarification>` 触发暂停 |

---

## 一、设计哲学

### 1.1 现有确认机制的真实工作方式（对照代码）

> ⚠️ **v1.0/v1.1 勘误**：之前将确认机制描述为"暂停+恢复"，暗示 LoopExecutor 有优雅的暂停协议。
> 实际上（对照 [loop.py](../backend/app/engine/harness/executor/loop.py)）：

```
确认机制的真实工作方式：

1. LoopExecutor 执行到 Guardian 返回 NEEDS_CONFIRM
2. break 出 for 循环（LoopExecutor 实例即将销毁）
3. final_output 带 _awaiting_confirmation=True + _loop_state_path
4. save_loop_state() → 将 messages 列表序列化到 JSON 文件
5. ChatAgent 检测 _awaiting_confirmation → 返回 ChatResult(status="awaiting_confirmation")
6. API 层返回给前端
7. 前端渲染 ChatConfirmCard
8. 用户确认 → POST /api/v1/chat/confirm
9. 加载 loop_state JSON → 创建新的 LoopExecutor 实例 → 从断点继续执行
```

**关键事实**：
- **LoopExecutor 实例不存活**——暂停时对象就销毁了，没有"暂停等待"的原生抽象
- **恢复是"序列化+重建"**——新 LoopExecutor 实例从 JSON 恢复 messages，从断点继续
- **`_awaiting_confirmation` 是 final_output 的标记**，不是 LoopExecutor 的状态变量
- **恢复不是简单的"追加 observation 然后继续循环"**——批准后 **立即执行被批准的 Skill**，把结果注入对话，再恢复循环。这是为了防止 LLM 反复重新发起同一调用导致无限确认死循环（代码注释明确写了这一点）
- **`_pending_confirmation` 实例变量是同请求内的快捷引用**——跨请求恢复走 `state["pending_skill_call"]`（JSON），这是设计正确的，不是 bug
- **续跑可能再次触发确认**——恢复后循环继续，可能再次遇到高危操作，代码已处理递归场景

### 1.2 核心设计决策：Clarify 不在 Guardian 内部

> ⚠️ **v1.1 致命缺陷**：v1.1 将 Clarify 作为 Guardian 的新 Step 2（在 Auto-allow 之前），
> 但这导致 **架构哲学冲突**：
>
> - Guardian 的设计哲学是"安全门控越快放行越好"——auto-allow 短路是核心优化
> - Clarify 的哲学是"不确定时主动问"——需要拦截并暂停
> - 如果 Clarify 在 Auto-allow 之前，**每个工具调用都要先走 Clarify 判定**，
>   包括 `trending_search` 这种完全不需要澄清的工具——性能退化
> - 如果 Clarify 在 Auto-allow 之后，创作类工具永远走不到
> - **no-policy 默认 ALLOW**：Guardian 对没有策略的 Skill 默认放行（`strict_mode=False`），
>   `prompts/skills/` 下 35 个 PromptDrivenSkill 全部没有 Guardian 策略，全部走 no-policy ALLOW。
>   如果 Clarify 在 Guardian 内部，这些 Skill 永远不触发澄清——而它们恰恰是最需要澄清的
>
> 这不是"修复插入位置"能解决的——是两个机制的根本矛盾。

**v2.0 决策：Clarify 是 LoopExecutor 的独立前置步骤，不在 Guardian 内部。**

```
LoopExecutor._execute_tool_call 的执行流（v2.0）：

  ┌─────────────────────────────────────────┐
  │ Step 0: Clarify 前置检查（新增）        │
  │   检查 Skill.clarify_meta               │
  │   if 需要澄清 → break + save + SSE 推送 │
  │                 → return (和确认同构)    │
  │   else → 继续                           │
  └──────────────┬──────────────────────────┘
                 │ 不需要澄清
                 ▼
  ┌─────────────────────────────────────────┐
  │ Step 1: Guardian.check()（不变）        │
  │   Policy → Auto-allow → Validate →     │
  │   Permission → Confirm                  │
  └─────────────────────────────────────────┘
```

**优势**：
- **不修改 Guardian 任何代码**——零侵入
- **不增加 auto-allow 路径的延迟**——不需要澄清的工具直接跳过 Step 0
- **no-policy Skill 也能触发澄清**——ClarifyGate 检查 `Skill.clarify_meta`，不依赖 Guardian 策略
- **完全复用确认机制的暂停/恢复模式**——break → save_loop_state → SSE → API → 新 LoopExecutor 实例
- **Clarify 和 Confirm 不会冲突**——Clarify 在 Guardian 之前，Confirm 在 Guardian 之内，串行执行

### 1.3 与宪法对齐

| 宪法条款 | 对齐方式 |
|---------|---------|
| C3 ReAct 自主循环 | LLM 在 Loop 中可自主触发 `<needs_clarification>` |
| C5 Skills 解耦 | 每个 Skill 自声明 clarify 元数据，系统不替它猜 |
| C7 SSE 实时推送 | 澄清卡片走现有 SSE 事件通道 |

---

## 二、架构设计

### 2.1 整体流程

```
用户输入 "帮我做一篇小红书图文"
        │
        ▼
┌──────────────────────────────────────────────────────┐
│  LoopExecutor 主循环                                  │
│                                                      │
│  ┌─ Step 0: Clarify 前置检查 ─────────────────────┐  │
│  │  遍历即将调用的 Skill.clarify_meta              │  │
│  │  收集待澄清字段 → 按依赖图分批                    │  │
│  │  if 需要澄清:                                   │  │
│  │    break + save_loop_state                      │  │
│  │    final_output._awaiting_clarification = True  │  │
│  │    SSE 推送 agent_clarification_required        │  │
│  │    return (LoopExecutor 实例销毁)                │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Step 1: Guardian.check() (不变) ──────────────┐  │
│  │  Policy → Auto-allow → Validate →              │  │
│  │  Permission → Confirm                           │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Step 2: Skill.execute() ──────────────────────┐  │
│  │  读取 clarification_result (最高优先级)         │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘

        用户回答 → POST /api/v1/chat/clarify
        │
        ▼
┌──────────────────────────────────────────────────────┐
│  /chat/clarify API 处理                               │
│  1. 加载 loop_state JSON                              │
│  2. 合并本批回答到 clarified_answers                   │
│  3. 判断是否还需追问                                   │
│     ├─ 是 → SSE 推送下一批 → 等待                    │
│     └─ 否 → 编译 clarification_result                 │
│            → 写入 WorkflowState                        │
│            → 创建新 LoopExecutor 实例                  │
│            → 从断点继续执行                             │
└──────────────────────────────────────────────────────┘
```

### 2.2 Clarify 前置检查的完整链路

> ⚠️ **v1.1 问题修复**：v1.1 只描述了 Guardian 内部的逻辑，没有描述从 LoopExecutor
> 到 ChatAgent 到 API 到前端的完整链路。v2.0 补全。

```
完整链路（与确认机制同构）：

1. LoopExecutor._execute_tool_call()
   → Step 0: 检查 Skill.clarify_meta
   → 发现待澄清字段
   → break 出循环

2. LoopExecutor.run() 的 final_output 组装
   → final_output._awaiting_clarification = True
   → final_output._clarification_batch = ClarificationBatch(...)
   → final_output._loop_state_path = save_loop_state(...)

3. ChatAgent.process() 检测 final_output
   → if final_output.get("_awaiting_clarification"):
   →     return ChatResult(
              status="awaiting_clarification",
              clarification_batch=final_output["_clarification_batch"],
              loop_state_path=final_output["_loop_state_path"],
          )

4. API 层 (chat_agent.py router)
   → 将 ChatResult 返回给前端
   → 前端收到 status="awaiting_clarification"

5. 前端 SSE 事件
   → sse_bus.emit("agent_clarification_required", batch.model_dump())

6. 前端渲染
   → useChatSSE.ts 收到事件 → 创建 ChatMessage(agentMeta.workflowStatus="awaiting_clarification")
   → ChatView.vue 根据 workflowStatus 路由到 ChatClarificationCard

7. 用户回答 → POST /api/v1/chat/clarify
   → 加载 loop_state → 合并回答 → 判断追问或 resume

8. 澄清恢复时（和确认恢复同构）：
   a. 从 loop_state 加载 pending_clarification（待执行的 Skill 调用信息）
   b. 将澄清结果 **合并到 pending_clarification.arguments** 中
   c. **立即执行该 Skill**（和确认恢复的"批准后立即执行"同构）
   d. 把执行结果注入对话
   e. 创建新 LoopExecutor 实例（iteration 补偿 1 次）→ 从断点继续

9. 续跑可能再次触发澄清（递归场景）：
   → API 层检测 output._awaiting_clarification
   → 返回新的 awaiting_clarification 状态 + 新的 ClarificationBatch
   → 前端渲染新的 ClarificationCard（和确认的递归场景同构）
```

### 2.3 Clarify 前置检查的判定逻辑

```
在 LoopExecutor._execute_tool_call() 的最开始：

1. 获取即将调用的 Skill 实例
2. 检查 Skill.clarify_meta 是否非空
3. 如果非空，遍历每个字段：

   if value is None/empty AND field.clarify_when == "missing":
       → 加入待澄清列表

   if value is ambiguous AND field.clarify_when == "ambiguous":
       → 加入待澄清列表（ambiguous 判定见 2.3.1）

   if field.clarify_when == "always":
       → 加入待澄清列表

4. 待澄清列表非空 → 触发澄清（break + save + SSE 推送）
5. 待澄清列表为空 → 继续进入 Guardian.check()
```

> ⚠️ **v2.2 when=always 去重**：`when=ClarifyWhen.always` 的字段在每次 Skill 调用时都会触发澄清，
> 但同一 session 内如果某字段已通过澄清获得值，后续调用不应重复提问（否则 audit Skill 每次都问"审核标准是什么？"）。
> **修复**：Step 0 检查 `clarified_answers` 中是否已有该字段的值——如果有，跳过；
> 如果用户想修改，通过 UI 的"修改澄清结果"入口（Q3）主动触发。
```

**性能保障**：如果 Skill 没有 clarify_meta（大多数工具如 trending_search、vl_analyze），Step 0 在 O(1) 内跳过，零延迟。

> ⚠️ **v2.2 触发阈值**：ReAct 模式下"收集所有已注册 Skill 的 clarify_meta → 首次调用前全部问完"
> 可能导致搜索/分析类请求也触发大量澄清问题。**修复**：Step 0 增加前置条件判断：
> - **意图过滤**：只有当用户输入匹配创作类 `trigger_words`（或 LLM 意图解析为创作类）时，才触发澄清
> - **搜索/分析类请求不触发**：`trending_search`/`xhs_search`/`vl_analyze`/`analyze` 等工具调用跳过 Step 0
> - **阈值配置**：`CLARIFY_TRIGGER_INTENTS = {"create", "write", "design", "generate"}`，可扩展

#### 2.3.1 Ambiguous 判定策略

**采用规则优先 + LLM 辅助的混合策略**：

| 层级 | 机制 | 适用场景 | 延迟 |
|------|------|---------|------|
| L1 规则 | 关键词/长度启发式 | 用户输入 < 10 字且包含"帮我做/写/生成"等泛化词 | 0ms |
| L2 规则 | 字段值存在但明显不充分 | topic 存在但 style/audience 为空 | 0ms |
| L3 LLM | 轻量 LLM 判断语义充分性 | 规则无法判定时 | ~200ms |

**L3 LLM 规格**：

```
模型: 与当前 Loop 相同的 LLM（复用连接，不额外配置）
Prompt: "判断以下用户输入对'{field_name}'字段是否足够明确。只需回答 SUFFICIENT 或 INSUFFICIENT。\n用户输入：{user_input}\n已有回答：{existing_answers}"
缓存: 同一 session 内相同输入缓存判定结果（LRU，上限 50 条）
超时: 2s，超时视为 SUFFICIENT（宁可漏问也不卡住）
```

### 2.4 Skill 的 clarify_meta 声明机制

> ⚠️ **v1.1 问题修复**：v1.1 说"clarify_meta 作为 Skill 的独立类属性"，
> 但 PromptDrivenSkill 的 `_create_skill_class` 创建的 `_DynamicSkill` **没有 clarify_meta 属性**，
> 方案没有说明注入到哪里。v2.0 明确。

> ⚠️ **v2.0 补充**：项目有两种 Skill 类型，澄清元数据注入方式不同：
> - **Python Skill**（copywrite/image_gen 等）：有独立的 Input Schema（如 `CopywriteInput`），
>   clarify_meta 声明为 **类属性**
> - **PromptDrivenSkill**（35 个 .md Skill）：共享 `_InputSchema`，
>   clarify_meta 从 **frontmatter 解析后动态注入为类属性**

#### 2.4.1 Python Skill 的 clarify_meta 声明

```python
class CopywriteTool(Tool):
    name = "copywrite"
    clarify_meta: dict[str, ClarifyFieldMeta] = {
        "topic": ClarifyFieldMeta(
            hint="这篇图文的核心主题是什么？",
            when=ClarifyWhen.missing,
            options=[
                ClarifyOption(label="技能/干货分享", value="skill_share"),
                ClarifyOption(label="产品种草推荐", value="product_recommend"),
                ClarifyOption(label="生活经验/避坑", value="life_experience"),
                ClarifyOption(label="情感/观点表达", value="emotion_opinion"),
            ],
        ),
        "style": ClarifyFieldMeta(
            hint="文案风格偏好？",
            when=ClarifyWhen.ambiguous,
            options=[
                ClarifyOption(label="口语化闺蜜感", value="casual"),
                ClarifyOption(label="专业干货感", value="professional"),
                ClarifyOption(label="故事叙事感", value="narrative"),
                ClarifyOption(label="清单攻略体", value="listicle"),
            ],
        ),
        "audience": ClarifyFieldMeta(
            hint="目标受众是？",
            when=ClarifyWhen.missing,
            options=[
                ClarifyOption(label="学生党", value="student"),
                ClarifyOption(label="职场新人", value="junior_worker"),
                ClarifyOption(label="宝妈", value="mom"),
                ClarifyOption(label="通用", value="general"),
            ],
        ),
    }
```

#### 2.4.2 PromptDrivenSkill 的 clarify_meta 声明

在 `.md` frontmatter 中声明 `clarify_schema`，由 `_register_single_md` 解析后注入到动态创建的 Skill 类的类属性上：

```yaml
---
node_type: produce
name: xhs_note_creator
display_name: 小红书笔记创作
clarify_schema:
  topic:
    hint: "这篇图文的核心主题是什么？"
    when: missing
    options:
      - label: "技能/干货分享"
        value: "skill_share"
      - label: "产品种草推荐"
        value: "product_recommend"
  style:
    hint: "文案风格偏好？"
    when: ambiguous
    options:
      - label: "口语化闺蜜感"
        value: "casual"
      - label: "专业干货感"
        value: "professional"
  visual_style:
    hint: "视觉风格偏好？"
    when: ambiguous
    options:
      - label: "极简白底"
        value: "minimal_white"
        preview: "/previews/minimal.png"
      - label: "暖色奶油"
        value: "warm_card"
        preview: "/previews/warm.png"
---
```

**`prompt_skills.py` 的 `_register_single_md` 扩展**：

```python
# 在 _create_skill_class 中：
# 1. 解析 frontmatter 的 clarify_schema（如果存在）
# 2. 用 ClarifyFieldMeta.from_dict() 转换为 dict[str, ClarifyFieldMeta]
# 3. 赋值给动态类的类属性：DynamicSkillClass.clarify_meta = parsed_meta
# 4. 如果 frontmatter 没有 clarify_schema → DynamicSkillClass.clarify_meta = {}
# 5. try-except 包裹：解析失败 → clarify_meta = {}，不影响 Skill 注册
```

**关键**：`clarify_meta` 是 Skill 类的独立类属性（在 Tool 基类中声明默认值 `{}`），与 `input_schema` 正交。不需要修改共享的 `_InputSchema`。

### 2.5 分批策略：按字段依赖图分组

#### 2.5.1 字段依赖图

```
字段间的依赖关系由 ClarifyFieldMeta.depends_on 声明：

  audience ──depends_on──→ topic        （选了主题才能问受众）
  style ──depends_on──→ topic           （选了主题才能问风格）
  visual_style ──depends_on──→ style    （选了文案风格才能问视觉风格）
  layout ──depends_on──→ visual_style   （选了视觉风格才能问布局）
```

**依赖图推导分批**：

```
Batch 0: 无依赖的字段（topic）
Batch 1: 依赖 Batch 0 的字段（audience, style）
Batch 2: 依赖 Batch 1 的字段（visual_style）
Batch 3: 依赖 Batch 2 的字段（layout）
```

#### 2.5.2 ReAct 模式 vs DAG 模式的分批差异

| 模式 | 分批策略 | 原因 |
|------|---------|------|
| ReAct | 一次性收集所有可能调用的 Skill 的 clarify_meta → 按字段依赖图分批 → 在首次 Skill 调用前全部问完 | LLM 运行时才决定调哪个 Skill，无法预判执行顺序 |
| DAG | 按 DAG 节点顺序分批 → 每个节点执行前问该节点的 clarify 字段 | DAG 执行顺序确定，可以逐节点澄清 |

> ⚠️ **v1.1 问题修复**：v1.1 说"从 AgentDef.skills 列表获取 Skill 调用顺序"，
> 但 `chat_agent` 的 `skills=None`（全量加载），实际加载的 Skill 还受 `creation_type` 影响。
> v2.0 的分批策略**不依赖 AgentDef.skills**，而是：
> - ReAct 模式：收集当前 session 所有已注册 Skill 的 clarify_meta（不区分是否会被调用）
> - 只收集 clarify_meta 非空的 Skill，忽略无澄清需求的工具
> - 字段去重：多个 Skill 声明同一字段的 clarify_meta 时，取第一个（按 Skill 注册顺序）

#### 2.5.3 depends_on 语义

```python
class ClarifyFieldMeta(BaseModel):
    depends_on: list[ClarifyDepends] = []
    # 多个依赖条件之间为 AND 关系（全部满足才显示）
    # 不支持 OR / 嵌套（Phase 1 保持简单）

class ClarifyDepends(BaseModel):
    field: str    # 依赖的字段名
    value: str    # 依赖字段需要等于的值（精确匹配）
    # 未来可扩展: operator: str = "eq"  # eq / in / not_eq
```

**循环依赖检测**：在构建依赖图时做拓扑排序，如果检测到环 → fallback 到不分批（一次问完）。

### 2.6 ClarificationResult 注入 WorkflowState

**扩展**：新增两个字段。

```python
class WorkflowState(TypedDict, total=False):
    # ... 现有字段保持不变 ...
    clarification_result: dict          # 澄清阶段收集的用户明确选择（仅当前会话生效）
    # key = 字段名, value = 用户选择的值
    clarified_answers: dict             # 服务端维护的逐批累积回答
    # 结构: {batch_id: {question_id: answer_value}}
```

**各节点读取优先级链**：

```
clarification_result  >  model_settings  >  Skill.default_config  >  系统默认
```

> ⚠️ **v2.1→v2.2 勘误**：
>
> **1. creative_state 是 session 级，不是 workflow 级**：`creative_state` 绑定在 `ChatSession` 上，
> 一个 session 可以有多个 workflow（用户多次发消息）。如果澄清结果写入 `creative_state`，
> workflow A 中澄清的 `writing_style: "casual"` 会被 workflow B 读到——跨工作流污染。
>
> **2. ~~Chat 模式没有 model_settings~~（已修正）**：v2.1 断言"Chat 模式没有 model_settings"是**错误的**。
> 实际代码中 `ChatRequest.model_settings` 字段存在（chat_agent.py L198），
> 通过 `context.extra["model_settings"]` 传递给 Skill（chat_agent.py L590-591），
> Skill 通过 `context.extra.get("model_settings", {})` 读取（workflow_skill.py L92-107）。
> **Chat 模式下优先级链是完整的**：`clarification_result > model_settings > default_config`。
>
> **修正方案**：
> - `clarification_result` **不写入 creative_state**，而是写入 `loop_state`（随 workflow 生命周期）
> - 优先级链在 Chat 模式下**完整**：`clarification_result > model_settings > default_config`
> - `model_settings` 在 Chat 模式下通过 `context.extra` 传递，和 DAG 模式通过 `graph_state.values` 传递路径不同，但对 Skill 读取透明

**作用域**：clarification_result **仅限当前工作流/会话**，工作流结束后自动清除。UI 上明确提示："此次选择仅本次生效，不会修改您的默认设置"。

**节点读取示例**：

```python
clarification = state.get("clarification_result", {})
style = (
    clarification.get("style")                           # 最高优先级，仅本次生效
    or model_settings.get("writing_style")               # 次优先级，用户持久配置
    or skill.default_config.get("writing_style")         # 再次
    or "casual"                                          # 系统默认
)
```

### 2.7 LLM 自主触发澄清

除了 Step 0 在 Skill 调用前自动触发澄清，LLM 在 ReAct Loop 创作过程中也可以主动提问。

**机制**：LLM 输出中包含 `<needs_clarification>` 标签时，LoopExecutor 识别并暂停。

```
LLM 输出示例：

  "我已经写好了前3张卡片的文案，但在规划第4张对比图时，
   我不确定用户想要左右对比还是上下对比的布局。
   <needs_clarification>
   question: 第4张对比图的布局方式？
   options: 左右对比 | 上下对比 | 表格对比
   </needs_clarification>"
```

#### 2.7.1 流式标签解析

**采用与 `ThinkingTagDetector` 同构的状态机方案**：

```
ClarificationTagDetector 状态机：

  IDLE → 检测到 "<ne" → PARTIAL_OPEN
  PARTIAL_OPEN → 继续匹配 "eds_clarification>" → TAG_OPEN
  TAG_OPEN → 收集标签内容直到 "</ne" → PARTIAL_CLOSE
  PARTIAL_CLOSE → 继续匹配 "eds_clarification>" → TAG_CLOSE → IDLE

  TAG_CLOSE 时：
  1. 解析标签内结构化内容（question + options）
  2. 组装 ClarificationBatch
  3. break + save_loop_state + SSE 推送
  4. 暂停执行（和确认机制同构）
```

**容错**：如果标签格式不合法（LLM 输出了残缺标签），fallback 为普通文本输出，不触发澄清。宁可漏问也不卡住。

> ⚠️ **v2.2 标签共存**：`ClarificationTagDetector` 和 `ThinkingTagDetector` 同时扫描同一个流式 chunk，
> 需要明确优先级：
> - **ClarificationTagDetector 只在 ThinkingTagDetector 的 outside_thinking 状态下激活**
> - 在 `<thinking>...</thinking>` 内部的 `<needs_clarification>` 标签**不触发澄清**（thinking 内容是 LLM 内部推理，不应路由到用户）
> - 如果 `<needs_clarification>` 标签内嵌套 `<thinking>` 标签，thinking 内容被忽略，只提取澄清标签的非 thinking 内容
> - 实现方式：`ClarificationTagDetector` 接收 `is_inside_thinking: bool` 参数，仅在 `False` 时处理

#### 2.7.2 与 Stage 4.5 Skill 输出级 confirmation 的协调

> ⚠️ **v1.1 遗漏**：现有代码有 Stage 4.5（Skill 执行后可触发 confirmation），
> 方案未考虑 LLM 自主澄清与 Stage 4.5 的关系。

**协调策略**：
- Stage 4.5 的 `needs_confirmation` 是 **Skill 代码主动设置**的（确定性逻辑）
- LLM 自主澄清 `<needs_clarification>` 是 **LLM 输出中检测**的（概率性）
- 两者可以共存：Skill 代码设置 `needs_confirmation=True` 时走确认流程；LLM 输出 `<needs_clarification>` 时走澄清流程
- 如果同时触发（极低概率）：先处理 Stage 4.5 确认，确认后再处理澄清

### 2.8 澄清对迭代预算的影响

> ⚠️ **v1.1 遗漏**：v1.1 说"澄清不计入 max_iterations"，但实际恢复后迭代计数器是连续的。

**分析**：

```
chat_agent 的 max_iterations = 8

场景：iteration=3 时触发澄清
  → break，保存 iteration=3 到 loop_state
  → 用户回答后恢复
  → 新 LoopExecutor 从 iteration=3 继续
  → 后续创作可能需要 5-6 次迭代
  → 3 + 5 = 8，刚好用完预算

如果澄清后创作需要更多迭代（因为有了更精确的需求，LLM 可能做更多探索）：
  → 可能不够
```

**建议**：澄清恢复时，给 iteration 一个 **补偿额度**：

```python
# 恢复时
iteration = loop_state["iteration"]
if loop_state.get("_awaiting_clarification"):
    iteration = max(0, iteration - 1)  # 补偿 1 次迭代
```

补偿 1 次（而非完全不计入），既不滥用预算，又给澄清后的创作留一点余量。

---

## 三、数据协议

### 3.1 核心类型定义

```python
from enum import Enum
from pydantic import BaseModel


class ClarifyWhen(str, Enum):
    missing = "missing"
    ambiguous = "ambiguous"
    always = "always"


class ClarifyOption(BaseModel):
    label: str
    value: str
    description: str = ""
    preview_url: str = ""


class ClarifyDepends(BaseModel):
    field: str
    value: str


class ClarifyFieldMeta(BaseModel):
    """Skill 声明的单个字段澄清元数据"""
    hint: str
    when: ClarifyWhen = ClarifyWhen.missing
    options: list[ClarifyOption] = []
    default: str = ""
    depends_on: list[ClarifyDepends] = []
    question_type: str = "single_choice"
    placeholder: str = ""
    min_value: float = 0
    max_value: float = 100
    required: bool = True


class QuestionType(str, Enum):
    single_choice = "single_choice"
    multi_choice = "multi_choice"
    text_input = "text_input"
    slider = "slider"
    image_select = "image_select"


class ClarificationQuestion(BaseModel):
    """发送给前端的具体问题实例"""
    id: str
    source_skill: str
    question: str
    type: QuestionType = QuestionType.single_choice
    options: list[ClarifyOption] = []
    default: str = ""
    required: bool = True
    depends_on: list[ClarifyDepends] = []
    placeholder: str = ""
    min_value: float = 0
    max_value: float = 100


class ClarificationBatch(BaseModel):
    """一批问题"""
    batch_id: str
    batch_index: int
    total_batches: int
    title: str
    description: str
    questions: list[ClarificationQuestion]
    next_batch_hint: str = ""
    requires_confirmation: bool = False


class ClarificationAnswer(BaseModel):
    question_id: str
    value: str | list[str]


class ClarificationSubmitRequest(BaseModel):
    session_id: str
    batch_id: str
    answers: list[ClarificationAnswer]
    user_comment: str = ""
    action: str = "answer"               # "answer" | "skip"


class ClarificationSubmitResponse(BaseModel):
    status: str                          # "awaiting_clarification" | "clarification_complete"
    batch: ClarificationBatch | None = None
    clarification_result: dict | None = None
```

### 3.2 SSE 事件扩展

```python
"agent_clarification_required"   # 推送一批问题给前端（非终态事件）
"agent_clarification_ack"        # 确认收到用户回答（非终态事件）
"agent_clarification_expired"    # 澄清超时（非终态事件）
```

> ⚠️ **v2.1 SSE 注意事项**：
> - 澄清事件**不是终态事件**（不在 `_TERMINAL_TYPES` 中）——澄清后工作流继续，SSE 连接保持
> - 澄清回答走 **POST API**（`/api/v1/chat/clarify`），不依赖 SSE 实时推送
> - SSE 只是"通知前端有澄清请求"的辅助通道（和确认的"双通道兜底"同构）
> - 如果用户长时间不回答导致 SSE 心跳超时断开，前端重新建立连接后，澄清请求仍可通过
>   loop_state 恢复（前端从 ChatMessage.agentMeta 中读取 clarificationBatch）

### 3.3 WorkflowState 字段扩展

```python
class WorkflowState(TypedDict, total=False):
    # ... 现有字段保持不变 ...
    clarification_result: dict          # 仅当前会话生效
    clarified_answers: dict             # 服务端维护的逐批累积回答
```

### 3.4 final_output 扩展

```python
# LoopExecutor.run() 的 final_output 新增字段
final_output = {
    # ... 现有字段 ...
    "_awaiting_clarification": True,        # 新增
    "_clarification_batch": batch_dict,     # 新增
    "_loop_state_path": path,               # 现有
}
```

### 3.5 loop_state 扩展

```python
# save_loop_state() 的 state dict 新增字段
state = {
    # ... 现有字段（messages/iteration/max_iterations/context_snapshot/total_token_usage）...
    "pending_skill_call": {...},            # 现有（确认恢复用）
    "pending_clarification": {...},         # 新增（澄清恢复用）
    # 结构: {"name": skill_name, "arguments": {...}, "clarified_fields": [...]}
    "clarified_answers": {...},             # 新增（逐批累积回答）
}
```

> ⚠️ **v2.1 关键设计**：`pending_clarification` 序列化到 loop_state JSON（和 `pending_skill_call` 同构），
> **不使用 LoopExecutor 实例变量**（`_pending_confirmation` 实例变量就不序列化，跨请求恢复走 JSON）。
> 澄清恢复时从 JSON 加载 `pending_clarification`，将澄清结果合并到 arguments，立即执行该 Skill。

### 3.6 ChatResult 扩展

```python
# ChatAgent.process() 返回的 ChatResult 新增
ChatResult(
    status="awaiting_clarification",        # 新增状态
    clarification_batch=batch,              # 新增
    loop_state_path=path,                   # 现有
)
```

---

## 四、前端设计

### 4.1 ChatClarificationCard 组件

**定位**：`ChatConfirmCard` 的泛化形式。

```
ChatConfirmCard:      prompt + [approve] [reject]
                         ↓ 泛化
ChatClarificationCard: title + description + questions[] + [提交] [跳过]
```

**组件接口**：

```typescript
interface ClarificationCardProps {
  sessionId: string
  batch: ClarificationBatch
  onSubmit: (answers: ClarificationAnswer[]) => void
  onSkip: () => void
}
```

**交互规范**：

| 规则 | 说明 |
|------|------|
| 每批 3-5 题 | 不多不少，用户不会觉得烦 |
| 选项支持 preview_url | 风格类选项配预览图，降低认知成本 |
| "跳过"始终可用 | 老用户/简单任务不强制澄清 |
| 自由输入兜底 | 每个问题末尾有"其他（自定义）"输入框 |
| 批次进度指示 | 显示 "2/3"，让用户知道还有几批 |
| 下一批预告 | `next_batch_hint` 让用户有预期 |
| 回答即时校验 | 必答题未填时提交按钮 disabled |
| 合并确认 | `requires_confirmation=true` 时按钮文案变为"确认并提交" |
| 作用域提示 | 底部显示"此次选择仅本次生效，不会修改您的默认设置" |

### 4.2 AgentMeta.workflowStatus 类型扩展

> ⚠️ **v1.1 遗漏**：v1.1 只说"AgentMeta 中新增 clarificationBatch 字段"，
> 但没提 workflowStatus 需要扩展。前端根据 workflowStatus 路由组件，不加状态值无法路由。

> ⚠️ **v2.1 类型安全要求**：现有 `agent_confirm_required` 事件处理中 `cMeta` 被断言为 `any`，
> 字段赋值无类型检查。新增字段必须在 `AgentMeta` 接口中正式声明，禁止 `any` + 动态赋值。

```typescript
// cell-types.ts 扩展
type WorkflowStatus =
  | 'running'
  | 'awaiting_review'
  | 'awaiting_confirmation'
  | 'awaiting_clarification'    // 新增
  | 'suspended'
  | 'completed'
  | 'error'

interface AgentMeta {
  workflowId: string | null
  workflowStatus?: WorkflowStatus
  clarificationBatch?: ClarificationBatch   // 新增
  currentBatch?: number                     // 新增：当前批次索引
  totalBatches?: number                     // 新增：总批次数
  // ... 现有字段（intent/steps/governance/collab/reviewImages 等）...
}
```

### 4.3 SSE 事件处理扩展

在 `useChatSSE.ts` 中新增：

```typescript
case 'agent_clarification_required':
  const batch = event.data as ClarificationBatch
  const clarifyMsg: ChatMessage = {
    role: 'assistant',
    content: batch.title,
    agentMeta: {
      workflowStatus: 'awaiting_clarification',
      clarificationBatch: batch,
    },
  }
  currentMessages.value.push(clarifyMsg)
  break
```

### 4.4 ChatView.vue 路由扩展

```typescript
// 在消息渲染逻辑中
if (msg.agentMeta?.workflowStatus === 'awaiting_clarification') {
  return <ChatClarificationCard :batch="msg.agentMeta.clarificationBatch" ... />
}
```

---

## 五、API 设计

### 5.1 新增端点

```
POST /api/v1/chat/clarify
```

> ⚠️ **v1.1 遗漏修复**：v1.1 写的 `/api/chat/clarify` 缺少 `/v1/` 版本前缀，与现有 `/api/v1/chat/confirm` 不一致。

**请求体**：`ClarificationSubmitRequest`

**响应体**：`ClarificationSubmitResponse`

**处理逻辑**：

```
1. 接收用户对本批问题的回答
2. 从 loop_state 读取 clarified_answers，合并本批回答，写回 loop_state
3. 判断是否还需要追问：
   a. 遍历所有待澄清字段
   b. 检查 depends_on 条件是否满足（基于已收集的 clarified_answers）
   c. 如果还有待澄清字段 → 生成下一批 ClarificationBatch → 返回 awaiting_clarification
   d. 如果全部澄清完毕 → 编译 clarification_result → 返回 clarification_complete
4. 如果 clarification_complete：
   a. 将 clarification_result 写入 loop_state（不是 creative_state！）
   b. 从 loop_state 加载 pending_clarification
   c. 将 clarification_result 合并到 pending_clarification.arguments
   d. **立即执行该 Skill**（和确认恢复的"批准后立即执行"同构）
   e. 把执行结果注入对话
   f. 创建新 LoopExecutor 实例（iteration 补偿 1 次）→ 从断点继续
5. 如果 action == "skip"：
   a. 对本批所有未回答的必答字段，走降级链
   b. 标记本批为 skipped
   c. 继续步骤 3
6. 续跑后检测递归澄清：
   → 如果 output._awaiting_clarification → 返回新的 awaiting_clarification + 新 batch
   → 前端渲染新的 ClarificationCard（和确认的递归场景同构）
```

> ⚠️ **v2.1 关键**：步骤 4c-4e 是"澄清后立即执行"模式，防止 LLM 恢复后重新发起同一 Skill 调用
> （参数仍然模糊）导致无限澄清循环。这和确认恢复的"批准后立即执行"完全同构。
> 不做这一步，LLM 可能反复触发同一字段的澄清 → 死循环。

> ⚠️ **v2.2 并发安全**：如果用户快速连续提交两批回答（网络并发），两个请求可能同时读取
> loop_state → 合并 → 写回，导致 lost update。现有确认机制没有这个问题（单次 approve/reject
> 是原子的）。**修复**：`/chat/clarify` 端点对同一 `loop_state_path` 的请求加
> **文件锁**（`fcntl.flock` 或 `asyncio.Lock`），防止并发写入丢失。

### 5.2 现有端点扩展

`POST /api/v1/chat/message` 的响应体扩展：

```python
# 现有
{"status": "awaiting_confirmation", ...}

# 新增
{"status": "awaiting_clarification", "clarification_batch": {...}, ...}
```

### 5.3 超时与过期

| 参数 | 值 | 说明 |
|------|---|------|
| clarification_timeout | 30 min | 澄清请求的超时时间 |
| 超时后行为 | 自动 skip | 走 default_config 降级链，resume loop |
| 超时通知 | SSE 推送 `agent_clarification_expired` | 前端显示"已超时，按默认设置继续" |
| loop_state 清理 | 超时后 5 min | `cleanup_loop_state` 正常清理 |

> ⚠️ **v2.2 超时清理竞争**：超时自动 skip 后，如果 `cleanup_loop_state` 立即删除文件，
> 而用户恰好在超时瞬间手动提交 → 404。**修复**：超时后不立即删除 loop_state 文件，
> 而是标记为 `expired`（写入文件内的元数据），5 分钟后再删除。
> 用户提交时先检查文件是否 expired → 如果是，返回"已超时，按默认设置继续"的提示。

---

## 六、Skip 行为完整定义

### 6.1 Skip 粒度

| 操作 | 效果 |
|------|------|
| 跳过单个问题 | 该字段走降级链 |
| 跳过整批 | 本批所有问题走降级链 |
| 跳过全部澄清 | 所有批次走降级链，立即 resume |

### 6.2 降级链

```
对每个被跳过的字段 field：

1. model_settings.get(field)          → 用户持久配置
2. ClarifyFieldMeta.default           → Skill 声明的默认值
3. Skill.default_config.get(field)    → Skill 默认配置
4. 系统全局默认                         → 最兜底

任一层有值即停止，写入 clarification_result（标记 source="skip_fallback"）
```

### 6.3 Skip 对 depends_on 的影响

```
如果字段 A 依赖字段 B，且 B 被 skip：
  → B 的值由降级链决定
  → A 的 depends_on 条件用 B 的降级值评估
  → 如果条件满足 → A 正常显示
  → 如果条件不满足 → A 也被 skip（级联 skip）
```

---

## 七、可拓展性验证

| 未来场景 | 方案是否自然支持 | 机制 |
|---------|----------------|------|
| 新增"代码生成" Skill | ✅ | clarify_meta 声明 → 自动获得澄清能力 |
| 新增"数据分析" Skill | ✅ | clarify_meta 声明 → 自动获得澄清能力 |
| 新增第三方 Skill（.md 文件） | ✅ | frontmatter 写 clarify_schema → 零代码获得澄清能力 |
| LLM 创作中途想提问 | ✅ | `<needs_clarification>` 标签 → LoopExecutor 识别并暂停 |
| 不同 Agent 有不同问题 | ✅ | 从 session 已注册 Skills 收集 clarify_meta |
| 用户跳过澄清 | ✅ | "跳过"按钮 → 走降级链 → 向后兼容 |
| 澄清结果跨节点共享 | ✅ | 写入 WorkflowState.clarification_result |
| 新增问题类型 | ✅ | QuestionType 枚举扩展 + 前端对应渲染组件 |
| 多轮追问 | ✅ | depends_on 条件触发 |
| Clarify + Confirm 同时需要 | ✅ | Clarify 在 Guardian 前处理完，再进 Guardian 走 Confirm |

---

## 八、与现有系统的兼容性

### 8.1 向后兼容

| 场景 | 行为 |
|------|------|
| Skill 没有 clarify_meta | Step 0 在 O(1) 内跳过 → 走现有流程 |
| 用户跳过澄清 | clarification_result 为空 → 各节点走 model_settings / default_config |
| 老版本前端 | 不识别 awaiting_clarification → 超时后自动 skip → 走默认创作 |
| DAG 模式工作流 | clarification_result 为空 → 节点走现有逻辑 |

### 8.2 与现有机制的复用

| 现有机制 | 复用方式 |
|---------|---------|
| `loop_state` 序列化/反序列化 | 澄清走同一套 save/load 逻辑 |
| `final_output._awaiting_*` 标记模式 | `_awaiting_clarification` 与 `_awaiting_confirmation` 同构 |
| `ChatAgent` 状态检测 | 检测 `_awaiting_clarification` 返回 `ChatResult` |
| LoopExecutor break + 新实例恢复 | 澄清恢复走同一套模式 |
| SSE 事件通道 | `agent_clarification_required` 走现有 `sse_bus.emit()` |
| `ChatConfirmCard` 交互模式 | `ChatClarificationCard` 复用其样式和动画 |
| `ThinkingTagDetector` | `ClarificationTagDetector` 同构实现 |

### 8.3 不修改的现有代码

| 文件 | 修改范围 |
|------|---------|
| `guardian.py` | **不修改**——Clarify 不在 Guardian 内部 |
| `loop.py` 的 Guardian 调用逻辑 | **不修改**——Step 0 在 Guardian 调用之前 |
| `cell-types.ts` 的现有类型 | **只扩展**——workflowStatus 联合类型新增值 |

---

## 九、效果度量

| 指标 | 定义 | 采集方式 | 目标 |
|------|------|---------|------|
| 澄清触发率 | 触发澄清的会话 / 总会话数 | 后端日志 | > 60%（创作类会话） |
| 澄清跳过率 | 跳过澄清的会话 / 触发澄清的会话 | 后端日志 | < 30% |
| 澄清后返工率 | 澄清后用户要求重做的会话 / 澄清完成的会话 | 后端日志 | < 15% |
| 未澄清返工率 | 跳过澄清后用户要求重做的会话 / 跳过澄清的会话 | 后端日志 | 基线（预期 > 30%） |
| 澄清耗时 | 从推送澄清卡片到用户提交最后一批的平均时间 | 前端埋点 | < 60s |
| Token 节约率 | (未澄清平均 token - 澄清后平均 token) / 未澄清平均 token | 后端日志 | > 20% |

---

## 十、实现路径

### Phase 1：基础设施（1 周）

| 任务 | 产出 | 依赖 |
|------|------|------|
| `ClarifyWhen` / `ClarifyOption` / `ClarifyDepends` / `ClarifyFieldMeta` 等类型定义 | `backend/app/agents/clarification_schema.py` | 无 |
| `Tool.clarify_meta` 类属性（默认 `{}`） | 修改 `base.py` Tool 基类 | 无 |
| `WorkflowState.clarification_result` + `clarified_answers` 新增 | 修改 `_base.py` | 无 |
| PromptDrivenSkill frontmatter `clarify_schema` 解析 + 动态注入 `clarify_meta` | 修改 `prompt_skills.py` | 无 |
| 字段依赖图构建 + 拓扑排序 + 环检测 | 新增 `clarification_graph.py` | 无 |

### Phase 2：后端流程（1.5 周）

| 任务 | 产出 | 依赖 |
|------|------|------|
| LoopExecutor Step 0: Clarify 前置检查 | 修改 `loop.py` 的 `_execute_tool_call` | Phase 1 |
| final_output `_awaiting_clarification` 标记 | 修改 `loop.py` 的 `run()` | Phase 1 |
| ChatAgent 检测 `_awaiting_clarification` → 返回 ChatResult | 修改 `chat_agent.py` | Phase 1 |
| Ambiguous 判定（L1/L2 规则 + L3 LLM 辅助 + 缓存） | 新增 `loop.py` 内部方法 | Phase 1 |
| `/api/v1/chat/clarify` API 端点 | 新增路由 | Phase 1 |
| 分批策略实现（字段依赖图 → ClarificationBatch） | 新增 `clarification_batch_builder.py` | Phase 1 |
| 澄清恢复：加载 loop_state → 新 LoopExecutor → iteration 补偿 | 修改 `chat_agent.py` | Phase 1 |
| 澄清超时机制 | 修改 `loop.py` | Phase 1 |

### Phase 3：前端交互（1.5 周）

> ⚠️ **v1.1 工作量修复**：v1.1 估计 1 周，但 useChatSSE.ts 已极复杂（StreamPlayer、
> 双游标、thinking 标签状态机），在其中新增事件路由 + ClarificationCard 组件
> （多题型渲染、批次进度、跳过逻辑、提交/下一批切换）工作量较大。调整为 1.5 周。

| 任务 | 产出 | 依赖 |
|------|------|------|
| `ChatClarificationCard.vue` 组件 | 新增前端组件 | Phase 2 |
| `AgentMeta.workflowStatus` 类型扩展（加 `awaiting_clarification`） | 修改 `cell-types.ts` | Phase 1 |
| SSE 事件 `agent_clarification_required` 处理 | 修改 `useChatSSE.ts` | Phase 2 |
| ChatView.vue 根据 workflowStatus 路由到 ClarificationCard | 修改 `ChatView.vue` + `AssistantMessageCell.vue` | Phase 3 |
| 回答提交 → 调 `/api/v1/chat/clarify` → 渲染下一批或恢复流式 | 修改 `useChatInteractions.ts` | Phase 2 |

### Phase 4：LLM 自主澄清（0.5 周）

| 任务 | 产出 | 依赖 |
|------|------|------|
| `ClarificationTagDetector` 状态机（同构 ThinkingTagDetector） | 新增 `loop.py` 内部类 | Phase 2 |
| LLM 输出中的澄清标签解析 → break + save + SSE | 新增解析逻辑 | Phase 2 |
| BEHAVIOR.md 补充 `<needs_clarification>` 使用指引 | 修改 prompt | Phase 4 |

### Phase 5：现有 Skill 补 clarify_meta 声明（2 周）

| 任务 | 产出 | 依赖 |
|------|------|------|
| copywrite Skill 补 clarify_meta | 修改 `copy*5_copywrite_builder.py` | Phase 1 |
| image_plan Skill 补 clarify_meta | 修改对应 Skill | Phase 1 |
| card_design 等 PromptDrivenSkill 补 frontmatter | 修改 `prompts/skills/*.md` | Phase 1 |
| 其余 30+ .md Skill 逐个评估是否需要 clarify | 逐个修改 | Phase 1 |

### Phase 6：度量与迭代（持续）

| 任务 | 产出 | 依赖 |
|------|------|------|
| 澄清指标埋点（后端日志） | 修改 `loop.py` | Phase 2 |
| 澄清指标埋点（前端埋点） | 修改 `ChatClarificationCard.vue` | Phase 3 |
| 效果看板 | Grafana / 内部报表 | Phase 6 |

---

## 十一、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 澄清问题太多，用户烦躁 | 用户跳过或放弃 | 每批限 3-5 题；"跳过"始终可用；首批只问最关键的 |
| LLM 判 ambiguous 误判 | 不该问的问了，或该问的没问 | L1/L2 规则兜底；L3 LLM 超时视为 SUFFICIENT |
| Step 0 性能退化 | 每次工具调用多一步检查 | Skill 无 clarify_meta 时 O(1) 跳过；有时 O(n) n=字段数 |
| loop_state 文件膨胀 | 磁盘占用 | 澄清回答量很小（<1KB），`cleanup_loop_state` 已有清理 |
| 前端 SSE 复杂度 | useChatSSE.ts 进一步膨胀 | ClarificationCard 逻辑独立于 StreamPlayer，不增加播放器复杂度 |
| 分批策略推导错误 | 问题顺序不合理 | 拓扑排序 + 环检测 fallback 到不分批 |
| clarification_result 残留 | 覆盖下次创作的偏好 | 仅限当前会话，工作流结束自动清除 |
| 澄清超时无人响应 | loop 永久暂停 | 30min 超时自动 skip + resume |
| `<needs_clarification>` 标签解析失败 | LLM 输出卡住 | 容错：格式不合法当普通文本，不触发暂停 |
| PromptDrivenSkill clarify_schema 格式错误 | 注册失败 | try-except，解析失败则 clarify_meta={} |
| 澄清后迭代预算不足 | 创作未完成就达到 max_iterations | iteration 补偿 1 次；长期可考虑动态调整 max_iterations |
| 澄清后 LLM 重复触发同一 Skill 澄清 | 无限澄清死循环 | 澄清恢复后立即执行 Skill（和确认的"批准后立即执行"同构），跳过 Step 0 重新判定 |
| creative_state 跨工作流污染 | workflow A 的澄清结果影响 workflow B | clarification_result 写入 loop_state（随 workflow 生命周期），不写入 creative_state |
| Chat 模式优先级链退化 | 缺少 model_settings 层 | ~~已删除~~：v2.2 勘误确认 Chat 模式有 model_settings，优先级链完整 |
| 递归澄清 | 恢复后再次触发澄清，前端需渲染新卡片 | API 层检测 _awaiting_clarification 并返回新 batch（和确认递归同构） |
| 前端 AgentMeta 类型安全 | any 断言绕过类型检查 | 新增字段必须在 AgentMeta 接口中正式声明，禁止 any + 动态赋值 |
| 跨批次并发写入 | lost update 导致回答丢失 | 文件锁（fcntl.flock / asyncio.Lock）保护 loop_state 写入 |
| 超时清理与用户提交竞争 | 用户提交时 404 | 超时后标记 expired + 延迟 5min 删除，提交时检查 expired |
| 搜索/分析请求误触发澄清 | 用户搜热点时弹出 30 个问题 | Step 0 意图过滤，仅创作类意图触发澄清 |
| thinking 内澄清标签误触发 | LLM 内部推理被路由到用户 | ClarificationTagDetector 仅在 outside_thinking 下激活 |
| when=always 重复触发 | 同一字段每次调用都问 | 检查 clarified_answers 去重，已有值则跳过 |

---

## 十二、开放问题（待审核确认）

| # | 问题 | 选项 | 建议 |
|---|------|------|------|
| Q1 | ambiguous 判定是否需要 LLM？ | A: 纯规则 B: 规则+LLM C: 可配置 | B——L1/L2 规则覆盖 missing，L3 LLM 辅助 ambiguous |
| Q2 | 澄清结果是否持久化到 DB？ | A: 仅会话内(state) B: 写入 chat_message C: 独立表 | A——仅当前会话生效 |
| Q3 | 用户修改已回答的澄清问题？ | A: 不允许 B: 允许回改 | B——Phase 1 先实现 A |
| Q4 | DAG 模式是否也支持澄清？ | A: 仅 ReAct B: 双模式都支持 | A——Phase 1 先只做 ReAct |
| Q5 | 风格选项的 preview_url 图片谁提供？ | A: 硬编码静态图 B: AI 实时生成 C: 用户上传 | A——Phase 1 用预设缩略图 |
| Q6 | 澄清阶段是否计入 max_iterations？ | A: 计入 B: 不计入 C: 补偿 | C——补偿 1 次迭代（见 2.8 节） |
| Q7 | i18n 如何支持？ | A: clarify_meta 内多语言 B: 运行时翻译 C: Phase 1 不考虑 | C——Phase 1 仅中文 |
| Q8 | 澄清在 Loop 首次 tool_call 之前还是之中触发？ | A: 之前（预澄清） B: 之中（逐 Skill 澄清） | A（ReAct）/ B（DAG）——见 2.5.2 |
| Q9 | Guardian 代码注释与实际执行顺序不一致，是否一并修正？ | A: 修正注释 B: 不动 | A——避免后续开发者再踩坑 |
| Q10 | Python Skill 的 clarify_meta 是否也支持从 input_schema Field 自动推导？ | A: 纯手动声明 B: Field 上加 clarify 装饰器自动推导 C: Phase 1 手动，Phase 2 自动 | C——Phase 1 先手动声明，稳定后再考虑自动推导 |

---

## 附录A：版本演进

| 版本 | 核心架构 | 致命问题 |
|------|---------|---------|
| v1.0 | Clarify 作为 Guardian 新阶段（Policy→Clarify→Confirm→Validate） | Guardian 描述与代码不符；auto-allow 绕过 Clarify；分批基于静态 skills 列表；PromptDrivenSkill 共享 schema |
| v1.1 | Clarify 在 Auto-allow 之前（Policy→Clarify→Auto-allow→...） | 确认恢复是"序列化+重建"不是"暂停+恢复"；chat_agent.skills=None 无数据源；auto-allow 与 Clarify 哲学冲突 |
| v2.0 | **Clarify 是 LoopExecutor 的独立前置步骤（Step 0），不在 Guardian 内部** | 上述问题全部解决 |
| v2.1 | 同 v2.0 架构，补充完整确认链路细节 | 澄清后立即执行 Skill；pending_clarification 序列化到 loop_state；no-policy Skill 澄清；creative_state 不写入；递归澄清；SSE 终态；前端类型安全 |
| v2.2 | 同 v2.0 架构，终审修正 | E1: Chat 模式有 model_settings；E2: _pending_confirmation 措辞修正；E3: #32 勘误；D1: 并发文件锁；D2: 超时清理竞争；D3: 触发阈值；D4: 标签共存优先级；D5: when=always 去重 |

## 附录B：全量审查问题索引

| # | 严重度 | 问题 | 版本 | 修复位置 |
|---|--------|------|------|---------|
| 1 | 🔴 | Guardian 阶段描述与代码不符 | v1.0 | v1.1 勘误 → v2.0 不再修改 Guardian |
| 2 | 🔴 | auto-allow 绕过 Clarify | v1.0 | v1.1 移到 Auto-allow 前 → v2.0 移出 Guardian |
| 3 | 🔴 | ReAct 下分批策略基于静态 skills 列表无效 | v1.0 | v1.1 改字段依赖图 → v2.0 不依赖 AgentDef.skills |
| 4 | 🔴 | PromptDrivenSkill 共享 input_schema | v1.0 | v1.1 clarify_meta 独立 → v2.0 明确注入到类属性 |
| 19 | 🔴 | 确认恢复是"序列化+重建"不是"暂停+恢复" | v1.1 | v2.0 1.1 节重写 + 2.2 节完整链路 |
| 20 | 🔴 | chat_agent.skills=None，分批策略无数据源 | v1.1 | v2.0 2.5.2 不依赖 AgentDef.skills |
| 21 | 🔴 | auto-allow 与 Clarify 架构哲学冲突 | v1.1 | v2.0 1.2 节：Clarify 移出 Guardian |
| 28 | 🔴 | 确认恢复有"批准后立即执行"逻辑，方案遗漏 | v2.0 | v2.1 2.2 步骤 8 + 5.1 步骤 4c-4e |
| 29 | 🔴 | _pending_confirmation 实例变量不序列化 | v2.0 | v2.1 3.5 节：pending_clarification 序列化到 loop_state JSON |
| 30 | 🔴 | no-policy Skill 默认 ALLOW，永远不触发 Clarify | v2.0 | v2.1 1.2 节：ClarifyGate 不依赖 Guardian 策略 |
| 5 | 🟡 | Clarify+Confirm 合并场景 | v1.0 | v2.0 串行处理（Clarify 先，Confirm 后） |
| 6 | 🟡 | `<needs_clarification>` 流式解析 | v1.0 | v2.0 2.7.1 状态机 |
| 7 | 🟡 | previous_answers 客户端维护不可靠 | v1.0 | v2.0 3.1 移除，服务端维护 |
| 8 | 🟡 | 无超时机制 | v1.0 | v2.0 5.3 节 |
| 9 | 🟡 | Skip 行为欠定义 | v1.0 | v2.0 第六章 |
| 10 | 🟡 | 优先级链覆盖持久偏好 | v1.0 | v2.0 2.6 节会话作用域 |
| 11 | 🟡 | ambiguous LLM 细节未指定 | v1.0 | v2.0 2.3.1 节三层策略 |
| 22 | 🟡 | Stage 4.5 Skill 输出级 confirmation 未考虑 | v1.1 | v2.0 2.7.2 协调策略 |
| 23 | 🟡 | API/ChatAgent/前端完整链路缺失 | v1.1 | v2.0 2.2 节完整链路 |
| 24 | 🟡 | AgentMeta.workflowStatus 需扩展 | v1.1 | v2.0 4.2 节 |
| 25 | 🟡 | 澄清对迭代预算影响未分析 | v1.1 | v2.0 2.8 节 + Q6 |
| 26 | 🟡 | PromptDrivenSkill 动态类无 clarify_schema 属性 | v1.1 | v2.0 2.4.2 明确注入到 clarify_meta 类属性 |
| 27 | 🟡 | 前端 SSE 已极复杂，工作量低估 | v1.1 | v2.0 Phase 3 调整为 1.5 周 |
| 31 | 🟡 | creative_state 跨工作流污染 | v2.0 | v2.1 2.6 节：写入 loop_state 不写入 creative_state |
| 32 | 🟡 | Chat 模式无 model_settings | v2.0 | v2.2 勘误：Chat 模式有 model_settings（通过 context.extra），优先级链完整 |
| 33 | 🟡 | 澄清递归场景未考虑 | v2.0 | v2.1 2.2 步骤 9 + 5.1 步骤 6 |
| 34 | 🟡 | SSE 终态清理机制未考虑 | v2.0 | v2.1 3.2 节：澄清事件为非终态，回答走 POST API |
| 35 | 🟡 | 前端 AgentMeta 类型安全 | v2.0 | v2.1 4.2 节：禁止 any 断言，正式声明接口字段 |
| 12 | 🟢 | SSE 事件命名不一致 | v1.0 | v2.0 统一为 `agent_clarification_required` |
| 13 | 🟢 | ClarifyOption 重复定义 | v1.0 | v2.0 统一为 `ClarifyOption` |
| 14 | 🟢 | depends_on 组合逻辑未定义 | v1.0 | v2.0 `list[ClarifyDepends]` + AND |
| 15 | 🟢 | 无 i18n 考虑 | v1.0 | v2.0 Q7 |
| 16 | 🟢 | 无度量框架 | v1.0 | v2.0 第九章 |
| 17 | 🟢 | C9 对齐不准确 | v1.0 | v2.0 移除 |
| 18 | 🟢 | Phase 5 工作量偏低 | v1.0 | v2.0 调整为 2 周 |
| D1 | 🟡 | 跨批次回答并发写入 lost update | v2.1 | v2.2 5.1 节：文件锁（fcntl.flock / asyncio.Lock） |
| D2 | 🟡 | 超时清理与用户提交竞争 → 404 | v2.1 | v2.2 5.3 节：标记 expired + 延迟删除 |
| D3 | 🟡 | ReAct 模式搜索/分析请求误触发澄清 | v2.1 | v2.2 2.3 节：意图过滤 + 触发阈值 |
| D4 | 🟡 | ClarificationTagDetector 与 ThinkingTagDetector 共存优先级 | v2.1 | v2.2 2.7.1 节：仅在 outside_thinking 下激活 |
| D5 | 🟡 | when=always 重复触发澄清 | v2.1 | v2.2 2.3 节：检查 clarified_answers 去重 |