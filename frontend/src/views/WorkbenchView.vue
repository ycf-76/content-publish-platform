﻿<template>
<main class="min-h-screen">
  <div class="mint-shell" :class="{ 'mint-collapsed': isSidebarCollapsed, 'mint-right-collapsed': isRightPanelCollapsed, 'cards-transparent': cardsTransparent, 'dark-theme': darkTheme }" :style="{ '--right-panel-width': rightPanelWidth + 'px' }">

    <!-- ============ 左侧导航 ============ -->
    <SidebarNav
      :current-page="currentPage"
      :cards-transparent="cardsTransparent"
      :dark-theme="darkTheme"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @toggle-cards-transparent="toggleCardsTransparent"
      @toggle-theme="toggleTheme"
      @go-eco="goToEco"
    />

    <!-- ============ 中间主工作区 ============ -->
    <div class="mint-content-card-wrapper">
    <section class="mint-main" id="mint-main">

      <!-- ========== 工作流页面 ========== -->
      <div class="page-container" id="page-workflow" v-show="currentPage === 'workflow'">
        <!-- 登录欢迎语 -->
        <WelcomeGreeting ref="welcomeGreetingRef" :nickname="authStore.user?.nickname" />

        <!-- 通知横幅 -->
        <div v-if="workflowStore.notifications.length > 0" class="wf-notifications">
          <div
            v-for="n in workflowStore.notifications"
            :key="n.id"
            class="wf-notification"
            :class="`wf-notification-${n.type}`"
          >
            <div class="wf-notification-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <div class="wf-notification-body">
              <div class="wf-notification-message">{{ n.message }}</div>
              <div v-if="n.suggestion" class="wf-notification-suggestion">{{ n.suggestion }}</div>
              <a v-if="n.action_url" :href="n.action_url" target="_blank" rel="noopener" class="wf-notification-action">
                {{ n.action_text || '前往处理' }}
              </a>
            </div>
            <button class="wf-notification-close" @click="workflowStore.dismissNotification(n.id)" title="关闭">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>

        <!-- ===== 节点容器（固定大小，内部滚动） ===== -->
        <div class="wf-nodes-container" ref="nodesContainerRef">

          <!-- ===== 阶段1：search 节点 ===== -->
          <div class="wf-search-row">
            <SearchCard
              class="wf-search-row-main"
              :keyword="keyword"
              :search-platforms="searchPlatforms"
              :selected-platform="selectedPlatform"
              :search-status="searchStatus"
              :search-results="searchResults"
              :search-error="searchError"
              :node-status="getNodeStatus('search')"
              :node-meta="getNodeMeta('search')"
              @update:keyword="keyword = $event"
              @start-flow="startSearchFlow"
              @cancel-and-restart="cancelAndRestart"
              @select-platform="onSelectPlatform"
              @start-from-result="startFromResult"
              @search-similar="searchSimilar"
            />
            <RecommendedCard
              class="wf-search-row-aux"
              @start-from-topic="startFromTopic"
              @search-similar="searchSimilar"
            />
          </div>

          <!-- ===== 阶段2：analyze 节点 ===== -->
          <AnalyzeCard
            :node-status="getNodeStatus('analyze')"
            :node-meta="getNodeMeta('analyze')"
            :result="getNodeResult('analyze')"
            :error-message="getNodeError('analyze')"
          />

          <!-- ===== 阶段3：copywrite 节点 ===== -->
          <CopywriteCard
            :node-status="getNodeStatus('copywrite')"
            :node-meta="getNodeMeta('copywrite')"
            :result="getNodeResult('copywrite')"
            :error-message="getNodeError('copywrite')"
            :workflow-id="currentWorkflowId"
          />

          <!-- ===== 阶段4：image_plan 节点 ===== -->
          <ImagePlanCard
            :node-status="getNodeStatus('image_plan')"
            :node-meta="getNodeMeta('image_plan')"
            :result="getNodeResult('image_plan')"
            :error-message="getNodeError('image_plan')"
          />

          <!-- ===== 阶段5：image_gen 节点 ===== -->
          <ImageGenCard
            :node-status="getNodeStatus('image_gen')"
            :node-meta="getNodeMeta('image_gen')"
            :result="getNodeResult('image_gen')"
            :error-message="getNodeError('image_gen')"
            :card-draft="imagePlanCardDraft"
            :workflow-id="currentWorkflowId"
          />

          <!-- ===== 阶段6：image_review 节点 ===== -->
          <ImageReviewCard
            :node-status="getNodeStatus('image_review')"
            :node-meta="getNodeMeta('image_review')"
            :result="getNodeResult('image_review')"
            :error-message="getNodeError('image_review')"
            :workflow-id="currentWorkflowId"
          />

          <!-- ===== 阶段7：audit 节点 ===== -->
          <AuditCard
            :node-status="getNodeStatus('audit')"
            :node-meta="getNodeMeta('audit')"
            :result="getNodeResult('audit')"
            :error-message="getNodeError('audit')"
          />

          <!-- ===== 阶段8：final_review 节点 ===== -->
          <FinalReviewCard
            :node-status="getNodeStatus('final_review')"
            :node-meta="getNodeMeta('final_review')"
            :result="getNodeResult('final_review')"
            :error-message="getNodeError('final_review')"
            :workflow-id="currentWorkflowId"
          />

          <!-- ===== 阶段9：publish 节点 ===== -->
          <PublishCard
            :node-status="getNodeStatus('publish')"
            :node-meta="getNodeMeta('publish')"
            :result="getNodeResult('publish')"
            :error-message="getNodeError('publish')"
            :workflow-id="currentWorkflowId"
          />
        </div>
      </div>

      <!-- ========== 其他页面 ========== -->
      <div class="page-container" id="page-reviews" v-show="currentPage === 'reviews'">
        <ReviewsPage />
      </div>
      <div class="page-container" id="page-history" v-show="currentPage === 'history'">
        <HistoryPage />
      </div>
      <div class="page-container" id="page-accounts" v-show="currentPage === 'accounts'">
        <AccountsPage />
      </div>
      <div class="page-container" id="page-config" v-show="currentPage === 'config'">
        <ConfigPage />
      </div>

    </section>
    </div>

    <!-- ============ 右侧面板 ============ -->
    <RightPanel
      :is-sidebar-collapsed="isSidebarCollapsed"
      :selected-platform="selectedPlatform"
      :initial-collapsed="isRightPanelCollapsed"
      @update:width="onRightPanelWidthUpdate"
      @update:is-collapsed="onRightPanelCollapsedUpdate"
      @update:model-settings="onModelSettingsUpdate"
    />

  </div>
