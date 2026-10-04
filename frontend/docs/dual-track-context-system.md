# 双轨上下文系统 — 设计文档

> 版本: v1.0  
> 日期: 2026-09-26  
> 状态: 已实现，类型检查通过，构建通过

---

## 1. 问题背景

Chat 页面原有侧边栏存在两个核心问题：

| 问题 | 表现 |
|------|------|
| **排版问题** | 侧边栏在左侧，点击采集作品时在页面中间弹出，遮挡对话区域 |
| **信息同步问题** | 侧边栏信息无法可靠地注入到对话上下文中，依赖关键词匹配（"分析"、"优化"等），漏注和误注频发 |

此外，侧边栏功能单一（仅展示作品详情），无法承载采集列表、快捷工具等能力。

## 2. 方案选型

| 方案 | 描述 | 优劣 |
|------|------|------|
| A. 事件总线 | 侧边栏 emit 事件，Chat 监听 | 松耦合但调试难，事件流不可追踪 |
| B. Props 层层传递 | 父组件中转数据 | 组件层级深时 props drilling 严重 |
| **C. 双轨上下文系统** | **Pinia store 作为单一真相源，Chat 和 Sidebar 都从同一轨道拉数据** | **数据流清晰可追踪，pin/unpin 精确控制注入，扩展性强** |

**选定方案 C。**

## 3. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        WorkbenchView                            │
│  ┌──────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │SidebarNav│  │      ChatView        │  │ ContextSidebar   │  │
│  │          │  │                      │  │ ┌──────────────┐ │  │
│  │ 选择作品  │──┤  work-bar (顶部条)   │  │ │ 轨道│作品│采集│工具│  │
│  │          │  │                      │  │ ├──────────────┤ │  │
│  │          │  │  对话消息区           │  │ │  内容区       │ │  │
│  │          │  │                      │  │ └──────────────┘ │  │
│  └──────────┘  └──────────────────────┘  └──────────────────┘  │
│                         │                      ▲               │
│                         ▼                      │               │
│              ┌─────────────────────┐           │               │
│              │  chatContext Store  │───────────┘               │
│              │  (单一真相源)        │                           │
│              │                     │                           │
│              │  contextTrack ──────┤── buildSystemPrompt()    │
│              │  sidebarVisible     │       │                   │
│              │  sidebarTab         │       ▼                   │
│              │  pendingSignals     │  messagesPayload.unshift  │
│              └─────────────────────┘  ({ role:'system', ...})  │
└─────────────────────────────────────────────────────────────────┘
```

### 核心原则

1. **单一真相源**：`chatContext` store 是上下文数据的唯一权威来源
2. **拉而非推**：Chat 和 Sidebar 都从 store 拉数据，而非互相推送
3. **钉选即注入**：用户通过 pin/unpin 精确控制什么进入对话，而非全量注入
4. **去重合并**：同一 `(type, refId)` 组合的上下文项自动合并，不会重复添加

## 4. 数据模型

### 4.1 ContextItem — 上下文轨道中的条目

```typescript
export type ContextItemType = 'work' | 'analysis' | 'file' | 'creation' | 'search' | 'workspace'

export interface ContextItem {
  id: string              // 格式: ctx-{type}-{refId}
  type: ContextItemType   // 条目类型
  label: string           // 显示名（如作品标题）
  summary: string         // 一行摘要（如"小红书 · 图文 · A级"）
  pinned: boolean         // 是否钉选（钉选 = 自动注入对话）
  addedAt: number         // 添加时间戳
  meta: Record<string, any>  // 类型特定数据
}
```

各类型 meta 结构：

| type | meta 字段 | 说明 |
|------|-----------|------|
| `work` | `refId, platform, contentType, performanceTier` | 关联的作品 |
| `analysis` | `refId: 'analysis-latest', overview` | 数据分析报告 |
| `file` | `refId, fileName, contentPreview` | 关联文件 |
| `creation` | `refId, draftTitle, contentType` | 创作草稿 |
| `search` | `refId, query, resultCount` | 搜索结果 |
| `workspace` | `refId, workspaceName, workspacePath` | 工作区 |

### 4.2 SidebarSignal — 对话驱动信号

```typescript
export interface SidebarSignal {
  type: 'show-work' | 'show-analysis' | 'show-creation' | 'highlight-metric' | 'show-file' | 'show-workspace'
  payload: Record<string, string | number | boolean | null>
  source: 'ai-message' | 'user-action'
}
```

信号机制允许 AI 回复驱动侧边栏行为（如 AI 提到某作品 → 侧边栏自动切到该作品详情）。

### 4.3 Store 状态

```typescript
// 核心状态
contextTrack: Ref<ContextItem[]>        // 有序上下文队列
sidebarVisible: Ref<boolean>            // 侧边栏是否可见
sidebarTab: Ref<'context'|'detail'|'collection'|'tools'>  // 当前 Tab
sidebarWidth: Ref<number>               // 面板宽度 (240-600px)
pendingSignals: Ref<SidebarSignal[]>    // 待消费信号队列

