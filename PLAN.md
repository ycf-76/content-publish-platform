# 卡片编辑器体验升级计划书

## 背景

草稿箱 + 图片页渲染已完成。当前编辑器有 14 种页面模板、2 套基础主题 + 3 套 Esther 主题、7 种装饰层。
用户反馈核心诉求：**模板不够多、切换风格不方便、编辑手感差**。

本计划聚焦「架构内可落地」的改进，不做自由画布。

---

## Phase 1：更多页面模板 + 模板预设包 ✅ 已完成

### 1.1 新增 4 种高频页面类型 ✅

| 新类型 | 场景 | 数据字段 |
|--------|------|----------|
| `qa` 问答页 | Q&A、常见问题 | `qaPairs: Array<{ q: string; a: string }>` |
| `timeline` 时间轴 | 发展历程、步骤回顾 | `timelineItems: Array<{ date: string; event: string }>` |
| `stat_card` 数据卡片 | 关键数据展示 | `statItems: Array<{ value: string; label: string; unit?: string }>` |
| `profile` 人物介绍 | 作者介绍、人物卡片 | `avatarUrl?: string; name: string; role?: string; bio?: string` |

**已改动文件**：
1. ✅ `templates.ts` — PageType 新增 4 种、CardPage 新增字段、PAGE_TYPE_LABELS、createDefaultPage
2. ✅ `esther-templates.ts` — FULL_PAGE_TYPE_LABELS 新增 4 种
3. ✅ `CardRenderer.vue` — 新增 4 种模板分支 + CSS
4. ✅ `EstherCardRenderer.vue` — 同步新增 4 种模板分支 + CSS
5. ✅ `useCardEditor.ts` — changePageType 新增 4 种初始化逻辑、draft 恢复映射新字段
6. ✅ `PropertyPanel.vue` — 新增 4 种类型的编辑表单

### 1.2 新增 3 套模板预设 ✅

| 模板 ID | 名称 | 风格 | 配色 |
|---------|------|------|------|
| `forest_green` | 森林绿 | 自然/健康/环保 | 深绿底+白字+金色点缀 |
| `sunset_orange` | 落日橙 | 活力/运动/美食 | 深橙底+白字+暖黄点缀 |
| `lavender` | 薰衣草 | 美妆/时尚/浪漫 | 浅紫底+深紫字+粉色点缀 |

**已改动文件**：
1. ✅ `templates.ts` — TEMPLATES 数组新增 3 套

---

## Phase 2：拖拽排序 + 撤销重做 ✅ 已完成

### 2.1 页面拖拽排序 ✅

**方案**：原生 HTML5 Drag & Drop，拖拽手柄 + drop 指示线

**已改动文件**：
1. ✅ `useCardEditor.ts` — `movePageByIndex(fromIndex, toIndex)` + pushUndoSnapshot
2. ✅ `PageList.vue` — 拖拽手柄 `⠿`、`draggable`、`@dragstart/@dragover/@drop/@dragend`、拖拽态/放置指示线 CSS
3. ✅ `ImageWorkspace.vue` — `@reorder="editor.movePageByIndex"` 事件绑定

### 2.2 撤销/重做 ✅

**方案**：维护 pages 快照栈（最大 30 步），每次修改前 push 快照

**已改动文件**：
1. ✅ `useCardEditor.ts` — `undoStack`、`redoStack`、`pushUndoSnapshot()`、`undo()`、`redo()`、`canUndo`、`canRedo`
2. ✅ `ImageWorkspace.vue` — 底部工具栏撤销/重做按钮 + Ctrl+Z/Y 快捷键

---

## Phase 3：AI 填充 + 图片滤镜 ✅ 已完成

### 3.1 AI 文案一键填充 ✅

**方案**：选中页面后，用 copywrite_context 中的文案自动填充当前页面空字段。
根据页面类型智能拆分：list→按行拆、qa→按行配对、steps→按句拆、stat_card→提取数字、timeline→按行映射。

**已改动文件**：
1. ✅ `useCardEditor.ts` — `fillPageFromCopywrite(pageId)` 方法，按页面类型智能填充
2. ✅ `PropertyPanel.vue` — 「✨ AI 填充」按钮（仅当 copywrite_context 存在时显示）+ 渐变紫蓝按钮样式
3. ✅ `ImageWorkspace.vue` — `@fill-copywrite="editor.fillPageFromCopywrite"` 事件绑定

### 3.2 图片简单滤镜 ✅

**方案**：CSS filter 属性，5 种预设滤镜

| 滤镜 | CSS |
|------|-----|
| 亮度+ | `brightness(1.2)` |
| 对比度+ | `contrast(1.3)` |
| 模糊 | `blur(2px)` |
| 灰度 | `grayscale(1)` |
| 暖色 | `sepia(0.3) saturate(1.3)` |

**已改动文件**：
1. ✅ `CardPage` 接口新增 `imageFilter?: string`
2. ✅ `CardRenderer.vue` — img 标签加 `:style="{ filter: page.imageFilter }"`
3. ✅ `EstherCardRenderer.vue` — 同步
4. ✅ `PropertyPanel.vue` — image_page 类型新增滤镜选择下拉框

---

## 后续优化（非计划内，可择时做）
- 导出格式选择（PNG/WebP）
- 水印/Logo 叠加
- 自定义装饰参数暴露到 UI
- 页面缩略图预览（当前是文字列表，可加小卡片预览）