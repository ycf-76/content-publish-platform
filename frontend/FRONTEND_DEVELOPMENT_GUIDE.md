# 前端开发规范

> 本文档基于 2026-08-22 前端层级重构总结而成
> 核心原则：**可拓展、易维护、不破坏**

---

## 1. z-index 分层规范

### 规则：用 CSS 变量，不硬编码数字

所有 z-index 必须使用 `_layout.css` 中 `:root` 定义的变量：

```css
/* 已定义的层级变量（_layout.css :root 中） */
--z-base: 1;          /* 普通内容层 */
--z-raised: 10;       /* 提升层：侧边栏 toggle、面板按钮 */
--z-sticky: 50;       /* 粘性层：散落卡片、统计区 */
--z-dropdown: 100;    /* 下拉层：select 下拉、导航子菜单 */
--z-overlay: 500;     /* 遮罩层：dialog、collapsed 按钮 */
--z-tooltip: 600;     /* 提示层：tooltip、popover */
--z-modal: 1000;      /* 弹窗层：modal dialog */
--z-global-ui: 9000;  /* 全局 UI 层：头像、右键菜单 overlay */
--z-top: 9999;        /* 最高层：右键菜单、view-transition-new */
--z-max: 10000;       /* 绝对最高：头像下拉菜单 */
```

### 使用示例

```css
/* ✅ 正确 */
.my-tooltip { z-index: var(--z-tooltip); }
.my-dropdown { z-index: var(--z-dropdown); }

/* ❌ 错误 — 硬编码数字 */
.my-tooltip { z-index: 600; }
.my-dropdown { z-index: 999; }
```

### 新增层级

如果现有变量不够用（比如需要一个介于 dropdown 和 overlay 之间的层级），在 `:root` 中新增变量并加注释说明用途，不要在组件里硬编码。

---

## 2. overflow 使用规范

### 规则：尽量少用 overflow:hidden

`overflow: hidden` 会创建新的格式化上下文（BFC），可能导致：
- `position: fixed` 元素在某些浏览器下被裁切
- compositing layer 异常，导致点击无响应

### 分层 overflow 策略

| 层级 | 元素 | overflow | 说明 |
|------|------|----------|------|
| L0 | `body` | `hidden` | ✅ 保留，禁止页面级滚动 |
| L1 | `.mint-shell` | `hidden` | ✅ 保留，shell 内部 flex 布局需要 |
| L2 | `.mint-content-card-wrapper` | `visible` | ✅ 已修复，不裁切内部元素 |
| L3 | `.mint-content-card` / `.ws-content-card` | `hidden` | ⚠️ 保留，卡片圆角需要，但内部不要放 fixed 元素 |

### 原则

- **fixed 元素必须放在 overflow:hidden 容器的外层**
- 卡片内部只放 relative/absolute 元素
- 如果卡片内需要弹出下拉菜单，用 Vue `<Teleport to="body">` 把弹层移到 body 下

---

## 3. 全局头像组件规范

### 规则：头像放在 shell 外层

所有页面的全局头像必须放在 `<main>` 标签下、`.mint-shell` 之前：

```vue
<template>
<main class="min-h-screen" style="position: relative;">

  <!-- 头像（放在 shell 外，避免 overflow:hidden 裁切） -->
  <div v-if="authStore.user" class="mint-global-user"
       :class="{ 'mint-global-user-active': userDropdownOpen }"
       @click="userDropdownOpen = !userDropdownOpen">
    <img v-if="authStore.user.avatar_url"
         :src="authStore.user.avatar_url" alt="头像"
         class="mint-avatar"
         style="width:36px;height:36px;border-radius:50%;object-fit:cover;" />
    <img v-else src="/images/avatar/@man.svg" alt="默认头像"
         class="mint-avatar"
         style="width:36px;height:36px;border-radius:50%;object-fit:cover;" />
    <transition name="mint-dropdown">
      <div v-if="userDropdownOpen" class="mint-global-dropdown" @click.stop>
        <!-- 下拉菜单内容 -->
      </div>
    </transition>
  </div>

  <div class="mint-shell ...">
    <!-- 页面内容 -->
  </div>
</main>
</template>
```

### 必需的 script 引入

```vue
<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const userDropdownOpen = ref(false)

function handleLogout() {
  authStore.logout()
  userDropdownOpen.value = false
  router.push('/login')
}
</script>
```

### ❌ 不要做的事

- 不要把头像放在 `.mint-shell` 内部（会被 overflow:hidden 裁切）
- 不要用 `position: absolute` 定位头像（用 `position: fixed`，样式已在 `_layout.css` 中定义）
- 不要自定义头像 class（统一用 `mint-global-user`，样式已全局定义）

---

## 4. 页面布局结构规范

### 标准三层结构

每个页面必须遵循统一的三层结构：

```
<main>                          ← 页面根元素，position: relative
  <.mint-global-user>           ← 全局头像（fixed，在 shell 外）
  <.mint-shell>                 ← 三栏布局容器
    <SidebarNav />              ← 左侧导航
    <main .mint-main>           ← 中间主内容区
      <.mint-content-card-wrapper>
        <.mint-content-card>    ← 白色圆角卡片
          <!-- 页面具体内容 -->
        </.mint-content-card>
      </.mint-content-card-wrapper>
    </main>
    <!-- 右侧面板（可选） -->
  </.mint-shell>
</main>
```

### 新增页面模板

创建新页面时，复制以下骨架：

