<template>
  <aside class="mint-sidebar">
    <div class="mint-sidebar-main">
      <div class="mint-logo-top" @click="goToEco" title="点击查看生态展示" style="cursor:pointer;">
        <div class="mint-logo-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
            <path d="M5 3v4"/>
            <path d="M19 17v4"/>
            <path d="M3 5h4"/>
            <path d="M17 19h4"/>
          </svg>
        </div>
        <div>
          <div class="mint-logo-title">灵犀工坊</div>
          <div class="mint-logo-sub">MINT ATELIER</div>
        </div>
      </div>

      <nav class="mint-nav">
        <a class="mint-nav-item" id="nav-workflow" data-page="workflow" data-tooltip="工作流" @click="$emit('nav-click', 'workflow')" :class="{ 'mint-nav-active': currentPage === 'workflow' }">
          <i data-lucide="workflow"></i>
          <span>工作流</span>
        </a>
        <a class="mint-nav-item" id="nav-topic-pool" data-page="topic-pool" data-tooltip="选题池" @click="goToTopicPool" :class="{ 'mint-nav-active': isTopicPoolActive }">
          <i data-lucide="lightbulb"></i>
          <span>选题池</span>
        </a>
        <a class="mint-nav-item" id="nav-reviews" data-page="reviews" data-tooltip="审核中心" @click="$emit('nav-click', 'reviews')" :class="{ 'mint-nav-active': currentPage === 'reviews' }">
          <i data-lucide="clipboard-check"></i>
          <span>审核中心</span>
        </a>
        <a class="mint-nav-item" id="nav-history" data-page="history" data-tooltip="工作流历史" @click="$emit('nav-click', 'history')" :class="{ 'mint-nav-active': currentPage === 'history' }">
          <i data-lucide="history"></i>
          <span>工作流历史</span>
        </a>
        <a class="mint-nav-item" id="nav-accounts" data-page="accounts" data-tooltip="账号管理" @click="$emit('nav-click', 'accounts')" :class="{ 'mint-nav-active': currentPage === 'accounts' }">
          <i data-lucide="users"></i>
          <span>账号管理</span>
        </a>
        <a class="mint-nav-item" id="nav-config" data-page="config" data-tooltip="配置管理" @click="$emit('nav-click', 'config')" :class="{ 'mint-nav-active': currentPage === 'config' }">
          <i data-lucide="sliders-horizontal"></i>
          <span>配置管理</span>
        </a>
        <a class="mint-nav-item" data-tooltip="系统设置">
          <i data-lucide="settings"></i>
          <span>系统设置</span>
        </a>
        <a class="mint-nav-item mint-nav-collapsible" data-tooltip="切换器" @click="toggleTogglesExpanded">
          <i data-lucide="toggle-right"></i>
          <span>切换器</span>
          <span class="mint-nav-chevron" :class="{ 'mint-nav-chevron-rotated': togglesExpanded }">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </span>
        </a>
        <transition name="mint-subgroup"
          :css="false"
          appear
          @enter="onTogglesEnter"
          @leave="onTogglesLeave">
          <div class="mint-nav-subgroup" v-show="togglesExpanded">
            <a class="mint-nav-sub" data-tooltip="切换卡片透明" @click="$emit('toggle-cards-transparent')">
              <i data-lucide="layers"></i>
              <span>{{ cardsTransparent ? '恢复卡片' : '透明卡片' }}</span>
            </a>
            <a class="mint-nav-sub mint-theme-toggler" data-tooltip="切换星空主题" @click="$emit('toggle-theme', $event)">
              <svg class="mint-theme-toggler-icon icon-sun" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="4"/>
                <path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/>
                <path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>
              </svg>
              <svg class="mint-theme-toggler-icon icon-moon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
              </svg>
              <span>{{ darkTheme ? '星空' : '日间' }}</span>
            </a>
          </div>
        </transition>
      </nav>
    </div>

    <div class="mint-sidebar-bottom">
      <div class="mint-sidebar-actions">
        <button class="mint-sidebar-toggle" id="sidebar-toggle" data-tooltip="收起侧边栏" aria-label="收起侧边栏" @click="$emit('toggle-sidebar')">
          <i data-lucide="panel-left-close"></i>
          <span>收起侧栏</span>
        </button>
      </div>

      <div class="mint-user-card" :class="{ 'mint-user-card-active': accountDropdownOpen }" @click="toggleAccountDropdown">
        <div class="mint-avatar" title="用户头像">
          <img v-if="displayAvatar" :src="displayAvatar" :alt="displayName" style="width:100%; height:100%; object-fit:cover; border-radius:inherit;" />
          <span v-else>{{ avatarInitial }}</span>
        </div>
        <div style="flex:1; min-width:0;">
          <div class="mint-user-name">{{ displayName }}</div>
          <div style="margin-top:3px;">
            <span class="mint-badge badge-mint">
              <span class="mint-status-dot" style="background:#FF2442;"></span>
              {{ displayUserId }}
            </span>
          </div>
        </div>
        <button class="mint-user-switch-btn" @click.stop="toggleAccountDropdown" title="切换账号" type="button">
          <i data-lucide="chevrons-up-down"></i>
        </button>
      </div>

      <transition name="mint-dropdown">
        <div class="mint-account-dropdown" v-if="accountDropdownOpen" ref="dropdownRef">
          <div class="mint-dropdown-header">
            <span>切换账号</span>
            <button class="mint-dropdown-add" @click="goToLoginToAddAccount" type="button" title="添加新账号">
              <i data-lucide="plus"></i>
            </button>
          </div>
          <div class="mint-dropdown-list">
            <div
              v-for="acc in accountStore.accounts"
              :key="acc.account_id"
              class="mint-dropdown-item"
              :class="{ 'is-current': acc.account_id === accountStore.currentAccountId }"
              @click="switchAccount(acc.account_id)"
            >
              <div class="mint-dropdown-avatar">
                <img v-if="acc.xhs_avatar_url" :src="acc.xhs_avatar_url" :alt="acc.xhs_nickname" style="width:100%; height:100%; object-fit:cover; border-radius:inherit;" />
                <span v-else>{{ (acc.xhs_nickname || '?').charAt(0) }}</span>
              </div>
              <div class="mint-dropdown-info">
                <div class="mint-dropdown-name">{{ acc.xhs_nickname || '未命名' }}</div>
                <div class="mint-dropdown-id">小红书号: {{ acc.xhs_user_id || '未绑定' }}</div>
              </div>
              <i v-if="acc.account_id === accountStore.currentAccountId" data-lucide="check" class="mint-dropdown-check"></i>
            </div>
            <div v-if="!accountStore.accounts || accountStore.accounts.length === 0" class="mint-dropdown-empty">
              暂无已绑定账号
            </div>
          </div>
          <div class="mint-dropdown-footer">
            <button class="mint-dropdown-logout" @click="handleLogout" type="button">
              <i data-lucide="log-out"></i>
              <span>退出登录</span>
            </button>
          </div>
        </div>
      </transition>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { createIcons, icons } from 'lucide'
