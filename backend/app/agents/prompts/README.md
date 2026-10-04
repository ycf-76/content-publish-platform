# Prompt Stack 架构说明

> 本文档是 `backend/app/agents/prompts/` 目录的唯一索引，说明各文件职责、加载机制和修改规则。

---

## 目录结构

```
prompts/
├── SOUL.md                          ← 第1层：人格与能力边界
├── AGENTS.md                        ← 第2层：场景路由与协作规则
├── BEHAVIOR.md                      ← 第3层：工具使用哲学与行为约束（运行时注入）
├── skills/                          ← Prompt-driven Skill 定义（由 prompt_skills.py 动态扫描注册）
│   ├── quality-gate.md
│   └── topic-evaluator.md
└── references/                      ← 第4层：领域知识（独立更新，不参与Stack拼接）
    ├── copy-frameworks.md           ← 文案框架库（8框架 + 去AI感规则）
    ├── hook-title-formulas.md       ← 钩子 + 标题公式库（12钩子 + 7类公式 + 平台规范）
    └── scoring-dimensions.md        ← 选题评分维度（7维度 + 标尺 + 权重 + 跨平台系数）
```

---

## Prompt Stack 加载机制

主Agent（chat_agent）的 system prompt 由三层拼接 + 运行时注入组成：

```
最终 system_prompt = role_block + behavior_block + [USER REQUEST]

其中：
  role_block    = _load_prompt_stack("SOUL", "AGENTS")   ← registry.py 第210行
                = SOUL.md + "\n\n" + AGENTS.md

  behavior_block = BEHAVIOR.md
                   .replace("{skill_lines}", 动态生成的工具目录)
                   .replace("{skill_guidance_block}", 各Skill的prompt_guidance)
```

### 加载链路

```
registry.py                          loop.py
┌─────────────────────┐             ┌──────────────────────────┐
│ BUILTIN_AGENTS       │             │ _system_prompt()         │
│  "chat_agent":       │  ──加载──→  │  1. role_block           │
│   prompt_template=   │             │     = harness.prompt_    │
│   _load_prompt_stack │             │       template           │
│   ("SOUL","AGENTS")  │             │  2. behavior_block       │
│                      │             │     = BEHAVIOR.md        │
│                      │             │       .replace(...)      │
│                      │             │  3. [USER REQUEST]       │
└─────────────────────┘             └──────────────────────────┘
```

### references 不参与拼接

`references/` 下的文件**不**拼入 system prompt。它们由各 Skill 在运行时按需读取并注入到 `prompt_guidance` 字段，最终进入 `behavior_block` 的 `{skill_guidance_block}` 占位符。

这样做的目的：
- 避免每次请求都塞入全部领域知识（省token）
- 各Skill只引用自己需要的reference（文案Skill引用框架库，选题Skill引用评分维度）
- reference可独立更新，不重启服务

---

## 各层职责与修改规则

### 第1层：SOUL.md — 人格与能力边界

| 项目 | 说明 |
|------|------|
| 职责 | 定义"我是谁"、"我能做什么"、"我的判断原则" |
| 内容 | 人格定位、能力清单、工具调用判断原则 |
| 修改频率 | 低（人格稳定） |
| 修改规则 | 改人格定位或能力边界时改此文件；不加具体场景路由（归AGENTS） |

### 第2层：AGENTS.md — 场景路由与协作规则

| 项目 | 说明 |
|------|------|
| 职责 | 定义"什么场景走什么路径"、"怎么协作" |
| 内容 | 场景→工具映射、浏览器规约、spawn协作规则、fork_mode选择 |
| 修改频率 | 中（新增平台/工具时更新场景映射） |
| 修改规则 | 新增工具或平台时加场景路由；不改人格（归SOUL）；不改工具使用哲学（归BEHAVIOR） |

### 第3层：BEHAVIOR.md — 工具使用哲学与行为约束

| 项目 | 说明 |
|------|------|
| 职责 | 定义"怎么用工具"、"什么时候停"、"输出格式"、"每轮提醒" |
| 内容 | 工具使用哲学、停止规则、输出格式、TURN_REMINDER |
| 修改频率 | 低（行为规则稳定） |
| 修改规则 | 改行为约束或TURN_REMINDER时改此文件；**含{skill_lines}和{skill_guidance_block}占位符，勿删** |
| 加载方式 | 进程级缓存（`_BEHAVIOR_TEMPLATE_CACHE`），修改后需重启后端生效 |

### 第4层：references/ — 领域知识

| 文件 | 职责 | 谁引用 |
|------|------|--------|
| copy-frameworks.md | 文案框架唯一源（PAS/AIDA/BAB/FAB/4U/STAR/SLAY/STEP + 去AI感） | 文案类Skill |
| hook-title-formulas.md | 钩子+标题公式唯一源（12钩子 + 7类公式 + 6平台规范） | 文案类Skill、选题Skill |
| scoring-dimensions.md | 选题评分唯一标准（7维度 + 标尺 + 权重 + 跨平台系数 + 合规预警） | 选题评估Skill |

修改规则：
- **唯一源原则**：同一份知识只在一个reference文件定义，不散落在各Skill代码中
- 改框架/公式/评分维度时只改对应reference文件，不改Skill代码
- 新增知识领域时新建reference文件，并在对应Skill中引用

---

## 子Agent prompt

子Agent（search/analyze/copywrite/audit/final_review/image_gen/publish）的 prompt 通过 `AgentDef.prompt_template` 内联定义在 `registry.py` 的 `BUILTIN_AGENTS` 中，不再使用独立 `.md` 文件。

---

## 新增平台/工具的修改清单

当需要支持新平台或新工具时，按以下清单修改：

| 步骤 | 改什么 | 改哪里 |
|------|--------|--------|
| 1 | 人格能力清单加新平台 | SOUL.md |
| 2 | 场景路由加新映射 | AGENTS.md |
| 3 | 跨平台适配规则 | references/copy-frameworks.md 的"平台特化"段 |
| 4 | 标题规范加新平台 | references/hook-title-formulas.md 的"平台标题规范"表 |
| 5 | 适配系数加新平台 | references/scoring-dimensions.md 的"跨平台选题适配"表 |
| 6 | 互动引导加新平台 | references/hook-title-formulas.md 的"互动引导"表 |
| 7 | TURN_REMINDER加新规则 | BEHAVIOR.md 的 REMINDER 段 |