```vue
<template>
<main class="min-h-screen" style="position: relative;">

  <div v-if="authStore.user" class="mint-global-user"
       :class="{ 'mint-global-user-active': userDropdownOpen }"
       @click="userDropdownOpen = !userDropdownOpen">
    <img v-if="authStore.user.avatar_url" :src="authStore.user.avatar_url" alt="头像"
         class="mint-avatar" style="width:36px;height:36px;border-radius:50%;object-fit:cover;" />
    <img v-else src="/images/avatar/@man.svg" alt="默认头像"
         class="mint-avatar" style="width:36px;height:36px;border-radius:50%;object-fit:cover;" />
    <transition name="mint-dropdown">
      <div v-if="userDropdownOpen" class="mint-global-dropdown" @click.stop>
        <div class="mint-dropdown-user-section">
          <span class="mint-dropdown-user-name">{{ authStore.user.nickname || '未设置' }}</span>
          <span class="mint-dropdown-user-method">{{ authStore.user.login_method === 'wechat' ? '微信登录' : '邮箱登录' }}</span>
        </div>
        <div class="mint-dropdown-body">
          <button class="mint-dropdown-item mint-dropdown-logout" @click="handleLogout">
            <i data-lucide="log-out" style="width:14px;height:14px;"></i> 退出登录
          </button>
        </div>
      </div>
    </transition>
  </div>

  <div class="mint-shell" :class="{ 'mint-collapsed': isSidebarCollapsed }"
       :style="{ '--right-panel-width': '0px', '--left-sidebar-width': leftSidebarWidth + 'px' }">
    <SidebarNav current-page="your-page-name"
                :is-collapsed="isSidebarCollapsed"
                @nav-click="handleNavClick"
                @toggle-sidebar="toggleSidebar"
                @go-eco="goToEco"
                @open-settings="openSettings" />

    <main class="mint-main">
      <div class="mint-content-card-wrapper">
        <div class="mint-content-card">
          <!-- 你的页面内容 -->
        </div>
      </div>
    </main>
  </div>

  <SettingsView v-if="showSettings" @close="showSettings = false" />
</main>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import SettingsView from '@/views/SettingsView.vue'
import { useUIState } from '@/composables/useUIState'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const { isSidebarCollapsed, toggleSidebar } = useUIState()
const authStore = useAuthStore()

const leftSidebarWidth = ref(220)
const showSettings = ref(false)
const userDropdownOpen = ref(false)

function openSettings() { showSettings.value = true }
function handleLogout() {
  authStore.logout()
  userDropdownOpen.value = false
  router.push('/login')
}
function handleNavClick(page: string) { /* ... */ }
function goToEco() { router.push('/eco') }
</script>
```

---

## 5. transition 使用规范

### 规则：不用 `transition: all`

`transition: all` 会让所有 CSS 属性变化都触发动画，包括 `width`/`height`/`padding` 等引发重排的属性，导致卡顿。

### ✅ 正确写法

```css
/* 只过渡视觉属性 */
.btn {
  transition: background-color 0.2s ease,
              color 0.2s ease,
              border-color 0.2s ease,
              box-shadow 0.2s ease,
              opacity 0.2s ease,
              transform 0.2s ease;
}

/* 简写：如果只需要一两个属性 */
.link {
  transition: color 0.15s ease, opacity 0.15s ease;
}
```

### ❌ 错误写法

```css
.btn {
  transition: all 0.2s ease;  /* 会触发 width/height/padding 等重排 */
}
```

### 性能提示

- 需要动画的元素加 `will-change: transform` 提示浏览器预分配 compositing layer
- 大量重复元素的容器加 `contain: layout style paint` 隔离重排范围

---

## 6. position 定位规范

### 规则：fixed 元素不放在 overflow:hidden 容器内

| 场景 | position | 放置位置 |
|------|----------|---------|
| 全局头像 | fixed | `<main>` 下，shell 外 |
| 右键菜单 overlay | fixed | Teleport 到 body |
| 右键菜单 | fixed | Teleport 到 body |
| tooltip | absolute | 最近的 relative 父元素 |
| 卡片内绝对定位 | absolute | 卡片内部（卡片已有 relative） |
| 统计区 | absolute | 卡片内部（卡片已有 relative） |

### ❌ 不要做的事

- 不要在 `.mint-shell` 内部放 `position: fixed` 元素
- 不要在 `.mint-content-card` 内部放 `position: fixed` 元素
- 需要全局浮层时，用 `<Teleport to="body">`

---

## 7. 卡片内头像规范

### 规则：头像 URL 用 fallback 链

卡片渲染器中显示用户头像时，按以下优先级取值：

```typescript
const resolvedAvatarUrl = computed(() => {
  return props.page.avatarUrl       // 1. 页面数据中的头像
      || authStore.user?.avatar_url  // 2. 全局用户头像
      || ''                          // 3. 空（显示默认占位符）
})
```

模板中：

```vue
<img v-if="resolvedAvatarUrl" :src="resolvedAvatarUrl" class="profile-avatar" alt="" />
<div v-else class="profile-avatar-placeholder">👤</div>
```

---

## 8. 检查清单

新增页面/组件时，逐项检查：

- [ ] z-index 使用变量，不硬编码
- [ ] fixed 元素不在 overflow:hidden 容器内
- [ ] 全局头像在 shell 外层，class 为 `mint-global-user`
- [ ] 页面结构为 main > avatar + shell 三层
- [ ] transition 不用 `all`，只列具体属性
- [ ] 弹层/下拉菜单用 Teleport 到 body
- [ ] 卡片内头像有 fallback 链
- [ ] `npm run build` 编译通过