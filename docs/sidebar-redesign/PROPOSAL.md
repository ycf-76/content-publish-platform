# 侧边栏 UI 重设计方案

> 状态：提案中 | 日期：2026-08-22 | 涉及组件：`SidebarNav.vue`、`_nav.css`
>
> **设计规范约束**：本文档所有色值、字号、圆角、字体必须引用 `_theme-vars.css` 中的 CSS 变量（`--ma-*`），禁止使用 Tailwind 硬编码色。品牌主色为 `#FF2442`（`--ma-sidebar-primary`），不是橙色。

---

## 1. 现状诊断

### 1.1 可用性问题

| 问题 | 具体表现 |
|------|----------|
| 新建对话不可发现 | `+` 按钮挤在 nav-item 行尾，和 chevron 抢空间，用户很难注意到 |
| 删除对话靠右键 | 唯一入口是右键菜单，无 hover 出现删除图标，移动端/触屏完全不可用 |
| 对话历史无搜索 | 对话多了只能"查看更多/收起"，没有搜索/筛选，找历史对话成本高 |
| 无键盘快捷键 | 没有 Cmd+K 呼出命令面板、没有数字键快速切换页面 |

### 1.2 空间利用率低

| 问题 | 数据 |
|------|------|
| 顶部留白过大 | `padding-top: 50px`，logo 区域占据 ~110px 垂直空间，仅放了一个 logo |
| nav 宽度受限 | sidebar 216px，但 nav `max-width: 200px`，两侧各浪费 8px |
| 对话标题截断过早 | `max-width: 140px`，216px 的侧栏完全可以给 160-170px |
| 底部区域浪费 | 仅一个"收起侧栏"按钮，大量纵向空间空置 |
| 折叠态 56px 过窄 | 折叠后只能放图标，不如 48px icon-only rail 更紧凑 |

### 1.3 UI 排版问题

| 问题 | 具体表现 |
|------|----------|
| 视觉层级扁平 | AI 对话、工作流、选题池、Esther工厂、设置——5 个项目平铺，没有分组/分区 |
| 活跃态过重 | 当前用 `#EA580C`（橙色，偏离品牌色 `#FF2442`）渐变背景 + box-shadow + inset 高光，视觉噪音大 |
| hover 效果过多 | translateX(2px) + scale(1.05) + 渐变 reveal + box-shadow，4 层叠加 |
| backdrop-filter 滥用 | 每个 nav-item 都有 `backdrop-filter: blur(15px)`，侧栏本就是实色背景，毫无意义还拖性能 |
| 字体声明不一致 | nav-item 用 `-apple-system...`，sidebar-wrapper 用 `"PingFang SC"...`，两套字体栈 |

### 1.4 交互感过杂

| 问题 | 具体表现 |
|------|----------|
| 动画过度工程化 | JS 手动控制 stagger 动画（enter/leave 各 40+ 行），CSS transition 已够用 |
| hover 反馈层次太多 | 位移 + 缩放 + 颜色 + 阴影 + 伪元素渐变，用户感知不到这么多层 |
| chevron 和 + 按钮冲突 | 同一行右侧两个可点击元素，手指/光标容易误触 |

---

## 2. 竞品参考分析

### 2.1 Claude Code 侧边栏

| 维度 | 设计 |
|------|------|
| 宽度 | 240px 展开 / 48px 折叠 |
| 结构 | 顶部：项目名 + 搜索框 → 中部：对话列表（可滚动）→ 底部：设置+折叠 |
| 分组 | 用分割线分"近期"/"更早"，时间分组 |
| 活跃态 | 左侧 2px 色条 + 浅灰背景，极克制 |
| hover | 仅背景色变化，无位移/缩放 |
| 新建对话 | 顶部独立按钮，大且显眼 |
| 搜索 | 内嵌搜索框，实时过滤 |
| 删除 | hover 时右侧浮现删除图标 |

### 2.2 Codex (OpenAI) 侧边栏

| 维度 | 设计 |
|------|------|
| 宽度 | 260px 展开 / 52px 折叠 |
| 结构 | 顶部：Logo → 中部：会话列表 → 底部：账号+设置 |
| 分组 | Pin 置顶 + 按日期分组 |
| 活跃态 | 左侧 3px 圆角色条 + 微灰背景 |
| hover | 仅背景色 + 文字色变化 |
| 新建对话 | 顶部独立按钮 + 快捷键提示 |
| 搜索 | Cmd+K 命令面板 |
| 删除 | 右键菜单 + hover 浮现删除 |

