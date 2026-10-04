# 侧边栏重新设计 — 设计文档

> 版本: v2.1  
> 日期: 2026-09-26  
> 状态: 设计中  
> 前置: 基于 dual-track-context-system.md v1.0 的实现

---

## 1. v1 的问题

| # | 问题 | 根因 |
|---|------|------|
| 1 | **Tab 切换割裂体验** | 关联/详情/工具三个 Tab，用户必须切换才能看到不同内容，但三个功能应该同时可见 |
| 2 | **只支持"作品"一种内容** | ContextItemType 只有 work/analysis/file/creation/search/workspace，但 MD 文件、URL 链接、风格记忆、创作规范都进不来 |
| 3 | **"钉选"概念不直觉** | 用户选了作品还要手动 pin，竞品（Cursor）是 @提及即注入，Windsurf 是看了就在上下文里 |
| 4 | **没有发布平台入口** | WorkDetailPanel 里有发布按钮（小红书/抖音/快手/B站/知乎/视频号），但侧边栏没有，用户必须先切到详情 Tab 才能发布 |
| 5 | **没有风格记忆** | 竞品 Windsurf 有 Memories（AI 自动记住用户偏好），我们没有，每次都要重新说"我的风格是xxx" |
| 6 | **没有创作规范** | 竞品 Cursor 有 Rules（alwaysApply 的规则始终注入），我们没有，品牌调性/平台红线/禁用词每次都要手动说 |
| 7 | **没有 Context Ring** | 竞品 Cursor 在输入框旁有 token 用量环，用户一眼知道上下文用了多少，我们没有 |
| 8 | **没有 @提及** | 竞品 Cursor 用 @files @docs @web 在输入框加上下文，我们只能从侧边栏手动加 |

---

## 2. 竞品参考

### 2.1 Cursor

| 机制 | 作用 | 生命周期 |
|------|------|---------|
| **Rules** (alwaysApply) | 每次对话都注入的规则 | 跨对话持久 |
| **Rules** (Agent Decides) | Agent 自己判断要不要加载 | 跨对话持久 |
| **@提及** | @files @docs @web @code 在输入框加上下文 | 对话级临时 |
| **Agent 自收集** | Agent 自己搜 codebase | 对话级临时 |
| **Context Ring** | 输入框旁 token 用量环 + breakdown | 实时 |

侧边栏（Customize 面板）：Rules / Skills / Memories 三个分区同时可见，没有 Tab。

### 2.2 Windsurf

| 机制 | 作用 | 生命周期 |
|------|------|---------|
| **Memories** | AI 自动记住 + 用户手动 pin | Workspace 级持久 |
| **Rules** | 全局 + 工作区行为规则 | 跨对话持久 |
| **Context Pinning** | 钉目录/库，始终参考 | Workspace 级持久 |
| **Cascade 自收集** | Flow 内自动 | 对话级临时 |

侧边栏（Customizations 面板）：Memories / Rules 同时可见。

### 2.3 共同模式

| 层 | 作用 | 生命周期 | 谁加的 |
|----|------|---------|--------|
| Rules/Memories | 品牌调性、写作规范、平台规则 | 跨对话持久 | 用户预设 + AI 自动记忆 |
| @提及/Context Pin | 本次对话需要的具体内容 | 对话级临时 | 用户主动选择 |
| Agent 自收集 | Agent 判断相关的上下文 | 对话级临时 | AI 自动 |

---

## 3. 新设计：内容预览面板 + 上下文条

### 3.1 核心原则

1. **点啥开啥** — 点任何内容（作品/MD/URL/分析），侧边栏打开并渲染对应预览
2. **看了就在上下文里** — 打开即注入 AI，但有上限保护（见 §6.5）
3. **没有 Tab** — 所有区域同时可见，滚动浏览
4. **发布平台用真实 logo** — 不用 emoji，用 SVG logo
5. **对话隔离** — 切对话 = 切上下文，互不污染

### 3.2 布局