</main>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { createIcons, icons } from 'lucide'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import RightPanel from '@/components/workbench/RightPanel.vue'
import WelcomeGreeting from '@/components/workbench/WelcomeGreeting.vue'
import ReviewsPage from '@/components/workbench/ReviewsPage.vue'
import HistoryPage from '@/components/workbench/HistoryPage.vue'
import AccountsPage from '@/components/workbench/AccountsPage.vue'
import ConfigPage from '@/components/workbench/ConfigPage.vue'
import SearchCard from '@/components/workbench/SearchCard.vue'
import RecommendedCard from '@/components/workbench/RecommendedCard.vue'
import AnalyzeCard from '@/components/workbench/AnalyzeCard.vue'
import CopywriteCard from '@/components/workbench/CopywriteCard.vue'
import ImagePlanCard from '@/components/workbench/ImagePlanCard.vue'
import ImageGenCard from '@/components/workbench/ImageGenCard.vue'
import ImageReviewCard from '@/components/workbench/ImageReviewCard.vue'
import AuditCard from '@/components/workbench/AuditCard.vue'
import FinalReviewCard from '@/components/workbench/FinalReviewCard.vue'
import PublishCard from '@/components/workbench/PublishCard.vue'
import { useAuthStore } from '@/stores/auth'
import { useAccountStore } from '@/stores/account'
import { useWorkflowStore } from '@/stores/workflow'
import { useSearchFlow } from '@/composables/useSearchFlow'
import { searchApi } from '@/api/search'