### 2.3 核心启示

两者都遵循 **"安静的主体 + 显眼的入口 + 克制的反馈"** 原则。

---

## 3. 设计方案

### 3.1 架构总览

```
┌─────────────────────────────────┐
│  Logo (紧凑)       [+ 新对话]    │  ← 顶栏：logo + 主操作
├─────────────────────────────────┤
│  🔍 搜索对话...                  │  ← 搜索框（可折叠）
├─────────────────────────────────┤
│                                 │
│  ── 核心功能 ──                  │  ← 分组标签（小字灰色）
│  💬 AI 对话          ›          │  ← 可展开，chevron 在右
│    ├ 对话标题1        🗑         │  ← hover 浮现删除
│    ├ 对话标题2        🗑         │
│    └ 对话标题3        🗑         │
│  ✨ 工作流                       │
│  📖 选题池                       │
│                                 │
│  ── 工具 ──                      │  ← 第二分组
│  ⚙ Esther工厂                   │
│                                 │
├─────────────────────────────────┤
│  ⚙ 设置          ◀ 收起         │  ← 底栏：设置 + 折叠
└─────────────────────────────────┘
```

### 3.2 尺寸体系

| 属性 | 现值 | 新值 | 理由 |
|------|------|------|------|
| 展开宽度 | 216px | **240px** | 对标 Claude Code，给对话标题更多空间 |
| 折叠宽度 | 56px | **48px** | 标准 icon rail 宽度，更紧凑 |
| nav-item 高度 | auto (~40px) | **36px** | 紧凑但可点击，对标 VS Code |
| sub-item 高度 | auto (~34px) | **32px** | 子项比父项矮 4px，层级清晰 |
| 顶部 padding | 50px | **16px** | logo 不需要那么大留白 |
| 分组间距 | 无 | **8px 上 + 4px 下** | 分组标签上方 8px、下方 4px |

### 3.3 视觉层级体系

> 所有色值严格引用 `_theme-vars.css` 中的 CSS 变量，不使用 Tailwind 硬编码色。

```
层级 0（背景）    侧栏背景：var(--ma-sidebar) = #F5F5F5
层级 1（默认项）  文字 var(--ma-text-secondary) = #4B4B4B，图标 var(--ma-text-tertiary) = #9A9A9A，无背景
层级 2（hover）   背景 var(--ma-bg-subtle) = #EEEEEF，文字 var(--ma-text-primary) = #1A1A1A  ← 仅背景变化
层级 3（active）  左侧 2px 色条 var(--ma-sidebar-primary) = #FF2442 + 背景 var(--ma-sidebar-accent) = rgba(255,36,66,0.08) + 文字 var(--ma-sidebar-primary)
层级 4（分组标签）var(--ma-font-xs) = 12px 大写字母间距，var(--ma-text-tertiary)，不可点击
```

**关键改变**：

- ❌ 去掉所有 `translateX`、`scale`、`backdrop-filter`、伪元素渐变
- ❌ 去掉 active 态的 `box-shadow` + `inset` 高光
- ✅ active 态改为**左侧色条**（2px 圆角矩形，`border-radius: 1px`），颜色用 `var(--ma-sidebar-primary)` 即 `#FF2442`，这是 Claude Code / Codex / VS Code 共识
- ✅ hover 仅改背景色，零位移零缩放

### 3.4 顶栏重构

**现状**：logo 独占一行，`padding-top: 50px`，新建对话藏在 nav-item 行尾

**新方案**：

```
┌──────────────────────────────────┐
│  🦀 Pulse Studio      [+ 新对话]  │  ← 一行搞定
└──────────────────────────────────┘
```

- Logo + 品牌名 左对齐
- `+ 新对话` 按钮右对齐，**独立按钮**，`24×24` 圆形，hover 变 `var(--ma-sidebar-primary)` 即品牌红
- 整行高度 48px，`padding: 0 12px`
- 折叠态：logo 居中，`+` 变为底部浮动按钮

### 3.5 搜索框

**新增组件**，位于顶栏下方：

```
┌──────────────────────────────────┐
│  🔍 搜索对话...                   │
└──────────────────────────────────┘
```