import { useAccountStore } from '@/stores/account'
import { useAuthStore } from '@/stores/auth'

defineProps<{
  currentPage: string
  cardsTransparent: boolean
  darkTheme: boolean
}>()

const emit = defineEmits<{
  'nav-click': [page: string]
  'toggle-sidebar': []
  'toggle-cards-transparent': []
  'toggle-theme': [event: MouseEvent]
  'go-eco': []
}>()

const router = useRouter()
const accountStore = useAccountStore()
const authStore = useAuthStore()

const currentAccount = computed(() => accountStore.currentAccount)
const displayName = computed(() => currentAccount.value?.xhs_nickname || '未绑定账号')
const displayAvatar = computed(() => currentAccount.value?.xhs_avatar_url || '')
const displayUserId = computed(() => {
  const uid = currentAccount.value?.xhs_user_id
  if (!uid) return '未绑定'
  return '小红书号'
})
const avatarInitial = computed(() => {
  const name = displayName.value
  return name ? name.charAt(0) : '?'
})

function goToEco() {
  emit('go-eco')
}

const route = useRoute()
const isTopicPoolActive = computed(() => route.path === '/topic-pool')

function goToTopicPool() {
  router.push('/topic-pool')
}

// ===== 账号下拉 =====
const accountDropdownOpen = ref(false)

