# Codex 聊天界面渲染哲学 — 研究文档

> 研究日期：2026-08-18
> 目的：为 ChatView 前端优化提供参考基线

---

## 一、消息数据模型：5 种 Cell 类型

Codex TUI 把聊天内容抽象成 **HistoryCell** trait，5 种具体类型各有独立渲染逻辑：

| Cell 类型 | 内容 | 渲染方式 |
|---|---|---|
| **UserHistoryCell** | 用户消息（含附件、@提及） | 简洁展示，附件用图标标注 |
| **AgentMessageCell** | AI 回复（纯文本） | Markdown 渲染（标题/列表/代码块/粗体） |
| **ExecCell** | 工具调用（shell 命令执行结果） | **折叠显示**：默认只显示几行 + `… +X lines`，可展开 |
| **PlanHistoryCell** | `update_plan` 的计划步骤 | Checkbox 列表：`✔ 已完成` / `◉ 进行中` / `□ 待处理` |
| **DiffCell** | `apply_patch` 的代码变更 | 红/绿 diff 视图 + 行号 + 语法高亮 |

**核心洞察**：不同类型的内容用不同的 Cell 组件，不是把所有内容都当"文本"渲染。工具调用有专门的 ExecCell，代码变更有 DiffCell，计划有 PlanCell。

---

## 二、Markdown 渲染细节

### 渲染引擎

- 解析器：`pulldown-cmark`（Rust 生态的 CommonMark 解析器）
- 两种渲染函数：

| 函数 | 用途 | 特殊处理 |
|---|---|---|
| `append_markdown` | Plan 块和历史 Cell | 直接解析渲染 |
| `append_markdown_agent` | AI 回复 | **先剥离 ` ```md ` / ` ```markdown ` 围栏**，让里面的表格能被原生渲染 |

### 各元素渲染规则