- 高度 32px，`border-radius: var(--ma-radius-md)` 即 8px，背景 `var(--ma-bg-subtle)`
- focus 时：边框 `var(--ma-sidebar-primary)` 即 `#FF2442`，背景变白
- 实时过滤对话历史列表
- 无对话时自动隐藏（节省空间）
- 折叠态隐藏

### 3.6 导航分组

**现状**：5 个项目平铺，无分组

**新方案**：分两组，用小字标签分隔

```
── 核心 ──         ← var(--ma-font-xs)=12px, uppercase, letter-spacing: 1px, var(--ma-text-tertiary)
  💬 AI 对话       ← 可展开
  ✨ 工作流
  📖 选题池

── 工具 ──         ← 同上
  ⚙ Esther工厂
```

- 分组标签：`font-size: var(--ma-font-xs)` 即 12px，`text-transform: uppercase`，`letter-spacing: 1px`，`color: var(--ma-text-tertiary)`，`padding: 8px 12px 4px`
- "设置"移到底栏（见 3.7 节）

### 3.7 底栏重构

**现状**：仅一个"收起侧栏"按钮，大量空间浪费

**新方案**：

```
┌──────────────────────────────────┐
│  ⚙ 设置                ◀ 收起    │
└──────────────────────────────────┘
```

- 一行两个元素：设置（左）+ 折叠（右）
- 高度 40px，`border-top: 1px solid var(--ma-border-default)`
- 折叠态：仅显示设置齿轮图标

### 3.8 对话历史子项优化

| 改动 | 现状 | 新方案 |
|------|------|--------|
| 标题宽度 | `max-width: 140px` | `flex: 1; min-width: 0` 自适应撑满 |
| 删除入口 | 仅右键菜单 | **hover 浮现 🗑 图标** + 右键菜单保留 |
| "查看更多" | 文字链接 | 改为 **滚动加载**，列表限高 200px 后自动滚动 |
| 展开动画 | JS stagger 40+ 行 | **CSS `grid-template-rows: 0fr → 1fr`**，3 行搞定 |

删除图标浮现方案：

```css
.mint-chat-history-item .delete-icon {
  opacity: 0;
  transition: opacity 0.15s ease;
}
.mint-chat-history-item:hover .delete-icon {
  opacity: 1;
}
```

### 3.9 折叠态（Icon Rail）设计

```
┌──────┐
│  🦀  │  ← logo 居中
├──────┤
│  💬  │  ← AI 对话
│  ✨  │  ← 工作流
│  📖  │  ← 选题池
│  ⚙  │  ← Esther
├──────┤
│  ⚙  │  ← 设置
│  ◀   │  ← 展开
└──────┘
```

- 宽度 48px，图标 18px，居中
- hover 时右侧浮出 tooltip（保留现有伪元素方案，但去掉 `skew(-5deg)` 和多层 box-shadow，改为简洁圆角矩形）
- active 态：图标变 `var(--ma-sidebar-primary)` 即品牌红 + 背景微灰

### 3.10 动画规范

| 场景 | 现状 | 新方案 |
|------|------|--------|
| hover 反馈 | translateX + scale + 渐变 + 阴影 | **仅 background-color 变化**，`transition: 0.15s ease` |
| 子组展开/收起 | JS 手动 stagger 40+ 行 | **CSS `grid-template-rows` 过渡**，或 `<Transition>` + `max-height` |
| 侧栏折叠/展开 | width transition | 保留，曲线改为 `ease-out`（展开快、收起慢，更自然） |
| tooltip 出现 | opacity + transform + skew | **仅 opacity + translateY(4px)**，去掉 skew |

### 3.11 字体统一

全侧栏统一使用设计规范变量：

```css
font-family: var(--ma-font-sans);
/* 即 'Inter', -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif */
```

去掉 nav-item 和 sidebar-wrapper 各声明一套的问题。`Inter` 作为首选西文字体不可省略。

---

## 4. CSS 变更清单

### 4.1 删除的样式

