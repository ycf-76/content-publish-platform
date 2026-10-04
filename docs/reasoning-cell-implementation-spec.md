# ReasoningCell 精确实现规格书

> 基于 Codex CLI 源码（`D:\My_Project\codex\codex-rs`）逆向分析，对齐 Codex 的 reasoning 渲染架构

---

## 一、Codex 原版架构（参考系）

### 1.1 数据流全景

```
LLM API Response
  ├─ reasoning_content 字段 ──→ ResponseEvent::ReasoningSummaryDelta
  │                                ↓
  │                          EventMsg::ReasoningContentDelta
  │                                ↓ (event_mapping.rs:378)
  │                          ServerNotification::ReasoningSummaryTextDelta
  │                                ↓ (protocol.rs:82)
  │                          on_agent_reasoning_delta(delta)
  │                                ↓ (streaming.rs:232)
  │                          reasoning_buffer.push_str(delta)
  │                          extract_first_bold() → set_status_header()
  │
  ├─ content 字段 ──→ ResponseEvent::ContentDelta
  │                       ↓
  │                  EventMsg::AgentMessageDelta
  │                       ↓ (event_mapping.rs)
  │                  ServerNotification::AgentMessageTextDelta
  │                       ↓ (protocol.rs)
  │                  on_agent_message_delta(delta)
  │                       ↓ (streaming.rs:141)
  │                  handle_streaming_delta(delta)
  │
  └─ reasoning 完成信号 ──→ ResponseEvent::ReasoningSummaryDone
                                ↓ (streaming.rs:276)
                           on_agent_reasoning_final()
                                ↓
                           reasoning_summary_parts → new_reasoning_summary_block()
                                ↓
                           add_boxed_history(ReasoningSummaryCell)
```

### 1.2 Codex 核心组件

#### `ReasoningSummaryCell`（messages.rs:297-367）
```rust
struct ReasoningSummaryCell {
    _header: String,        // 第一个 **bold** 段作为标题（不渲染）
    content: String,        // 完整 markdown 内容
    cwd: PathBuf,           // 用于渲染本地文件链接
    transcript_only: bool,  // header 为空且非 title-only 时为 true
}
```

**渲染逻辑（lines 方法）：**
1. `append_markdown()` 将 content 渲染为终端行
2. 所有行的所有 span 应用 `Style::default().dim().italic()` 样式（灰色+斜体）
3. `adaptive_wrap_lines()` 添加 `• ` 初始缩进和 `  ` 后续缩进

**关键设计决策：**
- **流式时不渲染到 scrollback**——reasoning delta 只更新底部状态栏的 header
- **完成后才创建 ReasoningSummaryCell**——`on_agent_reasoning_final()` 时一次性写入历史
- **transcript_only 标志**——当 header 为空且内容不是纯 bold 标题时，`display_lines()` 返回空（不显示），但 `transcript_lines()` 仍返回内容（导出时保留）

#### `on_agent_reasoning_delta`（streaming.rs:232-274）
```rust
fn on_agent_reasoning_delta(&mut self, delta: String) {
    // 1. 累积到 reasoning_buffer
    self.reasoning_buffer.push_str(&delta);

    // 2. 提取第一个 **bold** 作为状态栏 header（只提取一次，缓存）
    if self.reasoning_header.is_none() {
        self.reasoning_header = extract_first_bold(&self.reasoning_buffer);
    }
    let Some(header) = self.reasoning_header.as_deref() else { return; };

    // 3. 设置状态栏：TerminalTitleStatusKind::Thinking + header
    self.status_state.terminal_title_status_kind = TerminalTitleStatusKind::Thinking;
    self.set_status_header(header);
}
```

#### `on_agent_reasoning_final`（streaming.rs:276-291）
```rust
fn on_agent_reasoning_final(&mut self) {
    // 1. 将 reasoning_buffer 推入 reasoning_summary_parts
    if !self.reasoning_buffer.is_empty() {
        self.reasoning_summary_parts.push(std::mem::take(&mut self.reasoning_buffer));
    }
    // 2. 创建 ReasoningSummaryCell 并添加到历史
    if !self.reasoning_summary_parts.is_empty() {
        let reasoning_parts = std::mem::take(&mut self.reasoning_summary_parts);
        let cell = history_cell::new_reasoning_summary_block(reasoning_parts, &self.config.cwd);
        self.add_boxed_history(cell);
    }
    // 3. 清理状态
    self.reasoning_buffer.clear();
    self.reasoning_header = None;
    self.reasoning_summary_parts.clear();
}
```