```
┌──────────────────────────────────┐
│  侧边栏标题栏                     │  ← 标题 + 关闭按钮
│  "正在查看: 夏日穿搭指南"          │  ← 当前预览内容的标题
├──────────────────────────────────┤
│                                  │
│  ┌─ 内容预览区 ──────────────┐  │  ← 占 ~65% 高度
│  │                            │  │     点啥渲染啥
│  │  渲染器根据 contentType     │  │     每种内容有对应渲染器
│  │  自动选择：                 │  │
│  │  - 图文笔记 → NotePreview  │  │
│  │  - 爆款采集 → WorkDetail   │  │
│  │  - 分析报告 → AnalysisView │  │
│  │  - MD 文件  → MarkdownView │  │
│  │  - URL 链接 → WebPreview   │  │
│  │  - 脚本     → ScriptView   │  │
│  │                            │  │
│  │  ── 发布到 ──              │  │  ← 草稿时显示发布平台
│  │  [小红书] [抖音] [快手]     │  │     用 SVG logo，不用 emoji
│  │  [B站]   [知乎] [视频号]   │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌─ 上下文条 ────────────────┐  │  ← 占 ~35% 高度，固定底部
│  │  AI 正在读取：              │  │
│  │  📄 夏日穿搭  👁 ✕         │  │     对话级临时上下文
│  │  📊 竞品TOP3  👁 ✕         │  │     👁 = 切换读取
│  │                            │  │     ✕ = 移除
│  │  ── 风格记忆 ──            │  │  ← 跨对话持久
│  │  🎨 偏好短句+emoji   ✕    │  │     AI 自动记住
│  │  📏 小红书规范       ✕    │  │     用户预设
│  │                            │  │
│  │  ── 快捷操作 ──            │  │
│  │  ✨ 生成 📊 分析 ✍️ 改写 🚀 发布│
│  │                            │  │
│  │  ◐ 2.1K / 4K tokens       │  │  ← Context Ring
│  └────────────────────────────┘  │
└──────────────────────────────────┘
```

### 3.3 和 v1 的对应关系

| v1 | v2 | 变化 |
|----|----|------|
| 关联 Tab | 上下文条"AI 正在读取" | 不再是 Tab，始终可见在底部 |
| 详情 Tab | 内容预览区 | 不再是 Tab，点击条目自动展示 |
| 工具 Tab | 上下文条"快捷操作" | 不再是 Tab，始终可见在底部 |
| — | 风格记忆 | **新增**，跨对话持久 |
| — | 发布平台 logo | **新增**，从 WorkDetailPanel 迁移 |
| — | Context Ring | **新增**，token 用量可视化 |
| — | @提及 | **新增**，输入框加内容（v2.1） |

---

## 4. 内容渲染器

### 4.1 渲染器映射

| contentType | 渲染器组件 | 展示内容 | 注入 AI 的 |
|-------------|-----------|---------|-----------|
| `image_text` | `NotePreview` | 封面 + 正文 + 标签 + 平台 + 数据指标 | 标题+正文+标签 |
| `short_video` / `long_video` / `ai_edit` / `voiceover` / `live_clip` | `WorkDetail`（复用现有） | 封面 + 脚本 + 数据指标 + 诊断 | 标题+脚本+指标 |
| `image_gallery` | `NotePreview` | 图集 + 正文 + 标签 | 标题+正文+标签 |
| `long_article` | `MarkdownView` | Markdown 渲染 | 原文文本 |
| `analysis` | `AnalysisView` | 图表 + 归因 + 建议 | 归因摘要+建议 |
| `url` | `WebPreview` | 抓取的网页标题+摘要+正文 | 网页摘要 |
| `file` | `MarkdownView` | 文件内容渲染 | 文件文本 |
| `rule` | `RulesView` | 规则列表 + 开关 | 规则文本 |
| `memory` | `MemoriesView` | 记忆条目列表 | 记忆文本 |

### 4.2 渲染器选择逻辑

```typescript
function getRenderer(item: ContextItem): Component {
  if (item.type === 'analysis') return AnalysisView
  if (item.type === 'rule') return RulesView
  if (item.type === 'memory') return MemoriesView
  if (item.type === 'url') return WebPreview

  // work 类型按 contentType 分
  const work = workStore.works.find(w => w.id === item.meta.refId)
  if (!work) return MarkdownView  // fallback（work 找不到时用 Markdown 渲染 track 中的 summary）

  if (work.contentType === 'long_article') return MarkdownView
  if (['short_video','long_video','ai_edit','voiceover','live_clip'].includes(work.contentType)) return WorkDetail
  return NotePreview  // image_text, image_gallery 默认
```