```css
/* ❌ 删除：hover 位移 */
.mint-nav-item:hover { transform: translateX(2px); }
.mint-nav-sub:hover { transform: translateX(2px); }

/* ❌ 删除：hover 缩放 */
.mint-nav-item:hover svg { transform: scale(1.05); }
.mint-nav-sub:hover svg { transform: scale(1.05); }

/* ❌ 删除：无意义的 backdrop-filter */
.mint-nav-item { backdrop-filter: blur(15px); }
.mint-nav-sub { backdrop-filter: blur(15px); }

/* ❌ 删除：伪元素渐变叠层 */
.mint-nav-item::before { background: linear-gradient(...); }
.mint-nav-sub::before { background: linear-gradient(...); }

/* ❌ 删除：active 态过重装饰 */
.mint-nav-active { box-shadow: ...; }

/* ❌ 删除：tooltip skew */
.mint-shell.mint-collapsed .mint-nav-item::after { transform: ... skew(-5deg); }

/* ❌ 删除：新建对话旋转动画 */
.mint-nav-new-chat:hover { transform: scale(1.1) rotate(90deg); }
```

### 4.2 新增的样式

```css
/* ✅ 新增：分组标签 */
.mint-nav-group-label { ... }

/* ✅ 新增：左侧色条 active 态 */
.mint-nav-active::after {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  border-radius: 1px;
  background: var(--ma-sidebar-primary);  /* #FF2442 */
}

/* ✅ 新增：顶栏一行布局 */
.mint-sidebar-header { ... }

/* ✅ 新增：搜索框 */
.mint-sidebar-search { ... }

/* ✅ 新增：hover 浮现删除图标 */
.mint-chat-delete { opacity: 0; transition: opacity 0.15s ease; }
.mint-chat-history-item:hover .mint-chat-delete { opacity: 1; }

/* ✅ 新增：简化 hover */
.mint-nav-item:hover { background: var(--ma-bg-subtle); }
```

### 4.3 修改的样式

```css
/* 修改：侧栏宽度 */
.mint-sidebar-wrapper { width: 240px; }  /* was 216px */

/* 修改：折叠宽度 */
.mint-shell.mint-collapsed .mint-sidebar { width: 48px; }  /* was 56px */

/* 修改：顶部留白 */
.mint-sidebar-main { padding-top: 16px; }  /* was 50px */

/* 修改：nav-item 高度 */
.mint-nav-item { padding: 8px 12px; }  /* was 10px 12px → 36px total */

/* 修改：对话标题宽度 */
.mint-chat-history-title { max-width: none; flex: 1; min-width: 0; }  /* was 140px */

/* 修改：active 态 */
.mint-nav-active {
  background: var(--ma-sidebar-accent);       /* rgba(255,36,66,0.08)，was 渐变 */
  color: var(--ma-sidebar-primary);           /* #FF2442，was #EA580C */
  /* box-shadow: none; */
}
```

---

## 5. Vue 组件变更清单

### 5.1 SidebarNav.vue 结构变更

```diff
  <aside class="mint-sidebar">
    <div class="mint-sidebar-main">
-     <div class="mint-logo-top" ...>
-       <img ... class="mint-logo-text" />
-     </div>
-
-     <nav class="mint-nav" style="margin-top: 20px;">
+     <!-- 顶栏：Logo + 新建对话 -->
+     <div class="mint-sidebar-header">
+       <div class="mint-logo-top" ...>
+         <img ... class="mint-logo-text" />
+       </div>
+       <button class="mint-new-chat-btn" @click="$emit('new-chat')">
+         <Plus :size="16" />
+       </button>
+     </div>
+
+     <!-- 搜索框 -->
+     <div class="mint-sidebar-search" v-if="chatDisplayItems.length > 3">
+       <Search :size="14" />
+       <input v-model="searchQuery" placeholder="搜索对话..." />
+     </div>
+
+     <nav class="mint-nav">
+       <!-- 分组：核心 -->
+       <div class="mint-nav-group-label">核心</div>
+
        <a class="mint-nav-item" data-page="chat" ...>
          <Bot :size="16" />
          <span>AI 对话</span>
-         <span class="mint-nav-new-chat" @click.stop="$emit('new-chat')">
-           <Plus :size="14" />
-         </span>
          <span class="mint-nav-chevron" ...>
            <ChevronDown :size="14" />
          </span>
        </a>
+
        <!-- 对话子项：新增 hover 删除图标 -->
        <div class="mint-nav-subgroup" v-show="chatExpanded">
          <a v-for="item in chatDisplayItems" class="mint-nav-sub mint-chat-history-item">
            <MessageSquare :size="12" />
            <span class="mint-chat-history-title">{{ item.title }}</span>
+           <span class="mint-chat-delete" @click.stop="onDeleteChat(item.id)">
+             <Trash2 :size="12" />
+           </span>
          </a>
        </div>

        <a class="mint-nav-item" ...>工作流</a>
        <a class="mint-nav-item" ...>选题池</a>
+
+       <!-- 分组：工具 -->
+       <div class="mint-nav-group-label">工具</div>
+
        <a class="mint-nav-item" ...>Esther工厂</a>
-       <a class="mint-nav-item" ...>设置</a>
      </nav>
    </div>

    <div class="mint-sidebar-bottom">
-     <button class="mint-sidebar-toggle" ...>收起侧栏</button>
+     <a class="mint-nav-item" @click="onOpenSettings">
+       <Settings :size="16" />
+       <span>设置</span>
+     </a>
+     <button class="mint-sidebar-toggle" ...>收起</button>
    </div>
  </aside>
```