#### `StatusIndicatorWidget`（status_indicator_widget.rs:45-61）
- 流式思考时，底部状态栏显示：`shimmer_text(header) [elapsed]`
- `shimmer_text` 使用 `shimmer::shimmer_spans` 产生渐变动画
- `TerminalTitleStatusKind::Thinking` 控制终端标题显示 "Thinking"

### 1.3 Codex 的关键设计原则

| 原则 | Codex 实现 | 我们需要做的 |
|------|-----------|-------------|
| **流式时不渲染 reasoning 到消息区** | delta 只更新底部状态栏 header | 流式时只显示一行预览 + 状态栏 |
| **完成后才写入历史** | `on_agent_reasoning_final()` 创建 Cell | `reasoning_completed` 事件时 finalize |
| **灰色 + 斜体** | `Style::default().dim().italic()` | `var(--dsh-text-3)` + `font-style: italic` |
| **第一个 bold 作为 header** | `extract_first_bold()` | 同上，用于状态栏 |
| **transcript_only 隐藏** | header 为空且非 title-only → 不显示 | 可选：类似逻辑 |
| **Part 分段** | `ReasoningSummaryPartAdded` → `on_reasoning_section_break()` | 可选：多段 reasoning |

---

## 二、当前项目数据流（现状）

### 2.1 后端

```
LLM API Response
  ├─ reasoning_content 字段 ──→ emit_llm_stream()
  │                                ↓
  │                          emit_reasoning_delta()
  │                                ↓
  │                          SSE: reasoning_summary_text_delta { delta, summary_header }
  │
  ├─ content 字段 ──→ ThinkingTagDetector.feed(text)
  │                       ↓
  │                  ├── <thinking> 内 → emit_reasoning_delta()
  │                  └── <thinking> 外 → emit_agent_message_delta()
  │
  └─ reasoning 完成信号 ──→ SSE: reasoning_completed
```

**关键差异：**
- Codex 有 `ReasoningSummaryDone` 事件（携带完整文本），我们只有 `reasoning_completed`（无文本）
- Codex 的 `ReasoningSummaryPartAdded` 用于分段，我们没有
- 我们的 `ThinkingTagDetector` 在后端做分离，Codex 不需要（LLM API 直接分字段）

### 2.2 前端

```
SSE 事件
  ├─ reasoning_summary_text_delta ──→ msg.reasoning += delta
  │                                    streamingThinking = true
  │                                    extract_first_bold → transitionTurn('running', bold)
  │
  ├─ agent_message_delta ──→ pushStreamDelta()
  │                            ↓
  │                       _ingestContentDelta() (检测 <thinking> 标签)
  │                            ↓
  │                       ├── <thinking> 内 → msg.reasoning += delta
  │                       └── <thinking> 外 → StreamPlayer.raw += cleaned
  │
  ├─ reasoning_completed ──→ streamingThinking = false
  │
  └─ workflow_completed ──→ streamingThinking = false
```

### 2.3 当前渲染（AssistantMessageCell.vue）

```
┌─ ReasoningSummaryCell ──────────────────────────────┐
│  🧠 思考过程  <一行预览灰色文字>              ▸     │  ← 收起（默认）
│  ┌──────────────────────────────────────────────┐   │
│  │  灰色 markdown 渲染的完整内容               │   │  ← 展开
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘

┌─ AgentMarkdownCell ─────────────────────────────────┐
│  正式回复内容（v-html="getSafeStreamHtml(msg)"）    │
└─────────────────────────────────────────────────────┘
```

---

## 三、问题诊断

### 3.1 核心问题：思考内容泄漏到主内容区

**根因分析（按可能性排序）：**

#### 可能性 A：`msg.reasoning` 为空，ReasoningSummaryCell 不渲染

**场景：** 非 R1 模型（如 deepseek-chat/v3）不返回 `reasoning_content` 字段，也不使用 `<thinking>` 标签，思考内容直接在 `content` 字段里

**数据流：**
```
LLM content: "让我分析一下这个问题...\n首先...\n\n根据以上分析，答案是..."
  ↓
ThinkingTagDetector.feed() → 找不到 <thinking> 标签
  ↓
emit_agent_message_delta("让我分析一下这个问题...\n首先...\n\n根据以上分析，答案是...")
  ↓
前端 pushStreamDelta() → _ingestContentDelta() 找不到 <thinking> → cleaned = delta
  ↓
StreamPlayer.raw += "让我分析一下这个问题...\n首先...\n\n根据以上分析，答案是..."
  ↓
msg._streamHtml = 渲染后的 HTML（包含大段思考内容）
  ↓
主内容区大段显示思考内容 ✗
```