// 派生计算
pinnedItems: ComputedRef<ContextItem[]>   // 钉选的条目
unpinnedItems: ComputedRef<ContextItem[]> // 未钉选的条目
activeWorkId: ComputedRef<string|null>    // 当前活跃作品 ID
activeWork: ComputedRef<WorkItem|null>    // 当前活跃作品
```

## 5. 核心 API

### 5.1 上下文轨道操作

| 方法 | 签名 | 行为 |
|------|------|------|
| `addContextItem` | `(item: Omit<ContextItem, 'id'\|'addedAt'>) => ContextItem \| null` | 添加条目，同 `(type, refId)` 自动合并（保留较新的 label/summary，pin 状态取并集）。轨道满时返回 `null` |
| `removeContextItem` | `(id: string) => void` | 按 id 移除 |
| `togglePin` | `(id: string) => void` | 切换钉选状态 |
| `clearUnpinned` | `() => void` | 清除所有未钉选条目 |
| `clearAll` | `() => void` | 清空轨道 |

### 5.2 关联/解除操作

| 方法 | 签名 | 行为 |
|------|------|------|
| `linkWork` | `(workId: string) => void` | 关联作品：设 activeWork（若非当前）→ 加入 track 并 pin → 打开侧边栏切到 detail tab |
| `unlinkWork` | `(workId?: string) => void` | 解除作品：移除指定 workId 的 track 条目（默认 activeWorkId），清 activeWork |
| `linkAnalysis` | `(data: Record<string,any>) => void` | 关联分析：设 analysisContext → 加入 track（默认不 pin） |
| `unlinkAnalysis` | `() => void` | 解除分析：清 analysisContext → 移除 track 中 analysis 条目 |

### 5.3 侧边栏控制

| 方法 | 签名 | 行为 |
|------|------|------|
| `setSidebarVisible` | `(v: boolean) => void` | 控制显隐 |
| `toggleSidebar` | `() => void` | 切换显隐 |
| `setSidebarTab` | `(tab) => void` | 切换 Tab |
| `setSidebarWidth` | `(w: number) => void` | 设置宽度（clamp 240-600，持久化到 localStorage） |

### 5.4 信号机制

| 方法 | 签名 | 行为 |
|------|------|------|
| `emitSignal` | `(signal: SidebarSignal) => void` | 发出信号（AI 回复或用户操作触发） |
| `consumeSignal` | `() => SidebarSignal \| null` | 消费一个信号（FIFO） |

### 5.5 上下文注入

| 方法 | 签名 | 行为 |
|------|------|------|
| `buildSystemPrompt` | `() => string \| null` | 遍历 pinnedItems，按类型序列化为 system prompt 字符串；无 pinned 项时返回 null |
| `shouldInjectContext` | `() => boolean` | 是否有需要注入的上下文 |

## 6. buildSystemPrompt 序列化规则

对每个 pinned item，按 type 分别序列化：

### work 类型

```
=== 作品信息 ===
标题: {work.title}
平台: {getPlatformLabel(work.platform)}
类型: {getContentTypeLabel(work.contentType)}
等级: {work.performanceTier}

正文内容:
{work.contentText.slice(0, 800)}

脚本内容:
{work.scriptText.slice(0, 800)}