const router = useRouter()
const authStore = useAuthStore()
const accountStore = useAccountStore()
const workflowStore = useWorkflowStore()

// ===== 页面切换 =====
const currentPage = ref<string>('workflow')
function handleNavClick(page: string) {
  currentPage.value = page
  nextTick(() => createIcons({ icons }))
}
function goToEco() {
  router.push('/eco')
}

// ===== 侧边栏折叠 =====
const isSidebarCollapsed = ref(false)
function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
}

// ===== 右侧面板 =====
const isRightPanelCollapsed = ref(true)
const rightPanelWidth = ref(280)
function onRightPanelWidthUpdate(w: number) { rightPanelWidth.value = w }
function onRightPanelCollapsedUpdate(c: boolean) { isRightPanelCollapsed.value = c }

// ===== 模型设置 =====
const modelSettings = ref<Record<string, any>>({})
function onModelSettingsUpdate(s: Record<string, any>) { modelSettings.value = s }

// ===== search 节点状态 =====
const keyword = ref('')
const selectedPlatform = ref('')
const searchPlatforms = ref<{ name: string; label: string; desc?: string }[]>([])
const pendingReference = ref<Record<string, any> | null>(null)

const {
  searchStatus,
  searchResults,
  searchError,
  startSearchFlow,
  cancelAndRestart,
} = useSearchFlow(
  keyword,
  selectedPlatform,
  searchPlatforms,
  modelSettings,
  pendingReference,
)

function onSelectPlatform(name: string) {
  selectedPlatform.value = name
}

// ===== 从搜索结果/推荐热点发起分析或搜索同款 =====
function startFromResult(note: any) {
  // 如果工作流正在执行，先提示
  if (workflowStore.isStreaming) {
    if (!confirm('当前有工作流正在执行，是否取消并以此内容为参考发起新分析？')) return
    cancelAndRestart()
  }
  // 构造 reference
  pendingReference.value = {
    title: note.title,
    summary: note.summary,
    url: note.url,
    platform: note.platform,
    author: note.author,
    likes: note.likes,
    source_keyword: note.title,
  }
  keyword.value = note.title || note.summary || ''
  nextTick(() => startSearchFlow())
}

function startFromTopic(item: any) {
  if (workflowStore.isStreaming) {
    if (!confirm('当前有工作流正在执行，是否取消并以此内容为参考发起新分析？')) return
    cancelAndRestart()
  }
  pendingReference.value = {
    title: item.title,
    summary: item.summary,
    url: item.url,
    platform: item.platform,
    author: item.author,
    likes: item.likes,
    comments: item.comments,
    collects: item.collects,
    shares: item.shares,
    source_keyword: item.source_keyword || item.title,
  }
  keyword.value = item.source_keyword || item.title || ''
  nextTick(() => startSearchFlow())
}

function searchSimilar(kw: string) {
  if (!kw) return
  if (workflowStore.isStreaming) {
    if (!confirm('当前有工作流正在执行，是否取消并搜索同款内容？')) return
    cancelAndRestart()
  }
  pendingReference.value = null
  keyword.value = kw
  nextTick(() => startSearchFlow())
}

// ===== 节点容器 ref（用于滚动定位） =====
const nodesContainerRef = ref<HTMLElement | null>(null)

function scrollToNode(nodeId: string) {
  nextTick(() => {
    const el = document.getElementById(`card-${nodeId}`)
    if (el && nodesContainerRef.value) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  })
}