**msg.reasoning 为空 → ReasoningSummaryCell 不渲染 → 用户看到大段思考内容在主区域**

#### 可能性 B：`msg._streamHtml` 包含 thinking 残留

**场景：** R1 模型的 `reasoning_content` 正常路由到 `msg.reasoning`，但 `content` 字段也包含了部分思考内容（如 `<thinking>` 标签的残留）

**数据流：**
```
LLM reasoning_content: "让我想想..." → reasoning_summary_text_delta → msg.reasoning ✅
LLM content: "<thinking>一些思考</thinking>正式回复" → ThinkingTagDetector 分离
  ├── "一些思考" → reasoning_summary_text_delta → msg.reasoning ✅
  └── "正式回复" → agent_message_delta → StreamPlayer.raw ✅
```

**这种情况应该是正确的。但如果 ThinkingTagDetector 有 bug（如跨 chunk 部分匹配失败），就会泄漏。**

#### 可能性 C：`reasoning_summary_text_delta` 事件未到达前端

**场景：** SSE 连接问题或事件路由问题

**验证方法：** 浏览器 console 中搜索 `[ChatSSE] reasoning_summary_text_delta received`

### 3.2 次要问题：防线逻辑有 bug

当前 `pushStreamDelta` 中的防线：
```typescript
const hasReasoning = !!(msg.reasoning && msg.reasoning.length > 0)
if ((callbacks.streamingThinking.value || hasReasoning) && !inThink && cleaned === delta) {
    msg.reasoning += delta
    return
}
```

**问题：** `cleaned === delta` 这个条件不可靠——`_ingestContentDelta` 可能修改了 delta（如剥离了部分标签），导致 `cleaned !== delta`，防线失效。

---

## 四、精确实现方案

### 4.1 总体策略：对齐 Codex 三阶段模型

| 阶段 | Codex | 我们 |
|------|-------|------|
| **流式思考中** | delta → reasoning_buffer，只更新状态栏 header | delta → msg.reasoning，显示一行预览 + 状态栏 |
| **思考完成** | `on_agent_reasoning_final()` → 创建 ReasoningSummaryCell | `reasoning_completed` → 标记 settled，渲染完整 markdown |
| **正式回复** | `on_agent_message_delta()` → StreamController | `agent_message_delta` → StreamPlayer |

### 4.2 修改清单

---

#### 修改 1：后端 — 确保所有思考内容走 reasoning 通道

**文件：** `backend/app/engine/harness/executor/loop.py`

**现状：** `ThinkingTagDetector` 只处理 `content` 字段中的 `<thinking>` 标签。如果 LLM 不使用标签（非 R1 模型），思考内容直接走 `agent_message_delta`。

**修改：** 无需修改后端。后端已经正确：
- `reasoning_content` 字段 → `emit_reasoning_delta` ✅
- `<thinking>` 标签 → `ThinkingTagDetector` 分离 → `emit_reasoning_delta` ✅
- 无标签的 content → `emit_agent_message_delta` ✅（这是正确行为——非 R1 模型的 content 就是正式回复）

**关键认知：** 如果 LLM 不返回 `reasoning_content` 且不使用 `<thinking>` 标签，那 `content` 里就没有思考内容——它就是正式回复。**思考内容泄漏问题不在后端。**

---

#### 修改 2：前端 SSE — 修复 pushStreamDelta 防线

**文件：** `frontend/src/components/chat/composables/useChatSSE.ts`

**问题：** 当前防线的 `cleaned === delta` 条件不可靠。

**修改：** 移除不可靠的防线，改为更简洁的逻辑：

```typescript
function pushStreamDelta(msg: ChatMessage, delta: string) {
    if (!delta) return
    if (!streamedPlaceholderReplaced.has(msg)) {
        msg.content = ''
        streamedPlaceholderReplaced.add(msg)
    }
    const cleaned = _ingestContentDelta(msg, delta)
    const inThink = !!(msg as any)._thinkState?.inThink
    if (inThink) {
        callbacks.streamingThinking.value = true
    }
    if (!cleaned) return
    const p = _ensureStreamPlayer(msg)
    p.raw += cleaned
    ;(msg as any)._contentFromSSE = true
    callbacks.streamingHasContent.value = true
    callbacks.transitionTurn('running', '生成回复中…')
    callbacks.onStreamDelta?.()
}
```

**理由：** `_ingestContentDelta` 已经正确处理了 `<thinking>` 标签（路由到 `msg.reasoning`，返回标签外内容）。后端 `ThinkingTagDetector` 也已经分离了。所以到达 `pushStreamDelta` 的 delta 应该不包含思考内容。之前的防线是多余的且有害的。