标签: {work.tags.slice(0, 10).join(', ')}
数据: 浏览{views} | 点赞{likes} | 收藏{collects} | 互动率{ir}%
AI诊断: {work.aiDiagnosis.performanceReason}
下一步: {work.aiDiagnosis.nextAction}
```

**关键设计**：直接按 `item.meta.refId` 从 `workStore.works` 查找对应作品，而非取 `workStore.activeWork`。这确保多 work pin 时每个都能正确序列化。

### analysis 类型

委托 `workStore.buildAnalysisPrompt()` 生成。

### file / creation / workspace 类型

按 meta 字段直接拼接键值对。

### 尾部强制要求

所有序列化内容后追加：

```
=== 强制要求 ===
1. 回答时必须引用上述上下文中的实际内容，不要说"没有内容"或"未保存"
2. 如果用户要求分析/优化/改写，直接针对上述内容进行操作
3. 绝对禁止回复"草稿文件还没有保存"或类似的内容缺失提示
4. 上下文内容已经完整提供给你，立即开始工作！
```

## 7. 数据流

### 7.1 用户选择作品

```
SidebarNav: @select-work(workId)
  → WorkbenchView.handleSelectWork(workId)
    → workStore.setActiveWork(workId)
    → ctxStore.linkWork(workId)
      → [if activeWorkId !== workId] workStore.setActiveWork(workId)  // 守卫，避免冗余
      → addContextItem({ type:'work', pinned:true, meta:{refId:workId} })
      → sidebarVisible = true
      → sidebarTab = 'detail'
    → ChatView: activeWork watch 触发
      → ctxStore.setSidebarVisible(true)
      → ctxStore.linkWork(newWork.id)   // linkWork 内部有守卫，不会重复 setActiveWork
      → switchToWorkConversation(newWork.id)
```

### 7.2 用户发送消息

```
ChatInput: 发送
  → useChatSend.sendMessageReal()
    → 构建 messagesPayload（过滤空消息，映射 role+content）
    → ctxStore.buildSystemPrompt()
      → 遍历 pinnedItems
      → 按 type 序列化
      → 拼接强制要求
      → 返回 system prompt 字符串（或 null）
    → if (contextSystemPrompt):
        messagesPayload.unshift({ role:'system', content: contextSystemPrompt })
    → POST /api/v1/chat/completions
```

### 7.3 AI 回复驱动侧边栏

```
AI 回复中包含特定标记
  → ctxStore.emitSignal({ type:'show-work', payload:{workId}, source:'ai-message' })
  → ContextSidebar: watch(pendingSignals.length)
    → signal = ctxStore.consumeSignal()
    → ctxStore.linkWork(signal.payload.workId)  // 自动关联并切换
```

### 7.4 用户解除作品关联

```
work-bar: 点击 X 按钮
  → exitWorkContext()
    → ctxStore.unlinkWork()
      → workStore.setActiveWork(null)
      → 移除 track 中指定 workId 的条目（默认 activeWorkId）
    → showWorkDetail.value = false  // setter 同步 ctxStore.setSidebarVisible(false)
    → ctxStore.setSidebarVisible(false)
```

## 8. 组件结构

### 8.1 ContextSidebar

```
<aside class="ctx-sidebar" :style="{ width: ctxStore.sidebarWidth + 'px' }">
  <div class="ctx-header">
    <tabs: 轨道 | 作品 | 采集 | 工具>
    <close button>
  </div>
  <div class="ctx-body">
    [轨道] contextTrack 列表，每项可 pin/unpin/remove
    [作品] WorkDetailPanel（异步加载）
    [采集] worksByStatus.collected 列表，点击 linkWork
    [工具] 快捷操作按钮组（创作/分析/发布）
  </div>
</aside>
```

Tab 说明：

| Tab | 图标 | 内容 | 空状态提示 |
|-----|------|------|-----------|
| 轨道 | Layers | contextTrack 全部条目 | "关联作品、文件或分析后，它们会出现在这里" |
| 作品 | FileText | WorkDetailPanel | "在左侧导航选择一个作品，或从采集列表中关联" |
| 采集 | Search | collected works 列表 | "通过对话或添加链接来采集作品" |
| 工具 | Wrench | 创作/分析/发布快捷按钮 | — |

### 8.2 ChatView 布局变更

**之前**：
```
[Chat] [resize-bar] [WorkDetailPanel(左)]
```

**之后**：
```
[Chat] [resize-bar] [ContextSidebar(右)]
```

关键改动：
- 移除左侧 `WorkDetailPanel` + `dsh-detail-resize-bar`
- 添加右侧 `ContextSidebar` + `dsh-ctx-resize-bar`
- `toggleWorkDetail()` 改为操作 `ctxStore.sidebarVisible`
- work-bar 按钮高亮改为 `ctxStore.sidebarVisible`
- 分析联动解除按钮改为 `ctxStore.unlinkAnalysis()`

### 8.3 状态同步关系

```
workStore.showWorkDetail  ←→  ctxStore.sidebarVisible
         ↑                          ↑
         │    showWorkDetail        │
         │    computed setter       │
         └── set 时同步 ───────────┘