### 5.2 JS 变更

```diff
+ import { Search } from 'lucide-vue-next'

+ const searchQuery = ref('')

+ const filteredChatItems = computed(() => {
+   if (!searchQuery.value) return chatDisplayItems.value
+   const q = searchQuery.value.toLowerCase()
+   return chatDisplayItems.value.filter(item =>
+     item.title.toLowerCase().includes(q)
+   )
+ })

- /* 删除 onChatEnter / onChatLeave / onWorkflowEnter / onWorkflowLeave */
- /* 四个函数共 ~120 行，替换为 CSS 过渡 */
```

---

## 6. 实施优先级

| 优先级 | 改动 | 涉及文件 | 工作量 | 风险 |
|--------|------|----------|--------|------|
| **P0** | 去掉 hover translateX/scale/backdrop-filter/伪元素渐变 | `_nav.css` | 小 | 低 |
| **P0** | active 态改为左侧色条 | `_nav.css` | 小 | 低 |
| **P0** | 新建对话按钮独立到顶栏 | `SidebarNav.vue` + `_nav.css` | 中 | 低 |
| **P1** | 顶栏压缩：logo + 新建对话一行 | `SidebarNav.vue` + `_nav.css` | 中 | 低 |
| **P1** | 导航分组（核心/工具） | `SidebarNav.vue` + `_nav.css` | 中 | 低 |
| **P1** | 设置移到底栏 | `SidebarNav.vue` + `_nav.css` | 小 | 低 |
| **P2** | 对话子项 hover 浮现删除图标 | `SidebarNav.vue` + `_nav.css` | 中 | 低 |
| **P2** | 对话标题宽度自适应 | `_nav.css` | 小 | 低 |
| **P2** | 搜索框组件 | `SidebarNav.vue` + `_nav.css` | 中 | 中 |
| **P3** | JS stagger 动画替换为 CSS 方案 | `SidebarNav.vue` | 中 | 中 |
| **P3** | 折叠态 tooltip 简化 | `_nav.css` | 小 | 低 |
| **P3** | 字体统一 | `_nav.css` | 小 | 低 |

---

## 7. 设计原则

> **"安静的容器，显眼的入口，克制的反馈"**

1. **侧栏是容器不是舞台** — 它的职责是导航，不是展示动效。所有装饰性效果（blur、渐变伪元素、skew tooltip）都应该去掉
2. **操作入口必须显眼** — 新建对话是最高频操作，不能藏在行尾小图标里
3. **反馈一层就够** — hover 改背景色，active 加色条，不需要位移+缩放+阴影三重叠加
4. **分组比平铺好** — 5 个项目分两组，认知负荷从 5 降到 2+3
5. **底部空间也是资源** — 设置+折叠放底栏，顶栏就能更紧凑

---

## 8. 预期效果

| 指标 | 改前 | 改后 |
|------|------|------|
| 侧栏首屏可用导航项 | 5 项平铺 | 2 组 5 项，层级清晰 |
| 新建对话可发现性 | 低（行尾小图标） | 高（顶栏独立按钮） |
| 删除对话可发现性 | 低（仅右键） | 中（hover 浮现 + 右键） |
| hover 反馈层级 | 4 层叠加 | 1 层（背景色） |
| active 态视觉重量 | 重（渐变+阴影+高光） | 轻（色条+微灰背景） |
| 顶部空间利用率 | ~110px 仅放 logo | 48px 放 logo + 新建对话 |
| 对话标题可读长度 | 140px | 自适应撑满（~170px） |
| JS 动画代码量 | ~120 行 stagger | ~0 行（CSS 过渡） |
| backdrop-filter 调用 | 每个导航项 | 0 |