### 4.3 渲染器 fallback 与错误处理

| 场景 | fallback |
|------|----------|
| work 查找失败（refId 无效） | `MarkdownView` 渲染 track 中的 label + summary |
| URL 抓取失败（网络错误/超时） | `ErrorFallback`：显示 URL + 错误信息 + 重试按钮 |
| 文件读取失败 | `ErrorFallback`：显示文件名 + 错误信息 |
| 渲染器组件加载失败（动态 import 异常） | `ErrorFallback`：通用错误 + 刷新按钮 |

```vue
<!-- ErrorFallback.vue -->
<template>
  <div class="error-fallback">
    <AlertCircle :size="20" />
    <span>{{ message }}</span>
    <button v-if="retryable" @click="$emit('retry')">重试</button>
  </div>
</template>
```

---

## 5. 发布平台

### 5.1 平台定义

| 平台 | key | logo 来源 | 发布动作 |
|------|-----|----------|---------|
| 小红书 | `xiaohongshu` | `/icons/xiaohongshu-app.svg` | `publish_xiaohongshu` |
| 抖音 | `douyin` | 内联 SVG（音符图标） | `publish_douyin` |
| 快手 | `kuaishou` | 内联 SVG（摄像机图标） | `publish_kuaishou` |
| B站 | `bilibili` | 内联 SVG（电视机图标） | `publish_bilibili` |
| 知乎 | `zhihu` | 内联 SVG（灯泡图标） | `publish_zhihu` |
| 视频号 | `wechat_video` | `/icons/wechat-app.svg` | `publish_wechat` |

### 5.2 显示条件

- **草稿**（`isDraft = true`）：显示"发布到"区域，所有平台可选
- **已发布**：显示已发布平台标记（打勾 + 灰化），其余平台仍可选（一键分发）
- **采集作品**：不显示"发布到"（采集的作品不能直接发布，需要先创建草稿）

### 5.3 Logo 组件

```vue
<!-- PlatformLogo.vue -->
<template>
  <img v-if="logoSrc" :src="logoSrc" :alt="name" class="platform-logo" />
  <span v-else class="platform-logo-fallback">{{ fallbackEmoji }}</span>
</template>
```

优先用 SVG 文件（`/icons/xxx-app.svg`），fallback 用内联 SVG 图标（不依赖 emoji，跨平台一致）。

---

## 6. 上下文条

### 6.1 分区

| 分区 | 内容 | 生命周期 | 来源 |
|------|------|---------|------|
| **AI 正在读取** | 对话级临时上下文条目 | 切对话切换 | 用户点击 / @提及 / AI 信号 |
| **风格记忆** | 跨对话持久记忆 | 始终存在 | AI 自动记住 + 用户预设 |
| **快捷操作** | AI 生成/分析/改写/发布 | 始终存在 | 固定 |

### 6.2 条目交互

| 操作 | 效果 |
|------|------|
| 点击条目 | 内容预览区切换到该条目的渲染 |
| 👁 按钮 | 切换读取（pinned = !pinned），不影响预览 |
| ✕ 按钮 | 移除条目（从 contextTrack 删除） |

### 6.3 风格记忆

```typescript
interface StyleMemory {
  id: string
  content: string          // "偏好短句+emoji开头"
  source: 'ai-auto' | 'user-set'  // AI 自动记住 or 用户预设
  createdAt: number
}
```

- AI 在对话中检测到用户偏好时，自动创建 `source: 'ai-auto'` 的记忆
- 用户在设置中预设 `source: 'user-set'` 的记忆（品牌调性、平台规范）
- 风格记忆始终注入 system prompt，不受 👁 切换影响
- 用户可 ✕ 删除 AI 自动记忆（`source: 'ai-auto'`）
- 用户预设的记忆（`source: 'user-set'`）显示 🔒 图标，不可删除，只能点击 ✏️ 编辑

### 6.5 上下文条目上限与淘汰