```

`showWorkDetail` 的 setter 同时写 `workStore.showWorkDetail` 和 `ctxStore.sidebarVisible`，确保双源一致。

## 9. 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/stores/chatContext.ts` | 新增 | 双轨上下文编排器，单一真相源 |
| `src/components/chat/ContextSidebar.vue` | 新增 | 右侧上下文侧边栏组件 |
| `src/components/chat/ChatView.vue` | 修改 | 布局重构，集成 ContextSidebar |
| `src/components/chat/composables/useChatSend.ts` | 修改 | 消息发送时注入上下文 |
| `src/components/chat/composables/useChatWork.ts` | 修改 | exitWorkContext 走 ctxStore，showWorkDetail setter 同步 |
| `src/components/chat/chat-view.css` | 修改 | 右侧 resize bar 样式 |
| `src/views/WorkbenchView.vue` | 修改 | handleSelectWork/handleCreateDraft 联动 ctxStore |

## 10. 样式规格

### 10.1 侧边栏

| 属性 | 值 |
|------|-----|
| 位置 | 右侧，flex-shrink: 0 |
| 默认宽度 | `Math.max(280, Math.min(420, Math.floor(innerWidth / 4)))` |
| 宽度范围 | 240px — 600px |
| 宽度持久化 | localStorage key: `ctx-sidebar-width` |
| 边框 | 左侧 1px solid rgba(0,0,0,0.08) |
| 暗色 | `.is-dark` class，背景 #1e1e1e |

### 10.2 Resize Bar

| 属性 | 值 |
|------|-----|
| 宽度 | 24px（视觉 2px，margin 左右各 -12px 重叠） |
| 光标 | col-resize |
| 拖拽方向 | 向左拖 → 宽度增大；向右拖 → 宽度减小 |
| 双击 | 恢复默认宽度 |
| hover | opacity 1, 背景 rgba(0,0,0,0.06) |

### 10.3 上下文条目

| 状态 | 边框 | 背景 |
|------|------|------|
| 默认 | rgba(0,0,0,0.06) | #fafafa |
| hover | rgba(0,0,0,0.1) | #f5f5f5 |
| pinned | rgba(59,130,246,0.25) | rgba(59,130,246,0.03) |
| pinned hover | rgba(59,130,246,0.35) | rgba(59,130,246,0.06) |

类型图标颜色：

| type | 颜色 | 背景 |
|------|------|------|
| work | #4a90d9 | rgba(74,144,217,0.08) |
| analysis | #f97316 | rgba(249,115,22,0.08) |
| file | #8b5cf6 | rgba(139,92,246,0.08) |
| creation | #10b981 | rgba(16,185,129,0.08) |
| search | #6b7280 | rgba(107,114,128,0.08) |
| workspace | #eab308 | rgba(234,179,8,0.08) |

## 11. 已修复的问题（第一轮）

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 1 | P0 | `exitWorkContext()` 没清理 ctxStore | 改调 `ctxStore.unlinkWork()` + `ctxStore.setSidebarVisible(false)` |
| 2 | P0 | `showWorkDetail` 双源驱动冲突 | setter 中同步 `ctxStore.setSidebarVisible(v)` |
| 3 | P0 | `buildSystemPrompt()` 只取 activeWork | 改为按 `item.meta.refId` 从 `workStore.works` 查找 |
| 4 | P0 | 分析联动解除按钮没走 ctxStore | 改调 `ctxStore.unlinkAnalysis()` |
| 5 | P1 | work-bar 按钮高亮与侧边栏状态不一致 | 改为 `ctxStore.sidebarVisible` |
| 6 | P1 | `_resetToInitial()` 没清理 ctxStore | 加 `setSidebarVisible(false)` + `clearAll()` |
| 7 | P1 | `linkWork()` 冗余调 `setActiveWork` | 加 `if (activeWorkId !== workId)` 守卫 |
| 8 | P1 | WorkDetailPanel 同步 import | 改为 `defineAsyncComponent` |
| 9 | P2 | 侧边栏无暗色主题 | 加 `.is-dark` class + 完整暗色 CSS |