// ===== 各节点完成时自动滚动 =====
watch(() => getNodeStatus('copywrite'), (s) => { if (s === 'running') scrollToNode('copywrite') })
watch(() => getNodeStatus('image_plan'), (s) => { if (s === 'running') scrollToNode('image_plan') })
watch(() => getNodeStatus('image_gen'), (s) => { if (s === 'running') scrollToNode('image_gen') })
watch(() => getNodeStatus('image_review'), (s) => { if (s === 'running') scrollToNode('image_review') })
watch(() => getNodeStatus('audit'), (s) => { if (s === 'running') scrollToNode('audit') })
watch(() => getNodeStatus('final_review'), (s) => { if (s === 'running') scrollToNode('final_review') })
watch(() => getNodeStatus('publish'), (s) => { if (s === 'running') scrollToNode('publish') })

// ===== 主题/卡片透明 =====
const cardsTransparent = ref(false)
const darkTheme = ref(false)
function toggleCardsTransparent() { cardsTransparent.value = !cardsTransparent.value }
function toggleTheme(_e: MouseEvent) { darkTheme.value = !darkTheme.value }

// ===== 欢迎语 =====
const welcomeGreetingRef = ref<InstanceType<typeof WelcomeGreeting> | null>(null)

// ===== 节点状态查询工具函数（所有节点卡片共用） =====
function getNode(nodeId: string) {
  return workflowStore.nodes.find(n => n.node_id === nodeId)
}
function getNodeStatus(nodeId: string): string {
  return getNode(nodeId)?.status || 'idle'
}
function getNodeResult(nodeId: string): any {
  const node = getNode(nodeId) as any
  if (nodeId === 'analyze' && node) {
    console.log('[DEBUG] getNodeResult analyze raw node:', JSON.parse(JSON.stringify(node)))
  }
  if (!node) return null
  // 合并 output 字段和平铺字段。
  // 后端 node_completed 事件把 output dict 平铺到 payload 顶层（results/patterns/insights/layer1_stats/_model_used 等），
  // 而 getNodes / workflow_snapshot 接口可能返回嵌套的 output 字段。
  // 两者都可能出现，合并后返回最完整的数据，平铺字段优先（事件是最新的）。
  const out: Record<string, any> = { ...(node.output || {}) }
  const flatKeys = [
    'results', 'patterns', 'insights', 'layer1_stats', 'filter_stats',
    '_model_used', '_duration_ms', '_token_usage', '_error', '_skipped',
    'title_patterns', 'content_structures', 'emotion_triggers',
    'trend_signals', 'recommendations',
    // copywrite 节点字段
    'title', 'content', 'tags', 'key_points', 'structured_items', 'review_feedback', 'prompt_source',
    // image_plan 节点字段
    'card_draft', 'copywrite_passthrough', '_source',
    // image_gen 节点字段
    'images_base64', 'image_count', 'image_details', 'image_prompts', 'style', 'validation', 'plan_context', 'card_draft_summary',
    // image_review / final_review 节点字段
    'review_status', 'feedback', 'selected_indices', 'blueprint', 'is_blueprint_mode',
    // audit 节点字段
    'passed', 'issues', 'suggestions', 'audit_method', '_skill',
    // publish 节点字段
    'post_id', 'status', 'message',
  ]
  for (const k of flatKeys) {
    if (node[k] !== undefined) out[k] = node[k]
  }
  if (Object.keys(out).length > 0) return out
  return node.result || null
}
function getNodeError(nodeId: string): string {
  const node = getNode(nodeId) as any
  if (!node) return ''
  // 兼容平铺结构：_error 可能直接挂在节点顶层
  return node.error || node._error || node.output?._error || ''
}
function getNodeMeta(nodeId: string): { duration: string; model: string; tokens: string } | null {
  const n = getNode(nodeId) as any
  if (!n) return null
  // 兼容平铺结构：_duration_ms/_model_used/_token_usage 可能直接挂在节点顶层
  const out: any = n.output || n
  return {
    duration: out._duration_ms ? `${out._duration_ms}ms` : '-',
    model: out._model_used || '-',
    tokens: out._token_usage?.total != null ? String(out._token_usage.total) : '-',
  }
}

