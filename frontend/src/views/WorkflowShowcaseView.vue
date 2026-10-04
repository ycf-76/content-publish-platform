<template>
<div class="min-h-screen" style="position: relative;">

  <div class="mint-shell" :class="{ 'mint-collapsed': isSidebarCollapsed, 'settings-blur': showSettings }" :style="{ '--right-panel-width': '0px', '--left-sidebar-width': leftSidebarWidth + 'px' }">

    <!-- ============ 左侧导航 ============ -->
    <SidebarNav
      current-page="workflow-showcase"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @go-eco="goToEco"
      @new-workflow="goToWorkbench"
      @open-settings="openSettings"
      @new-chat="goToChat"
    />

    <!-- left sidebar resize handle -->
    <div
      class="mint-left-resize-handle"
      v-show="!isSidebarCollapsed"
      :class="{ 'is-left-resizing': isLeftResizing }"
      title="拖拽调整侧边栏宽度 · 双击恢复默认"
      @mousedown="startLeftResize"
      @dblclick.prevent="resetLeftSidebarWidth"
    >
      <div class="mint-resize-line"></div>
    </div>

    <!-- ============ 中间主工作区 ============ -->
    <div class="mint-content-card-wrapper">
    <section class="mint-main ws-page" id="mint-main">

      <!-- ===== 固定卡片容器 ===== -->
      <div class="ws-content-card">
        <div class="ws-container" ref="scrollRef">

          <!-- ===== 标题区 ===== -->
          <section class="ws-hero">
            <h1 class="ws-hero-title">
              <span v-for="(line, i) in heroLines" :key="i" class="ws-hero-line" :style="{ animationDelay: i * 0.4 + 's' }">{{ line }}</span>
            </h1>
            <p class="ws-hero-desc">从洞察到发布，一条 AI 工作流搞定。你的创作成果，都在这里。</p>
          </section>

          <!-- ===== 入口卡片区 ===== -->
          <section class="ws-entry-section">
          <div class="ws-entry-card ws-entry-quick" @click="goToWorkbench">
            <div class="ws-entry-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>
            </div>
            <div class="ws-entry-body">
              <h3 class="ws-entry-title">快速启动</h3>
              <p class="ws-entry-desc">一键跑标准流程：搜索 → 分析 → 写作 → 配图 → 发布</p>
            </div>
            <div class="ws-entry-arrow">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </div>
          </div>

          <div class="ws-entry-card ws-entry-orchestrate" @click="goToWorkflowTemplates">
            <div class="ws-entry-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/></svg>
            </div>
            <div class="ws-entry-body">
              <h3 class="ws-entry-title">动态编排</h3>
              <p class="ws-entry-desc">拖拽节点、自由连线，构建你自己的 AI 工作流</p>
            </div>
            <div class="ws-entry-arrow">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </div>
          </div>
        </section>

        <!-- ===== 成果展示区 ===== -->
        <section class="ws-showcase-section">
          <div class="ws-section-header">
            <h2 class="ws-section-title">最近创作</h2>
            <button v-if="showcaseItems.length > 0" class="ws-view-all" @click="goToHistory">
              查看全部
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
          </div>

          <div v-if="showcaseLoading" class="ws-showcase-loading">
            <div class="ws-showcase-spinner"></div>
            <span>加载中...</span>
          </div>
          <div v-else-if="showcaseItems.length === 0" class="ws-showcase-empty">
            <div class="ws-empty-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M16 2v4"/><path d="M18 2h-4"/><path d="M12 13l-2-2"/><circle cx="10" cy="11" r="2"/></svg>
            </div>
            <p class="ws-empty-text">还没有已完成的创作</p>
            <p class="ws-empty-hint">启动一个工作流，完成后的图文作品会展示在这里</p>
            <button class="mint-btn mint-btn-primary ws-empty-btn" @click="goToWorkbench">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/></svg>
              开始创作
            </button>
          </div>
          <ScatteredDesk v-else :items="showcaseItems" @card-click="onShowcaseCardClick" />
        </section>

        <!-- ===== 传送带河流 ===== -->
        <section v-if="riverItems.length > 0" class="ws-river-section">
          <div class="ws-section-header" style="margin-bottom: 12px;">
            <h2 class="ws-section-title">已完成作品</h2>
          </div>
          <div class="ws-river">
            <div class="ws-river-track">
              <div
                v-for="(ri, i) in [...riverItems, ...riverItems]"
                :key="i"
                class="ws-river-item"
                :style="{ backgroundImage: ri.image ? `url(${ri.image})` : 'none' }"
                @click="ri.workflow_id && onShowcaseCardClick({ workflow_id: ri.workflow_id, topic: ri.title || '', status: 'completed', created_at: '' })"
              >
                <div class="ws-river-overlay">
                  <span class="ws-river-title">{{ ri.title || '未命名创作' }}</span>
                  <span v-if="ri.snippet" class="ws-river-snippet">{{ ri.snippet }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        </div><!-- /ws-container -->

        <!-- ===== 统计区（右上角） ===== -->
        <div class="ws-stats-section">
          <div class="ws-stat">
            <span class="ws-stat-value">{{ totalWorkflows }}</span>
            <span class="ws-stat-label">执行</span>
          </div>
          <div class="ws-stat-divider"></div>
          <div class="ws-stat">
            <span class="ws-stat-value">{{ completedWorkflows }}</span>
            <span class="ws-stat-label">完成</span>
          </div>
          <div class="ws-stat-divider"></div>
          <div class="ws-stat">
            <span class="ws-stat-value">{{ availableNodes }}</span>
            <span class="ws-stat-label">节点</span>
          </div>
        </div>

      </div><!-- /ws-content-card -->

    </section>
    </div>

  </div>

  <SettingsView v-if="showSettings" @close="showSettings = false" />
</div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import ScatteredDesk from '@/components/workbench/ScatteredDesk.vue'
import SettingsView from '@/views/SettingsView.vue'
import { workflowApi } from '@/api/workflow'
import { useUIState } from '@/composables/useUIState'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const { isSidebarCollapsed, toggleSidebar } = useUIState()
const authStore = useAuthStore()

import { useResizeHandle } from '@/composables/useResizeHandle'
const {
  width: leftSidebarWidth,
  isResizing: isLeftResizing,
  startResize: startLeftResize,
  resetWidth: resetLeftSidebarWidth,
} = useResizeHandle({
  direction: 'left',
  minWidth: 170,
  maxWidth: 520,
  storageKey: 'mint-left-sidebar-width-v2',
})

const showSettings = ref(false)
const scrollRef = ref<HTMLElement | null>(null)
const heroLines = ['从灵感到发布', '一条工作流搞定']

interface ShowcaseItem {
  workflow_id: string
  topic: string
  status: string
  cover_image?: string
  title?: string
  content_snippet?: string
  completed_at?: string
  updated_at?: string
  created_at: string
  likes?: number
}

interface RiverItem {
  workflow_id: string
  image?: string
  title?: string
  snippet?: string
}

const showcaseItems = ref<ShowcaseItem[]>([])
const riverItems = ref<RiverItem[]>([])
const totalWorkflows = ref(0)
const completedWorkflows = ref(0)
const availableNodes = ref(8)
const showcaseLoading = ref(true)

async function loadShowcaseData() {
  showcaseLoading.value = true
  try {
    const resp = await workflowApi.getShowcase({ limit: 8 })
    const data = (resp as any)?.data || resp
    const items = data?.items || []
    totalWorkflows.value = data?.total || 0
    completedWorkflows.value = data?.completed_count || 0

    const enriched: ShowcaseItem[] = []
    const allRiverItems: RiverItem[] = []

    for (const item of items) {
      const coverImage = item.cover_image_url || undefined
      const imageUrls: string[] = item.image_urls || []

      enriched.push({
        workflow_id: item.workflow_id,
        topic: item.topic,
        status: item.status,
        cover_image: coverImage,
        title: item.title || undefined,
        content_snippet: item.content_snippet || undefined,
        created_at: item.created_at,
      })

      for (const url of imageUrls) {
        allRiverItems.push({
          workflow_id: item.workflow_id,
          image: url,
          title: item.title || item.topic,
          snippet: item.content_snippet,
        })
      }
    }

    showcaseItems.value = enriched
    riverItems.value = allRiverItems
  } catch (e) {
    console.error('[WorkflowShowcase] loadShowcaseData failed:', e)
  } finally {
    showcaseLoading.value = false
  }
}

function onShowcaseCardClick(item: ShowcaseItem) {
  router.push({ path: '/workbench/' + item.workflow_id, query: { page: 'workflow' } })
}

function goToWorkbench() {
  router.push({ path: '/workbench', query: { page: 'workflow' } })
}

function goToChat() {
  router.push({ path: '/workbench', query: { page: 'chat' } })
}

function goToWorkflowTemplates() {
  router.push('/workflow-templates')
}

function goToHistory() {
  router.push({ path: '/workbench', query: { page: 'history' } })
}

function goToEco() {
  router.push('/eco')
}

function openSettings() {
  showSettings.value = true
}

function handleNavClick(page: string) {
  if (page === 'topic-pool' || page === 'my-works' || page === 'task-plans' || page === 'portfolio') {
    router.push(`/${page}`).catch(() => {})
    return
  }
  router.push({ path: '/workbench', query: { page } })
}

onMounted(async () => {
  await loadShowcaseData()
})
</script>