## 12. 已修复的边界问题（第二轮）

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 10 | P0 | 序列化字段无 null 守卫 | `contentText`/`scriptText`/`tags`/`aiDiagnosis` 全部加 nullish 检查；数值字段用 `??` 替代 `||`；`tags` 用 `Array.isArray()` 守卫 |
| 11 | P0 | refId 查找失败无 fallback | work 查找失败时用 track 中的 label/summary 作为降级内容，标记 `orphanItemIds`，UI 显示"⚠ 原始数据已丢失" |
| 12 | P0 | `setSidebarVisible` 双向同步不完整 | `setSidebarVisible` 内同步写 `workStore.showWorkDetail`；`toggleSidebar` 改为调 `setSidebarVisible` |
| 13 | P0 | 对话级上下文未隔离 | 新增 `boundConversationId` + `bindConversation(convId)` + `isContextForConversation(convId)`；`sendMessageReal` 中调 `bindConversation(conv.id)`；切换对话时保存/恢复轨道（分桶存储） |
| 14 | P1 | `unlinkWork` 移除所有 work 条目 | 改为 `unlinkWork(workId?)` 只移除指定 workId（默认 activeWorkId），不再误伤其他 pinned work |
| 15 | P1 | System prompt 无总长度上限 | 新增 `MAX_SYSTEM_PROMPT_LEN = 6000`，超长时截断 + 追加截断提示 + console.warn |
| 16 | P1 | `_resetToInitial` 未清信号 | `clearAll()` 中追加 `pendingSignals.value = []` |
| 17 | P1 | 信号队列无上限无去重 | `emitSignal` 加 `MAX_SIGNALS = 10` 上限 + 同 type+payload 去重 |
| 18 | P1 | localStorage 初始值未校验 | `sidebarWidth` 初始化改为 IIFE，校验 `Number.isFinite` + 范围 240-600 |
| 19 | P2 | contextTrack 无上限 | `addContextItem` 加 `MAX_TRACK_SIZE = 20`，满时优先淘汰最旧的未钉选条目 |
| 20 | P2 | 截断无标记 | `contentText`/`scriptText` 截断时追加 `…` 标记 |

### 12.1 新增 API

| 方法 | 签名 | 行为 |
|------|------|------|
| `bindConversation` | `(convId: string \| null) => void` | 绑定对话 ID；切换对话时保存/恢复轨道（分桶存储） |
| `isContextForConversation` | `(convId: string \| null) => boolean` | 检查当前上下文是否属于指定对话 |
| `unlinkWork` (升级) | `(workId?: string) => void` | 只移除指定 workId，默认 activeWorkId |

### 12.2 新增状态

| 状态 | 类型 | 说明 |
|------|------|------|
| `boundConversationId` | `Ref<string \| null>` | 当前上下文绑定的对话 ID |
| `orphanItemIds` | `Ref<Set<string>>` | 原始数据已丢失的条目 ID 集合 |

### 12.3 新增常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `MAX_SYSTEM_PROMPT_LEN` | 6000 | system prompt 最大字符数 |
| `MAX_CONTENT_SLICE` | 800 | 单个内容字段最大截断长度 |
| `MAX_TRACK_SIZE` | 20 | 轨道最大条目数 |
| `MAX_SIGNALS` | 10 | 信号队列最大长度 |