// ===== ImageGenCard 需要的额外数据 =====
// 从 image_plan 节点结果中提取 card_draft
const imagePlanCardDraft = computed(() => {
  const result = getNodeResult('image_plan')
  return result?.card_draft || null
})

// 当前工作流 ID
const currentWorkflowId = computed(() => {
  return workflowStore.currentWorkflow?.workflow_id || ''
})

// ===== 加载搜索平台列表 =====
async function loadSearchPlatforms() {
  try {
    const res = await searchApi.getPlatforms()
    const list = (res as any).data || res || []
    searchPlatforms.value = [
      { name: '', label: '全部', desc: '并发搜索所有已启用平台' },
      ...(Array.isArray(list) ? list.map((p: any) => ({
        name: p.name,
        label: p.label,
        desc: p.desc,
      })) : []),
    ]
  } catch (e) {
    searchPlatforms.value = [{ name: '', label: '全部', desc: '并发搜索所有已启用平台' }]
  }
}

// ===== 生命周期 =====
onMounted(async () => {
  await nextTick()
  createIcons({ icons })
  welcomeGreetingRef.value?.trigger()
  try { await accountStore.fetchAccounts() } catch (e) { console.warn('fetchAccounts failed:', e) }
  await loadSearchPlatforms()
  try {
    await workflowStore.restoreWorkflow()
  } catch (e) {
    // 静默失败
  }
})

watch(() => workflowStore.nodes, () => {
  nextTick(() => createIcons({ icons }))
}, { deep: true })

// search 节点完成时自动滚动到 analyze 卡片（analyze 已无 interrupt，会自动执行）
watch(() => getNodeStatus('search'), (newStatus) => {
  if (newStatus === 'completed') {
    // 给 search 结果渲染一点时间，然后滚到 analyze
    setTimeout(() => scrollToNode('analyze'), 300)
  }
})
// analyze 开始执行时也滚动一次（保险）
watch(() => getNodeStatus('analyze'), (newStatus) => {
  if (newStatus === 'running') {
    scrollToNode('analyze')
  }
})
</script>

<style scoped>
.page-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  flex: 1;
}

/* 节点容器：固定高度，内部滚动 */
.wf-nodes-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: #D1D5DB transparent;
}
.wf-nodes-container::-webkit-scrollbar { width: 6px; }
.wf-nodes-container::-webkit-scrollbar-track { background: transparent; }
.wf-nodes-container::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 3px; }
/* 搜索行：搜索卡片 + 推荐卡片并排 */
.wf-search-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.wf-search-row-main {
  flex: 1;
  min-width: 0;
}
.wf-search-row-aux {
  flex: 0 0 340px;
}

.wf-nodes-container::-webkit-scrollbar-thumb:hover { background: #9CA3AF; }

/* 通知横幅 */
.wf-notifications {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wf-notification {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 15px;
}
.wf-notification-arrearage,
.wf-notification-config_error,
.wf-notification-workflow_failed,
.wf-notification-workflow_error {
  background: #FEF2F2;
  color: #DC2626;
}
.wf-notification-search_degraded {
  background: #FFFBEB;
  color: #D97706;
}
.wf-notification-icon { flex-shrink: 0; margin-top: 1px; }
.wf-notification-body { flex: 1; min-width: 0; }
.wf-notification-message { font-weight: 500; }
.wf-notification-suggestion { margin-top: 2px; font-size: 14px; opacity: 0.85; }
.wf-notification-action {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 14px;
  text-decoration: underline;
}
.wf-notification-close {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  color: inherit;
  opacity: 0.6;
}
.wf-notification-close:hover { opacity: 1; background: rgba(0,0,0,0.06); }
</style>