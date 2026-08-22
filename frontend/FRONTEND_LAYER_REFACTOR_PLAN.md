# 前端层级重构策划书

> 创建时间：2026-08-22
> 目标：修复前端页面层级问题（卡顿、点击无响应、刷新后才能点击、点击后返回空白、头像缺失）
> 核心原则：
> 1. **可拓展** — 所有修复必须为未来新增页面留好接入点，不能只修当前页面。z-index 用变量、头像用可复用模式、布局用统一结构
> 2. **易维护** — 每个修改都要让后来人一眼看懂为什么这么写。删掉的规则加注释说明、新增的代码加结构标注、变量命名语义化
> 3. **不破坏** — 不删除任何现有文件/组件/逻辑，只修改 CSS 规则和补充缺失代码

---

## 问题根因分析

| # | 问题 | 根因 | 严重度 |
|---|------|------|--------|
| 1 | 全局层级污染 | `body > * { position: relative; z-index: 1 }` 把所有页面根元素压到 z-index:1，fixed 元素堆叠上下文被限制 | P0 |
| 2 | 头像在部分页面不可见 | WorkflowShowcaseView 和 WorkflowTemplatesView 完全没有头像代码 | P0 |
| 3 | 头像被 overflow:hidden 裁切 | TopicPoolView 的头像在 mint-shell 内部，shell 有 overflow:hidden | P0 |
| 4 | z-index 分布混乱 | 0→1→2→10→20→30→100→200→500→600→9998→9999→10000→100000，无分层体系 | P1 |
| 5 | 4层 overflow:hidden 嵌套 | body→mint-shell→content-card-wrapper→content-card，compositing layer 异常 | P1 |
| 6 | transition: all 性能差 | 20+ 处 transition: all 触发不必要的重排重绘 | P2 |
| 7 | pointer-events 冲突 | 19处 pointer-events:none 可能导致点击穿透 | P2 |

---

## 修复步骤

### Step 1：删除 body > * 全局层级污染 [P0]

- **文件**: `frontend/src/styles/workbench/_layout.css`
- **操作**: 删除 `body > * { position: relative; z-index: 1; }` 这一行
- **风险**: 低。这行规则本身就是多余的，body 子元素默认就是 relative，z-index:1 反而制造了问题
- **验证**: 刷新页面，检查 fixed 元素（头像、右键菜单、Settings 弹窗）是否正常显示和交互

### Step 2：给 WorkflowShowcaseView 添加全局头像 [P0]

- **文件**: `frontend/src/views/WorkflowShowcaseView.vue`
- **操作**: 在 `<main>` 标签下、`mint-shell` 之前，添加与 WorkbenchView 相同结构的全局头像组件
- **需要**: 引入 useAuthStore，添加 userDropdownOpen 状态，添加 handleLogout 方法
- **验证**: 访问 /workflow 页面，右上角应显示头像，点击可弹出下拉菜单

### Step 3：给 WorkflowTemplatesView 添加全局头像 [P0]

- **文件**: `frontend/src/views/WorkflowTemplatesView.vue`
- **操作**: 在 mint-shell 外层包裹 `<main>` 标签，在 main 下、shell 之前添加全局头像
- **需要**: 引入 useAuthStore，添加 userDropdownOpen 状态，添加 handleLogout 方法
- **验证**: 访问 /workflow-templates 页面，右上角应显示头像

### Step 4：将 TopicPoolView 的头像移到 shell 外层 [P0]

- **文件**: `frontend/src/views/TopicPoolView.vue`
- **操作**: 
  1. 在 mint-shell 外层包裹 `<main>` 标签
  2. 将 tp-global-user 从 mint-shell 内部移到 main 下、shell 之前
  3. 将 tp-global-user 的 class 改为 mint-global-user（统一命名）
- **验证**: 访问 /topic-pool 页面，头像正常显示，不被 overflow:hidden 裁切

### Step 5：建立统一 z-index 分层体系 [P1]

- **文件**: `frontend/src/styles/workbench/_layout.css`
- **操作**: 在 :root 中定义 z-index CSS 变量层级：
  ```css
  --z-base: 1;
  --z-raised: 10;
  --z-dropdown: 100;
  --z-sticky: 200;
  --z-overlay: 500;
  --z-modal: 1000;
  --z-popover: 2000;
  --z-tooltip: 3000;
  --z-global-ui: 9000;
  --z-max: 9999;
  ```
- **不修改现有 z-index 值**（避免大范围回归），只定义变量供未来使用
- **验证**: 页面各层级元素（侧边栏、弹窗、头像、tooltip）显示顺序不变

### Step 6：修复 mint-content-card-wrapper 的 overflow:hidden [P1]

- **文件**: `frontend/src/styles/workbench/_layout.css`
- **操作**: 将 `.mint-content-card-wrapper { overflow: hidden }` 改为 `overflow: visible`
- **原因**: content-card-wrapper 是 flex 容器，内部只有一个子元素（mint-main），overflow:hidden 完全没必要，反而裁切了内部 fixed 元素
- **验证**: 页面内容正常显示，无溢出

### Step 7：优化 transition: all 为具体属性 [P2]

- **文件**: 各 .vue 文件中的 scoped style
- **操作**: 将 `transition: all 0.2s ease` 改为 `transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease`（只过渡视觉属性，不过渡布局属性）
- **范围**: 只修改 .vue 文件中 scoped style 内的 transition: all（约20处）
- **不修改**: CSS 文件中的 transition（那些已经比较具体）
- **验证**: 页面动画效果不变，但性能更流畅

### Step 8：清理 pointer-events 冲突 [P2]

- **文件**: `frontend/src/styles/workbench/_nav.css`
- **操作**: 检查 .mint-nav-item 和 .mint-nav-sub 上的 ::before/::after 伪元素的 pointer-events:none，确保不会透传到可交互元素
- **验证**: 侧边栏所有导航项可正常点击

### Step 9：构建验证 + 最终测试 [P0]

- **操作**: 
  1. 运行 `npm run build` 确保无编译错误
  2. 逐页访问所有路由，验证功能正常
  3. 检查头像在所有页面可见
  4. 检查点击交互无卡顿
  5. 检查弹窗/下拉菜单层级正确

### Step 10：编写前端开发规范文档 [P1]

- **操作**: 编写 `FRONTEND_DEVELOPMENT_GUIDE.md`，包含：
  - z-index 分层使用规范
  - overflow 使用规范
  - 全局头像组件使用规范
  - 新页面开发模板和要点
  - transition 使用规范
  - 页面布局结构规范

---

## 不做的事情（安全边界）

- ❌ 不删除任何文件或组件
- ❌ 不删除任何现有功能逻辑
- ❌ 不修改路由结构
- ❌ 不修改后端代码
- ❌ 不修改 store 逻辑
- ❌ 不新增依赖包

---

## 每步验证清单

每完成一步，执行以下检查：
- [ ] `npm run build` 编译通过
- [ ] 页面无白屏
- [ ] 头像在当前修改的页面可见
- [ ] 点击交互正常
- [ ] 侧边栏导航正常
- [ ] 弹窗/下拉菜单层级正确