---

#### 修改 3：前端渲染 — 对齐 Codex ReasoningSummaryCell

**文件：** `frontend/src/components/chat/AssistantMessageCell.vue`

**3a. 模板：** 对齐 Codex 的三阶段渲染

```vue
<!-- ReasoningSummaryCell -->
<div v-if="msg.reasoning" class="dsh-cell dsh-cell-reasoning"
     :class="{ 'dsh-cell-reasoning-streaming': isCurrentlyStreamingThinking }">
  <!-- Header：点击展开/收起 -->
  <div class="dsh-cell-header" @click="toggleExpand(msg, 'reasoning')">
    <Brain :size="14" class="dsh-cell-icon" />
    <span class="dsh-cell-label">
      {{ isCurrentlyStreamingThinking ? '正在思考' : '思考过程' }}
    </span>
    <!-- 收起时：一行预览（对齐 Codex 的状态栏 header） -->
    <span v-if="!isExpanded(msg, 'reasoning')"
          class="dsh-cell-streaming-preview"
          :class="{ 'dsh-cell-streaming-preview--settled': !isCurrentlyStreamingThinking }">
      {{ getReasoningPreview(msg.reasoning) }}
    </span>
    <span class="dsh-cell-chevron"
          :style="{ transform: isExpanded(msg, 'reasoning') ? 'rotate(90deg)' : 'rotate(0deg)' }">▸</span>
  </div>
  <!-- Body：展开时渲染完整 markdown -->
  <Transition name="dsh-slide">
    <div v-show="isExpanded(msg, 'reasoning')" class="dsh-cell-body dsh-cell-reasoning-body">
      <div v-html="renderMarkdown(msg.reasoning)"
           class="dsh-cell-reasoning-content"
           :class="{ 'dsh-cell-reasoning-content--streaming': isCurrentlyStreamingThinking }">
      </div>
    </div>
  </Transition>
</div>
```

**3b. 主内容渲染：** 移除 `getSafeStreamHtml` 中的复杂清理逻辑

```typescript
function getSafeStreamHtml(msg: ChatMessage): string {
  if (msg._streamHtml) {
    return stripThinkingFromHtml(msg._streamHtml)
  }
  return renderMarkdown(sanitizeContent(stripThinkingFromContent(msg.content || '')))
}
```

移除 `stripReasoningLeakFromHtml` 和 `stripReasoningLeakFromContent`——这些基于文本匹配的清理不可靠且不必要。

**3c. stripThinkingFromHtml 增强：** 处理 markdown 渲染后的 `<thinking>` 残留

```typescript
function stripThinkingFromHtml(html: string): string {
  if (!html) return ''
  return html
    .replace(/<thinking>[\s\S]*?<\/thinking>/gi, '')
    .replace(/<thinking>[\s\S]*$/gi, '')
    .replace(/<p>&lt;thinking&gt;[\s\S]*?&lt;\/thinking&gt;<\/p>/gi, '')
    .replace(/<p>&lt;thinking&gt;[\s\S]*$/gi, '')
    .replace(/<code>&lt;\/thinking&gt;<\/code>/g, '')
    .trim()
}
```

---

#### 修改 4：CSS — 对齐 Codex 的 dim + italic 样式

**文件：** `frontend/src/components/chat/chat-view.css`

```css
/* 对齐 Codex ReasoningSummaryCell: Style::default().dim().italic() */
.dsh-cell-reasoning {
  background: transparent;
  border: none;
}

.dsh-cell-reasoning .dsh-cell-header {
  color: var(--dsh-text-3);
  font-size: 12px;
  letter-spacing: 0.02em;
}

.dsh-cell-reasoning .dsh-cell-icon {
  color: var(--dsh-text-3);
}

/* 一行预览：对齐 Codex 状态栏的 shimmer header */
.dsh-cell-streaming-preview {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dsh-text-3);
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.7;
}

.dsh-cell-streaming-preview--settled {
  opacity: 0.5;
  font-style: italic;
}

/* 展开后的 body：对齐 Codex dim + italic */
.dsh-cell-reasoning-body {
  color: var(--dsh-text-3);
  font-size: 12.5px;
  line-height: 1.6;
  font-style: italic;
  border-top: 1px solid color-mix(in srgb, var(--dsh-border) 40%, transparent);
  margin-top: 0;
  padding-top: 6px;
}

.dsh-cell-reasoning-content {
  color: var(--dsh-text-3);
}

/* 流式时光标闪烁：对齐 Codex shimmer 动画 */
.dsh-cell-reasoning-content--streaming::after {
  content: '▍';
  animation: dsh-reasoning-cursor 1s step-end infinite;
  color: var(--dsh-text-3);
  margin-left: 1px;
}

/* 流式时 header 脉冲 */
.dsh-cell-reasoning-streaming .dsh-cell-icon {
  animation: dsh-reasoning-pulse 1.5s ease-in-out infinite;
  will-change: opacity;
}

@keyframes dsh-reasoning-cursor {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

@keyframes dsh-reasoning-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
```