function toggleAccountDropdown() {
  accountDropdownOpen.value = !accountDropdownOpen.value
}

function switchAccount(accountId: string) {
  accountStore.selectAccount(accountId)
  accountDropdownOpen.value = false
  nextTick(() => createIcons({ icons }))
}

function goToLoginToAddAccount() {
  accountDropdownOpen.value = false
  router.push('/login')
}

function closeAccountDropdown(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.mint-user-card') && !target.closest('.mint-account-dropdown')) {
    accountDropdownOpen.value = false
  }
}

async function handleLogout() {
  if (!confirm('确定要退出登录吗？')) return
  await authStore.logout()
  router.push('/login')
}

const togglesExpanded = ref(false)

function toggleTogglesExpanded() {
  togglesExpanded.value = !togglesExpanded.value
}

function onTogglesEnter(el: Element, done: () => void) {
  const container = el as HTMLElement
  const items = Array.from(container.querySelectorAll('.mint-nav-sub')) as HTMLElement[]

  container.style.height = '0'
  container.style.opacity = '0'
  container.style.overflow = 'hidden'
  items.forEach((item) => {
    item.style.opacity = '0'
    item.style.transform = 'translateX(-12px)'
  })

  void container.offsetHeight

  const targetHeight = container.scrollHeight
  container.style.transition = 'height 0.32s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.28s ease'
  container.style.height = targetHeight + 'px'
  container.style.opacity = '1'

  items.forEach((item, i) => {
    const delay = 90 + i * 70
    item.style.transition = `opacity 0.34s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms, transform 0.34s cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms`
  })

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      items.forEach((item) => {
        item.style.opacity = '1'
        item.style.transform = 'translateX(0)'
      })
    })
  })

  const total = 320 + 90 + Math.max(0, items.length - 1) * 70 + 340 + 60
  window.setTimeout(() => {
    container.style.height = ''
    container.style.overflow = ''
    container.style.transition = ''
    container.style.opacity = ''
    items.forEach((item) => {
      item.style.transition = ''
      item.style.transform = ''
      item.style.opacity = ''
    })
    done()
  }, total)
}

function onTogglesLeave(el: Element, done: () => void) {
  const container = el as HTMLElement
  const items = Array.from(container.querySelectorAll('.mint-nav-sub')) as HTMLElement[]

  const currentHeight = container.offsetHeight
  container.style.height = currentHeight + 'px'
  container.style.overflow = 'hidden'

  items.forEach((item, i) => {
    const reverseDelay = (items.length - 1 - i) * 45
    item.style.transition = `opacity 0.2s ease ${reverseDelay}ms, transform 0.2s ease ${reverseDelay}ms`
    item.style.opacity = '0'
    item.style.transform = 'translateX(-8px)'
  })

  void container.offsetHeight
  const collapseDelay = items.length * 45 + 60
  container.style.transition = `height 0.28s cubic-bezier(0.4, 0, 1, 1) ${collapseDelay}ms, opacity 0.24s ease ${collapseDelay}ms`
  container.style.height = '0'
  container.style.opacity = '0'

  const total = collapseDelay + 280 + 30
  window.setTimeout(() => {
    done()
  }, total)
}

onMounted(() => {
  document.addEventListener('click', closeAccountDropdown)
  nextTick(() => createIcons({ icons }))
})

onUnmounted(() => {
  document.removeEventListener('click', closeAccountDropdown)
})
</script>