| 参数 | 值 | 说明 |
|------|---|------|
| `MAX_TRACK_ITEMS` | 10 | 对话级上下文条目上限 |
| `MAX_STYLE_MEMORIES` | 20 | 风格记忆上限 |
| `CONTEXT_RING_WARN` | 0.9 | Context Ring 占比超过 90% 时警告 |

淘汰策略：
- 新条目加入时，若 `contextTrack.length >= MAX_TRACK_ITEMS`，自动 unpin 最旧的未钉选条目
- 若全部 pinned，不加入新条目，UI 提示"上下文已满，请先移除部分内容"
- Context Ring 占比 ≥ 90% 时，上下文条底部显示橙色警告"上下文接近上限，建议移除部分内容"

### 6.6 Context Ring

```
◐ 2.1K / 4K tokens
```

- 环形进度条，显示当前上下文 token 占比
- 点击展开 breakdown（对标 Cursor）：
  - 系统提示 / 上下文内容 / 风格记忆 / 对话历史
- 数据来源：`buildSystemPrompt().length` 估算（中文约 1 字符 ≈ 1.5 token，此为粗略估算；英文约 1 字符 ≈ 0.25 token；精确计算需 tiktoken，v2.1 可接入）

---

## 7. 数据模型变更

### 7.1 ContextItemType 扩展

```typescript
// v1
type ContextItemType = 'work' | 'analysis' | 'file' | 'creation' | 'search' | 'workspace'

// v2
type ContextItemType = 'work' | 'analysis' | 'file' | 'url' | 'rule' | 'memory'
```

变更说明：
- `creation` / `search` / `workspace` 移除（语义不清，实际未使用）
- `url` 新增：URL 链接内容
- `rule` 新增：创作规范
- `memory` 新增：风格记忆

### 7.2 新增状态

```typescript
// chatContext store 新增
const styleMemories = ref<StyleMemory[]>([])
const previewItem = ref<ContextItem | null>(null)   // 当前预览的条目
```

### 7.3 sidebarTab 移除

v1 的 `sidebarTab: 'context' | 'detail' | 'tools'` 不再需要。侧边栏没有 Tab，所有区域同时可见。

### 7.4 buildSystemPrompt 扩展

```typescript
function buildSystemPrompt(): string | null {
  // 1. 风格记忆（始终注入）
  const memoryParts = styleMemories.value.map(m => m.content)

  // 2. 对话级上下文（pinned 条目）
  const contextParts = pinnedItems.value.map(...)

  // 3. 合并
  return [...memoryParts, ...contextParts, ...强制要求].join('\n')
}
```

---

## 8. 交互流

### 8.1 从导航栏选择作品

```
用户点击导航栏"夏日穿搭"
  → workStore.setActiveWork(id)
  → ctxStore.linkWork(id)         // addContextItem + pinned=true
  → ctxStore.previewItem = item   // 设置预览条目
  → ctxStore.sidebarVisible = true // 打开侧边栏
  → 侧边栏渲染 NotePreview
  → 上下文条出现 "📄 夏日穿搭"
```

### 8.2 从对话中点击 URL

```
用户在对话消息中点击 URL
  → ctxStore.addContextItem({ type: 'url', meta: { url, refId: url } })
  → ctxStore.previewItem = item
  → ctxStore.sidebarVisible = true
  → 侧边栏渲染 WebPreview（异步抓取）
```

### 8.3 切换对话

```
用户从对话 A 切到对话 B
  → ctxStore.bindConversation(B.id)
  → 保存 A 的轨道到桶，恢复 B 的轨道
  → previewItem = B 轨道的第一个条目（或 null）
  → 侧边栏保持打开，内容切换
```

### 8.4 对话桶存储

| 维度 | 定义 |
|------|------|
| **存储位置** | 内存（`conversationBuckets: Map<string, ContextItem[]>`） |
| **持久化** | 风格记忆（`styleMemories`）写入 localStorage，对话级桶不持久化（刷新后丢失，与对话历史行为一致） |
| **桶上限** | `MAX_BUCKETS = 20`，超限时 LRU 淘汰最久未访问的桶 |
| **桶内容** | 只存 `ContextItem` 的序列化快照（不含组件实例），恢复时从快照重建 |