## 13. 已修复的边界问题（第三轮）

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 21 | P1 | `bindConversation` 切换对话清空轨道，切回时上下文丢失 | 改为分桶存储：`conversationBuckets: Map<convId, ContextItem[]>`，切换时保存当前轨道到桶、从桶恢复目标对话的轨道 |
| 22 | P1 | 全钉选时 `addContextItem` 静默失败 | 返回 `null` + 设 `trackFull = true`，UI 显示"轨道已满，请先取消部分钉选" |
| 23 | P1 | `unlinkWork()` 在 `activeWorkId=null` 时可能匹配异常条目 | 先查 targetItem，找不到直接 return；`activeWorkId` 为 null 时 early return |
| 24 | P2 | 信号去重 payload 对象浅比较永远不等 | 改为 `stableStringify`：key 排序后 JSON 序列化，确保 `{"a":1,"b":2}` 与 `{"b":2,"a":1}` 视为相同 |
| 25 | P2 | orphaned item 仍 pin 时序列化产出残缺数据 + 强制要求 → AI 幻觉 | orphaned work 自动 `togglePin(id)` 取消钉选 + 序列化时跳过，不再注入残缺内容 |
| 26 | P2 | 空内容 pinned item + 强制要求 → AI 幻觉 | 每个 type 序列化到 `local[]`，`local.length === 0` 时不推入全局 `parts`，确保只有有效内容才注入 |
| 27 | P2 | `bindConversation` 与信号消费竞态 | `bindConversation` 切换时同步清空 `pendingSignals`，防止 A 的信号在 B 中被消费 |

### 13.1 新增/变更 API

| 方法 | 变更 | 说明 |
|------|------|------|
| `addContextItem` | 返回值从 `ContextItem` 改为 `ContextItem \| null` | 轨道满时返回 null |
| `bindConversation` | 内部改为分桶存储 | 切换时保存/恢复而非清空 |
| `stableStringify` | 新增内部函数 | key 排序 JSON 序列化，用于信号去重 |

### 13.2 新增状态

| 状态 | 类型 | 说明 |
|------|------|------|
| `conversationBuckets` | `Ref<Map<string, ContextItem[]>>` | 按对话 ID 分桶存储上下文轨道 |
| `trackFull` | `Ref<boolean>` | 轨道是否已满（全钉选无法添加新条目） |

## 14. 已修复的边界问题（第四轮）

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 28 | P1 | `conversationBuckets` 无限增长，内存泄漏 | `MAX_BUCKETS = 20` LRU 淘汰 + 空轨道不存桶 |
| 29 | P1 | `trackFull` 不自动重置，unpin 后 UI 仍显示"轨道已满" | `removeContextItem`/`togglePin`/`clearUnpinned`/`clearAll` 中重置 `trackFull = false` |
| 30 | P2 | `addContextItem` 返回值变更为 `ContextItem \| null`，调用方未做 null 检查 | `linkWork`/`linkAnalysis` 加 null 守卫，轨道满时不执行后续操作 |
| 31 | P2 | `orphanItemIds` 不随桶走，切对话后状态错乱 | `bindConversation` 切换时重置 `orphanItemIds`，恢复桶后调 `revalidateOrphans()` 重新检测 |
| 32 | P2 | 桶恢复后 orphaned work 的 pinned=true 未被处理 | `revalidateOrphans()` 遍历恢复的条目，orphaned work 自动 unpin |
| 33 | P2 | `stableStringify` 对 undefined/循环引用无防护 | `SidebarSignal.payload` 收窄为 `Record<string, string \| number \| boolean \| null>` + try-catch fallback |
| 34 | P2 | `bindConversation(null)` 语义未定义 | 新增 `unbindConversation()` 语义：保存当前桶 → 解绑 → 轨道清空 |
| 35 | P2 | 桶不持久化，刷新后丢失 | 当前版本为内存级缓存，v2 扩展点 #1 持久化解决；文档显式声明此限制 |

### 14.1 新增/变更 API

| 方法 | 变更 | 说明 |
|------|------|------|
| `saveCurrentBucket` | 新增内部函数 | 保存当前轨道到桶（空轨道不存 + LRU 淘汰） |
| `revalidateOrphans` | 新增内部函数 | 遍历 contextTrack，orphaned work 自动 unpin |
| `unbindConversation` | 新增公开方法 | `bindConversation(null)` 的语义别名 |
| `SidebarSignal.payload` | 类型收窄 | `Record<string, any>` → `Record<string, string \| number \| boolean \| null>` |

### 14.2 新增常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `MAX_BUCKETS` | 20 | 对话桶最大数量（LRU 淘汰） |