---

#### 修改 5：调试日志 — 移除 console.log

**文件：** `useChatSSE.ts` 和 `AssistantMessageCell.vue`

移除所有 `console.log` 调试日志（搜索 `[pushStreamDelta]`、`[ChatSSE] reasoning`、`[StreamPlayer]`）。

---

## 五、验证清单

### 5.1 功能验证

| 场景 | 预期 | 验证方法 |
|------|------|---------|
| R1 模型思考 | 🧠 正在思考 + 一行灰色预览 → 点击展开看完整内容 | 新对话，观察 ReasoningSummaryCell |
| R1 模型回复 | 主内容区只显示正式回复，无思考内容泄漏 | 检查主内容区无大段思考文字 |
| 非 R1 模型 | 无 ReasoningSummaryCell，主内容区直接显示回复 | 切换模型测试 |
| 流式思考中 | 一行预览实时更新，光标闪烁 | 观察流式过程 |
| 思考完成 | 预览固定，无光标闪烁，可展开 | 等待思考完成 |
| 历史消息 | reasoning 字段已持久化 → ReasoningSummaryCell 显示 | 刷新页面，检查历史消息 |

### 5.2 数据验证

在浏览器 console 中执行：
```javascript
// 检查最新消息的 reasoning 和 content
const msgs = document.querySelectorAll('.dsh-assistant-row')
console.log('reasoning:', msgs[0]?.__vue__?.msg?.reasoning?.length)
console.log('content:', msgs[0]?.__vue__?.msg?.content?.length)
console.log('_streamHtml:', msgs[0]?.__vue__?.msg?._streamHtml?.length)
```

### 5.3 样式验证

- 思考过程文字颜色 = `var(--dsh-text-3)`（灰色）
- 展开后文字 = italic
- 预览文字 = 单行截断 + ellipsis
- 流式时 = 光标闪烁动画

---

## 六、Codex 源码关键引用

| 组件 | 文件路径 | 行号 |
|------|---------|------|
| ReasoningSummaryCell | `codex-rs/tui/src/history_cell/messages.rs` | 297-367 |
| new_reasoning_summary_block | `codex-rs/tui/src/history_cell/messages.rs` | 629-645 |
| split_reasoning_summary_parts | `codex-rs/tui/src/history_cell/messages.rs` | 648-696 |
| on_agent_reasoning_delta | `codex-rs/tui/src/chatwidget/streaming.rs` | 232-274 |
| on_agent_reasoning_final | `codex-rs/tui/src/chatwidget/streaming.rs` | 276-291 |
| on_reasoning_section_break | `codex-rs/tui/src/chatwidget/streaming.rs` | 293-300 |
| protocol 事件路由 | `codex-rs/tui/src/chatwidget/protocol.rs` | 82-90 |
| StatusIndicatorWidget | `codex-rs/tui/src/status_indicator_widget.rs` | 45-61 |
| shimmer_text | `codex-rs/tui/src/motion.rs` | 52-63 |
| ReasoningSummaryTextDeltaNotification | `codex-rs/app-server-protocol/src/protocol/v2/item.rs` | 1372-1379 |
| event_mapping (ReasoningContentDelta → ReasoningSummaryTextDelta) | `codex-rs/app-server-protocol/src/protocol/event_mapping.rs` | 378-386 |
| ReasoningSummary enum | `codex-rs/protocol/src/config_types.rs` | 65-72 |
| ChatWidget.reasoning_buffer | `codex-rs/tui/src/chatwidget.rs` | 649 |
| ChatWidget.reasoning_header | `codex-rs/tui/src/chatwidget.rs` | 651 |
| ChatWidget.reasoning_summary_parts | `codex-rs/tui/src/chatwidget.rs` | 653 |
| TerminalTitleStatusKind::Thinking | `codex-rs/tui/src/chatwidget/status_state.rs` | 32-37 |
| turn.rs ReasoningSummaryDelta 处理 | `codex-rs/core/src/session/turn.rs` | 2635-2658 |
| turn.rs ReasoningContentDelta 处理 | `codex-rs/core/src/session/turn.rs` | 2711-2731 |