### 8.5 点击发布平台

```
用户在预览区点击"小红书"发布按钮
  → emit('chat-action', 'publish_xiaohongshu')
  → ChatView 接收，向对话发送发布指令
```

### 8.6 AI 自动记忆

```
AI 回复中检测到用户偏好（如"我喜欢短句"）
  → ctxStore.addStyleMemory({ content: '偏好短句风格', source: 'ai-auto' })
  → 上下文条"风格记忆"区出现新条目
  → 后续对话自动注入此记忆
```

### 8.7 AI 自动记忆规范

| 维度 | 定义 |
|------|------|
| **谁来判断** | LLM 自输出：在 system prompt 中指示"当检测到用户表达内容偏好时，在回复末尾输出 `<memory>偏好描述</memory>` 标签"，前端解析标签后调用 `addStyleMemory` |
| **去重策略** | `addStyleMemory` 内部对 content 做模糊匹配（余弦相似度 > 0.8 视为重复），重复时更新已有记忆的 `createdAt` 而非新建 |
| **数量上限** | `MAX_STYLE_MEMORIES = 20`，超限时删除最旧的 `ai-auto` 记忆（不删 `user-set`） |
| **触发频率** | 每条 AI 回复最多触发 1 次记忆创建（避免批量刷入） |

---

## 9. WebPreview 后端 API 契约

### 9.1 接口定义

```
POST /api/web/fetch
Body: { url: string, maxLength?: number }  // maxLength 默认 4000 字符
Response: {
  title: string
  description: string
  content: string          // 纯文本正文，截断到 maxLength
  author?: string
  publishedAt?: string
  images?: string[]        // 前 3 张图片 URL
}
```

### 9.2 超时与错误

| 场景 | 处理 |
|------|------|
| 请求超时 | 前端 8s 超时，显示 ErrorFallback + 重试按钮 |
| 后端返回 4xx | URL 无效或被屏蔽，显示 ErrorFallback（不可重试） |
| 后端返回 5xx | 服务端错误，显示 ErrorFallback + 重试按钮 |
| 反爬拦截 | 后端返回 `{ error: 'blocked' }`，前端显示"该网站不允许抓取" |

### 9.3 安全

- 后端校验 URL 合法性（只允许 http/https）
- 后端限制抓取频率（同 IP 每分钟最多 10 次）
- 前端不直接 fetch 用户 URL，全部走后端代理

---

## 10. 组件结构

### 10.1 ContextSidebar.vue（重写）

```
ContextSidebar
├── SidebarHeader          // 标题栏：当前预览标题 + 关闭按钮
├── ContentPreview         // 内容预览区（~65% 高度）
│   ├── NotePreview        // 图文笔记预览
│   ├── WorkDetail         // 视频类作品详情（复用现有）
│   ├── AnalysisView       // 分析报告
│   ├── MarkdownView       // MD 文件 / 长文
│   ├── WebPreview         // URL 链接
│   ├── ScriptView         // 脚本
│   ├── RulesView          // 创作规范
│   ├── MemoriesView       // 风格记忆详情
│   └── PublishPlatforms   // 发布平台（草稿时显示）
└── ContextBar             // 上下文条（~35% 高度）
    ├── ContextTrack       // AI 正在读取（对话级临时）
    ├── StyleMemories      // 风格记忆（跨对话持久）
    ├── QuickActions       // 快捷操作
    └── ContextRing        // Token 用量环
```

### 10.2 新增组件

| 组件 | 作用 | 复杂度 |
|------|------|--------|
| `NotePreview.vue` | 图文笔记预览（封面+正文+标签+指标） | 中 |
| `MarkdownView.vue` | Markdown 渲染 | 低（用现有 renderMarkdown） |
| `WebPreview.vue` | URL 内容抓取+渲染 | 高（需后端支持） |
| `AnalysisView.vue` | 分析报告图表 | 中 |
| `ScriptView.vue` | 脚本格式化展示 | 低 |
| `RulesView.vue` | 创作规范列表+开关 | 低 |
| `MemoriesView.vue` | 风格记忆列表 | 低 |
| `PublishPlatforms.vue` | 发布平台 logo 网格 | 低（从 WorkDetailPanel 迁移） |
| `PlatformLogo.vue` | 单个平台 logo | 低 |
| `ContextRing.vue` | Token 用量环 | 低 |
| `ErrorFallback.vue` | 渲染错误降级（错误信息+重试） | 低 |