| Markdown 元素 | 渲染方式 |
|---|---|
| **标题** `#` `##` `###` | 粗体 + 加大字号，短 Title Case（1-3 词），用 `**…**` 包裹 |
| **粗体** `**text**` | 终端粗体样式 |
| **斜体** `*text*` | 终端斜体样式 |
| **行内代码** `` `code` `` | 反引号包裹，用于命令/路径/环境变量/代码 ID |
| **代码块** ` ```lang ` | 语法高亮（syntect）+ 主题 + 可选行号 + 语言标识 |
| **列表** `- item` | `•` 前缀，4-6 条/组，按重要性排序 |
| **有序列表** `1. item` | 数字前缀，用于建议选项（用户可快速回复数字） |
| **引用** `> text` | 竖线 `│` 前缀 + 缩进 |
| **表格** | Unicode box-drawing 边框；窄屏自动降级为 label-value 卡片 |
| **链接** | 不渲染为可点击，只显示文本 |

### 系统提示词中的输出格式规范

Codex 的系统提示词明确要求模型：

> "You are producing plain text that will later be styled by the CLI. Follow these rules exactly. Formatting should make results easy to scan, but not feel mechanical."

具体规则：
- 默认：非常简洁，友好的编程队友语气
- 只在需要时提问；主动建议；镜像用户风格
- 大量工作时清晰总结；遵循 final-answer 格式
- 简单确认跳过重度格式化
- 不倾倒写好的大文件；只引用路径
- 不说"保存/复制这个文件"——用户在同一台机器上
- 代码变更：先快速解释变更，再给上下文细节
- 多选项时用数字列表，方便用户回复数字

### 终端宽度自适应（Reflow）

Codex 最用力的地方之一：

- **流式阶段**：每收到 delta，用 `textwrap::wrap` 按当前终端宽度换行
- **完成后**：保存原始 markdown 源文本（source-backed），终端宽度变化时**从源文本重新渲染**
- **防抖**：resize 事件做 debounce，避免频繁重绘
- **表格响应式**：宽屏用 Unicode 表格边框，窄屏降级为 key-value 卡片

---

## 三、思考过程（Reasoning）的渲染

### 流式阶段（模型正在思考）

| 配置 | 行为 |
|---|---|
| 默认 | 显示 spinner + `Thinking…` 状态行 |
| `show_raw_agent_reasoning = true` | **实时流式显示**推理文本，dim + italic 样式 |
| `hide_agent_reasoning = true` | 完全隐藏推理内容 |

实时流式显示的具体行为：
- 推理文本以 **dim + italic** 样式逐行出现
- 只显示最后 3 行 wrapped lines（PREVIEW_LINES 截断），避免刷屏
- 约 50ms 刷新间隔
- spinner 动画继续运行

### 完成后（回复已结束）

- 推理内容**折叠为一行 dim 指示器**，显示行数（如 `思考过程 (42行)`）
- 用户可点击展开查看完整推理
- 展开后内容仍然是 dim + italic，视觉上从属于正式回复

---

## 四、工具调用的渲染

### Shell 命令（exec_command）

```
$ rg "TODO" src/
… +12 lines                    ← 默认折叠
```

- **默认折叠**：只显示前几行 + `… +X lines` 提示
- 用户可展开查看完整输出
- 输出上限：10KB 或 256 行（硬编码），超出截断中间保留首尾
- 这个折叠行为是用户投诉最多的点之一（#4550, #19260）

### 代码变更（apply_patch）

```
src/app.ts · +18 -2            ← 文件路径 + 增删行数摘要
 15 | function old() {         ← 行号 + 删除行（红色）
 16 | function new() {         ← 行号 + 新增行（绿色/粗体）
```

- 红/绿 diff 着色，主题感知（亮色/暗色终端不同配色）
- 语法高亮（syntect）在 diff 内部
- 行号 + 变更标记

---

## 五、计划步骤（update_plan）的渲染

```
Updated Plan
└ 先读取文件结构，理解代码组织
✔ 读取 src/ 目录结构
◉ 分析核心模块依赖关系
□ 生成重构方案
□ 编写测试用例
```

- **结构化数据**：不是文本，是 `[{step, status}]` 数组
- `✔` 已完成 / `◉` 进行中（动画点） / `□` 待处理
- 顶部有 `explanation` 字段（一段叙述性文字，解释当前策略）
- 始终只有 **1 个** `in_progress` 项
- 流式更新：模型完成一步后重新调用 `update_plan`，前端增量更新 checkbox

### update_plan 工具定义

```json
{
  "type": "function",
  "name": "update_plan",
  "description": "Updates the task plan...",
  "parameters": {
    "type": "object",
    "properties": {
      "explanation": { "type": "string" },
      "plan": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "step": { "type": "string" },
            "status": { "type": "string", "enum": ["pending", "in_progress", "completed"] }
          }
        }
      }
    }
  }
}
```

---

## 六、流式输出机制

### Source-Backed Streaming

Codex 的流式不是简单的"追加字符"：

1. **活跃阶段**：收到 delta → 追加到 source-backed markdown cell → 用 `pulldown-cmark` 实时解析渲染
2. **完成阶段**：流结束 → 用最终完整文本**替换**流式草稿 → 重新渲染（确保格式完整）
3. **resize 阶段**：终端宽度变化 → 从保存的源文本重新渲染

这意味着：**流式过程中看到的格式可能不完整（比如代码块还没闭合），完成后会重新渲染为正确格式**。

### 状态指示

| 状态 | 显示 |
|---|---|
| 等待首个 token | `• Thinking… (Ns • esc to interrupt)` |
| 推理中 | spinner + dim italic 推理文本（如果开启） |
| 工具执行中 | spinner + 工具名 + 执行时间 |
| 回复流式中 | 逐字符/逐词出现 |
| 完成 | 无特殊标记，内容定格 |

---

## 七、对我们项目的优化建议

### 优先级 P0：立即做

| 优化项 | 现状 | Codex 做法 | 建议 |
|---|---|---|---|
| **Markdown 渲染** | 手写正则替换，功能有限 | `pulldown-cmark` 完整解析 | 引入 `marked` 或 `markdown-it` 库 |
| **代码块语法高亮** | 无高亮 | syntect 语法高亮 + 语言标识 | 引入 `highlight.js` 或 `shiki` |
| **思考过程样式** | 普通文字 + 关键词高亮 | dim + italic，完成后折叠为一行 | 改为 `opacity:0.5 + italic`，折叠为 `思考过程 (N行)` |
| **流式完成后重渲染** | 不重渲染 | 用完整文本替换草稿重新渲染 | 流结束时重新调 `renderMarkdown` |

### 优先级 P1：后续做

| 优化项 | 说明 |
|---|---|
| **工具调用 Cell** | 如果接入 RPA 工具，需要独立的 ExecCell 组件（折叠显示命令输出） |
| **计划步骤 Cell** | 后端定义 `update_plan` tool schema，前端解析 `tool_call` 事件渲染 checkbox |
| **Diff 视图** | 代码变更用红绿 diff 展示，需要 DiffCell 组件 |
| **表格响应式** | 宽屏用表格，窄屏降级为 key-value 卡片 |
| **响应式宽度** | markdown 渲染需注意窄屏降级 |

### 优先级 P2：锦上添花

| 优化项 | 说明 |
|---|---|
| **主题切换** | 亮色/暗色终端不同配色 |
| **代码块行号** | 可选显示 |
| **工具输出折叠阈值** | 可配置折叠行数 |
| **resize 防抖重渲染** | web 端天然响应式，暂不需要 |

---

## 八、参考源

- [Unrolling the Codex Agent Loop](https://openai.com/index/unrolling-the-codex-agent-loop/) — OpenAI 官方博客
- [Codex CLI TUI markdown.rs](https://github.com/openai/codex/blob/main/codex-rs/tui/src/markdown.rs) — Markdown 渲染源码
- [Codex CLI markdown_render.rs](https://github.com/openai/codex/blob/main/codex-rs/tui/src/markdown_render.rs) — 渲染引擎
- [feat(tui): stream agent reasoning live](https://github.com/openai/codex/pull/6006) — 思考过程流式渲染 PR
- [feat(tui): source-back assistant streaming](https://github.com/openai/codex/pull/19870) — Source-backed 流式 PR
- [feat(tui): render responsive Markdown tables](https://github.com/openai/codex/pull/22052) — 响应式表格 PR
- [fix(tui): reflow scrollback on terminal resize](https://github.com/openai/codex/pull/18575) — resize 重渲染 PR
- [Plan Mode: Shift+Tab](https://github.com/openai/codex/pull/4770) — Plan 模式 PR
- [Codex CLI system prompt](https://github.com/openai/codex/pull/10124) — 系统提示词
- [Codex CLI exec_cell render](https://github.com/openai/codex/issues/4550) — 工具输出折叠
- [Codex CLI DiffCell](https://github.com/Hmbown/CodeWhale/issues/505) — Diff 渲染
- [Todo/Plan 展示 Deep-Dive 4方对比](https://github.com/wenshao/codeagents/blob/main/docs/comparison/todo-display-deep-dive.md) — 计划展示对比