## 15. 已修复的边界问题（第五轮）

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 36 | P2 | LRU 淘汰机制未定义实现方式 | 利用 Map 插入有序性：`bindConversation` 恢复桶时先 delete 再 set，最近访问的桶始终在 Map 末尾，淘汰时删除 Map 第一项 |
| 37 | P2 | `linkWork` 轨道满时跳过全部操作，用户点击无反馈 | 调整执行顺序：先 `setActiveWork` + `sidebarVisible` + `sidebarTab`（用户看到作品详情），再 `addContextItem`（失败时仅不加入轨道，不影响 UI） |
| 38 | P2 | `revalidateOrphans` 依赖 workStore 已加载，未加载时全部误判 orphaned | 加 `if (workStore.isLoading) return` 守卫，works 未加载时跳过检测 |
| 39 | P2 | `contentPreview` 截断无标记 | 与 contentText/scriptText 统一：`length > MAX_CONTENT_SLICE` 时追加 `…` |

### 15.1 设计声明（文档补全，非代码修改）

| 编号 | 声明 |
|------|------|
| D1 | **合并键是 `(type, refId)` 组合**：同 refId 不同 type 视为不同条目，不会合并。id 格式 `ctx-{type}-{refId}` 天然保证这一点 |
| D2 | **Pin 并集语义为设计意图**：合并时 `pinned = A || B`，只升不降。业务理由：pin 表示"用户显式要求注入"，不应被后续自动添加覆盖 |
| D3 | **信号队列为单消费者模式**：当前仅 ContextSidebar 消费。未来扩展多消费者时需改为发布-订阅模式指定目标 |
| D4 | **`SidebarSignal.payload` 类型已收窄为 `Record<string, string \| number \| boolean \| null>`**：breaking change，所有 emitSignal 调用方需确认不传对象值 |
| D5 | **`unbindConversation()` 语义**：保存当前桶 → `boundConversationId = null` → 轨道清空。解绑后轨道仍可操作（addContextItem/buildSystemPrompt 正常工作），`isContextForConversation` 对任何 convId 返回 false |
| D6 | **桶为内存级缓存，页面刷新后丢失**：v2 扩展点 #1（上下文持久化）将解决此限制 |
| D7 | **LRU 淘汰无用户提示**：桶被淘汰后切回对话时轨道为空，与"从未访问过该对话"行为一致，不额外提示 |

## 16. 已修复的边界问题（第六轮）

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 40 | P2 | linkWork 轨道满时 UI 与轨道不一致，用户不知作品未注入 | `addContextItem` 返回 null 时设 `trackFull = true`，UI 显示"轨道已满"提示 |
| 41 | P2 | `revalidateOrphans` 跳过后 works 加载完成无后续触发 | `watch(workStore.isLoading)`：从 true 变 false 时自动调 `revalidateOrphans()` |
| 42 | P2 | 文档 5.2 节 `unlinkWork` 签名未更新 | 同步为 `(workId?: string) => void` |
| 43 | P2 | 文档 4.2 节 `SidebarSignal.payload` 类型未更新 | 同步为 `Record<string, string \| number \| boolean \| null>` |

### 16.1 截断标记确认

`contentText`、`scriptText`、`contentPreview` 的截断逻辑统一为：
```typescript
const s = str.length > MAX_CONTENT_SLICE
  ? str.slice(0, MAX_CONTENT_SLICE) + '…'
  : str
```
仅在 `length > 800` 时追加 `…`，恰好 800 字符时不追加。

## 17. 扩展点（v2 方向）

1. **上下文持久化**：将 contextTrack 序列化到后端，跨会话恢复
2. **AI 自动 pin**：AI 回复中检测到新作品/分析时，自动 emitSignal + pin
3. **上下文摘要压缩**：当 pinnedItems 过多导致 system prompt 超长时，自动摘要压缩（当前已有硬截断，v2 改为智能摘要）
4. **拖拽排序**：支持拖拽调整 contextTrack 中条目的顺序（影响序列化优先级）
5. **批量操作**：全选 pin/unpin、按类型批量移除
6. **上下文模板**：预设常用上下文组合（如"爆款分析"= pin work + pin analysis）
7. **meta 联合类型**：将 `Record<string, any>` 改为按 type 的联合类型，编译期捕获结构错误