### 10.3 复用组件

| 组件 | 来源 | 用途 |
|------|------|------|
| `WorkDetailPanel.vue` | 现有 | 视频类作品详情（preview/analysis tab） |

---

## 11. 实现计划

### Phase 1：布局重构（本次）

- [ ] ContextSidebar 改为双区布局（预览区 + 上下文条）
- [ ] 移除 Tab，所有区域同时可见
- [ ] previewItem 状态驱动预览区内容
- [ ] 发布平台从 WorkDetailPanel 迁移到预览区底部
- [ ] PlatformLogo 组件（SVG logo，不用 emoji）

### Phase 2：内容渲染器

- [ ] NotePreview（图文笔记预览）
- [ ] MarkdownView（MD 文件渲染）
- [ ] ScriptView（脚本展示）
- [ ] 渲染器选择逻辑（getRenderer）

### Phase 3：风格记忆 + Context Ring

- [ ] StyleMemory 数据模型 + store
- [ ] AI 自动记忆机制
- [ ] ContextRing 组件
- [ ] buildSystemPrompt 扩展（注入记忆）

### Phase 4：@提及 + WebPreview

- [ ] 输入框 @提及（@笔记 @爆款 @链接 @热点 @风格 @规范）
- [ ] WebPreview（URL 抓取+渲染）
- [ ] AnalysisView（分析报告）

---

## 12. 和 v1 的兼容性

| v1 API | v2 变化 | 迁移 |
|--------|---------|------|
| `sidebarTab` | 移除 | 所有 `setSidebarTab` 调用移除 |
| `linkWork()` | 保留，新增 `previewItem` 设置 | 无需迁移 |
| `addContextItem()` | 保留，type 扩展 | 无需迁移 |
| `togglePin()` | 保留，语义改为"切换读取" | 无需迁移 |
| `buildSystemPrompt()` | 扩展，注入风格记忆 | 无需迁移 |
| `WorkDetailPanel` | 保留，在预览区中使用 | 调用方式不变 |

---

## 13. 平台 Logo 资源

| 平台 | 现有资源 | 需要补充 |
|------|---------|---------|
| 小红书 | `/icons/xiaohongshu-app.svg` ✅ | — |
| 微信 | `/icons/wechat-app.svg` ✅ | — |
| 抖音 | ❌ | 需创建 `douyin-app.svg` |
| 快手 | ❌ | 需创建 `kuaishou-app.svg` |
| B站 | ❌ | 需创建 `bilibili-app.svg` |
| 知乎 | ❌ | 需创建 `zhihu-app.svg` |

缺失的 logo 临时用内联 SVG 图标（lucide 图标 + 品牌色背景），后续替换为正式 logo。

### 13.1 Logo 尺寸规范

- SVG 文件：`viewBox="0 0 48 48"`，`rx="12"` 圆角
- 渲染尺寸：`24×24` CSS 像素（在发布平台网格中）
- 品牌色背景 + 白色图标/文字

---

## 14. 发布平台交互细节

### 14.1 一键分发流程

```
用户点击"小红书"发布按钮
  → 弹出确认弹窗："确认发布到小红书？"
  → 用户确认
  → 按钮变为 loading 状态（旋转图标 + "发布中..."）
  → emit('chat-action', 'publish_xiaohongshu')
  → ChatView 向对话发送发布指令
  → AI 执行发布，回复发布结果
  → 按钮恢复，显示 ✓ 已发布
```

### 14.2 多平台同时发布

- 用户可连续点击多个平台按钮，每个独立进入发布流程
- 不做"全选+一键全发"（避免误操作风险）
- 每个平台发布状态独立追踪

### 14.3 发布失败

- 发布失败时按钮变红 + 显示错误信息
- 提供"重试"按钮
- 不自动回滚（已发布到其他平台的内容不受影响）