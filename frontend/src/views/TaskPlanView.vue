<template>
<div class="min-h-screen" style="position: relative;">

  <div class="mint-shell da-shell" :class="{ 'mint-collapsed': isSidebarCollapsed }" :style="{ '--left-sidebar-width': leftSidebarWidth + 'px' }">

    <SidebarNav
      :current-page="'task-plans'"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @go-eco="goToEco"
      @open-settings="openSettings"
      @new-workflow="goToWorkbench"
      @new-chat="goToChat"
    />

    <div v-if="!isSidebarCollapsed" class="da-sidebar-resizer" @mousedown="startSidebarResize"><div class="da-sidebar-resizer-line"></div></div>

    <main class="da-page">
      <div class="da-content-card-wrapper">
      <div class="da-content-card">

        <div class="da-topbar">
          <h1 class="da-topbar-title">任务清单</h1>
          <div class="da-topbar-actions">
            <button class="tp-btn tp-btn-primary" @click="openCreate"><Plus :size="14" :stroke-width="2" /> 新建清单</button>
            <button class="tp-btn tp-btn-ghost" @click="loadPlans" :disabled="loading"><RefreshCw :size="14" :stroke-width="2" :class="{ 'tp-spin': loading }" /> 刷新</button>
          </div>
        </div>

      <div class="tp-container">

        <div v-if="plans.length === 0 && !loading" class="tp-empty-state">
          <div class="tp-empty-icon-wrap">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none"><rect x="6" y="8" width="36" height="34" rx="4" stroke="#D1D5DB" stroke-width="2"/><path d="M6 18h36M15 4v8M33 4v8" stroke="#D1D5DB" stroke-width="2" stroke-linecap="round"/><path d="M17 28l4 4 8-8" stroke="#2563EB" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <p class="tp-empty-title">还没有定时任务清单</p>
          <p class="tp-empty-desc">发布一句话意图，例如「10 个单词每天发一个」，系统逐日自动写图文并定时发布</p>
          <button class="tp-btn tp-btn-primary" @click="openCreate"><Plus :size="14" :stroke-width="2" /> 新建清单</button>
        </div>

        <template v-else>

          <div class="tp-metrics-row">
            <div class="tp-metric-card"><span class="tp-metric-val">{{ plans.length }}</span><span class="tp-metric-label">清单总数</span></div>
            <div class="tp-metric-card"><span class="tp-metric-val">{{ activeCount }}</span><span class="tp-metric-label">进行中</span></div>
            <div class="tp-metric-card"><span class="tp-metric-val">{{ totalPublishedDays }}</span><span class="tp-metric-label">已发布天数</span></div>
            <div class="tp-metric-card"><span class="tp-metric-val">{{ totalPendingDays }}</span><span class="tp-metric-label">待执行天数</span></div>
            <div class="tp-metric-card" :class="{ 'tp-metric-card-warn': totalFailedDays > 0 }"><span class="tp-metric-val">{{ totalFailedDays }}</span><span class="tp-metric-label">失败天数</span></div>
          </div>

          <div class="tp-plans-list">
            <div v-for="p in plans" :key="p.id" class="tp-plan-card" @click="openDetail(p.id)">
              <div class="tp-plan-main">
                <div class="tp-plan-title-row">
                  <span class="tp-plan-title">{{ p.title || '未命名清单' }}</span>
                  <span class="tp-status-badge" :class="'tp-status-' + p.status">{{ statusLabel(p.status) }}</span>
                </div>
                <div class="tp-plan-meta">
                  <span class="tp-meta-item"><Clock :size="13" :stroke-width="2" /> 每日 {{ p.plan_config?.daily_time || '09:00' }}</span>
                  <span class="tp-meta-item"><CalendarDays :size="13" :stroke-width="2" /> {{ p.total_days }} 天</span>
                  <span class="tp-meta-item"><ShieldCheck :size="13" :stroke-width="2" /> {{ reviewModeLabel(p.plan_config?.review_mode) }}</span>
                  <span class="tp-meta-item" v-if="p.plan_config?.publish_strategy === 'auto'"><MousePointerClick :size="13" :stroke-width="2" /> 自动发布（实验）</span>
                  <span class="tp-meta-item" v-else><MousePointerClick :size="13" :stroke-width="2" /> 半自动发布</span>
                </div>
                <div class="tp-progress-row">
                  <div class="tp-progress-bar">
                    <div class="tp-progress-fill" :style="{ width: progressPercent(p) + '%' }"></div>
                  </div>
                  <span class="tp-progress-text">已发布 {{ p.published_days }}/{{ p.total_days }}<template v-if="p.failed_days"> · 失败 {{ p.failed_days }}</template></span>
                </div>
              </div>
              <div class="tp-plan-actions" @click.stop>
                <button v-if="p.status === 'active'" class="tp-icon-btn" title="暂停" @click="handlePause(p)"><Pause :size="16" :stroke-width="2" /></button>
                <button v-if="p.status === 'paused'" class="tp-icon-btn tp-icon-btn-accent" title="恢复" @click="handleResume(p)"><Play :size="16" :stroke-width="2" /></button>
                <button v-if="p.status === 'active' || p.status === 'paused'" class="tp-icon-btn tp-icon-btn-danger" title="取消清单" @click="handleCancel(p)"><X :size="16" :stroke-width="2" /></button>
              </div>
            </div>
          </div>

        </template>

      </div>
      </div>
      </div>
    </main>
  </div>

  <!-- ===== 新建清单抽屉 ===== -->
  <div class="tp-drawer-overlay" v-if="createVisible" @click.self="closeCreate">
    <div class="tp-drawer tp-drawer-wide">
      <div class="tp-drawer-header">
        <h2>新建定时任务清单</h2>
        <button class="tp-drawer-close" @click="closeCreate"><X :size="16" :stroke-width="2" /></button>
      </div>
      <div class="tp-drawer-body">

        <p class="tp-hint">用一句话或多行清单描述发布意图，系统拆解成逐日任务：每天到点自动写图文并发小红书。</p>

        <div class="tp-form-row">
          <label class="tp-form-label">发布意图</label>
          <textarea v-model="createForm.intent" rows="6" class="tp-textarea" placeholder="示例：&#10;背单词计划：ability, benefit, culture, develop, economy, factor...&#10;每天发一个单词的记忆卡笔记，早上 9 点发布"></textarea>
        </div>

        <div class="tp-form-grid">
          <div class="tp-form-row">
            <label class="tp-form-label">每日发布时间</label>
            <input v-model="createForm.dailyTime" type="time" class="tp-input" />
          </div>
          <div class="tp-form-row">
            <label class="tp-form-label">账号</label>
            <select v-model="createForm.accountId" class="tp-select">
              <option value="">默认账号</option>
            </select>
          </div>
        </div>

        <div class="tp-form-grid">
          <div class="tp-form-row">
            <label class="tp-form-label">审核方式</label>
            <select v-model="createForm.reviewMode" class="tp-select">
              <option value="quality_gate">质量门 · AI 审核不达标转人工（推荐）</option>
              <option value="auto">全自动 · 不打断</option>
              <option value="manual">人工 · 每次发飞书卡片确认</option>
            </select>
          </div>
          <div class="tp-form-row">
            <label class="tp-form-label">发布方式</label>
            <select v-model="createForm.publishStrategy" class="tp-select">
              <option value="manual">半自动 · 到点填好内容，手动点发布</option>
              <option value="auto">自动点击 · 实验性，失败自动降级半自动</option>
            </select>
          </div>
        </div>

        <div class="tp-form-actions">
          <button class="tp-btn tp-btn-primary" @click="handleDecompose(false)" :disabled="decomposing || !createForm.intent.trim()">
            <Sparkles :size="14" :stroke-width="2" /> {{ decomposing ? '拆解中...' : 'AI 拆解' }}
          </button>
          <button class="tp-btn tp-btn-ghost" @click="handleDecompose(true)" :disabled="!createForm.intent.trim()" title="按行切分意图，不调用大模型，不消耗 Token">
            <FileText :size="14" :stroke-width="2" /> 规则拆解（零 Token 测试）
          </button>
        </div>

        <!-- 拆解结果：可编辑预览 -->
        <template v-if="preview">
          <div class="tp-preview-head">
            <h3>拆解预览（共 {{ preview.items.length }} 天，可编辑）</h3>
            <span v-if="previewTitle !== preview.title" class="tp-preview-title-hint">标题：{{ preview.title }}</span>
          </div>
          <div class="tp-preview-warnings" v-if="preview.warnings?.length">
            <div v-for="(w, i) in preview.warnings" :key="i" class="tp-warning-item"><AlertTriangle :size="13" :stroke-width="2" /> {{ w }}</div>
          </div>
          <div class="tp-preview-table">
            <div class="tp-pt-row tp-pt-header">
              <span class="tp-pt-day">天</span>
              <span class="tp-pt-topic">当天主题（可编辑）</span>
              <span class="tp-pt-keyword">关键词（可编辑）</span>
            </div>
            <div class="tp-pt-row" v-for="(it, idx) in preview.items" :key="idx">
              <span class="tp-pt-day">D{{ it.day_index }}</span>
              <input class="tp-pt-input tp-pt-topic-input" v-model="it.topic" placeholder="当天发布主题" />
              <input class="tp-pt-input" v-model="it.keyword" placeholder="搜索关键词（可选）" />
            </div>
          </div>
          <div class="tp-form-actions">
            <button class="tp-btn tp-btn-primary" @click="handleCreate" :disabled="creating || !validPreview">
              <Check :size="14" :stroke-width="2" /> {{ creating ? '创建中...' : '确认创建并生效' }}
            </button>
            <button class="tp-btn tp-btn-ghost" @click="preview = null">重新拆解</button>
          </div>
        </template>

      </div>
    </div>
  </div>

  <!-- ===== 清单详情抽屉 ===== -->
  <div class="tp-drawer-overlay" v-if="detailVisible" @click.self="closeDetail">
    <div class="tp-drawer tp-drawer-wide" v-if="detail">
      <div class="tp-drawer-header">
        <h2>{{ detail.title || '清单详情' }}</h2>
        <button class="tp-drawer-close" @click="closeDetail"><X :size="16" :stroke-width="2" /></button>
      </div>
      <div class="tp-drawer-body">

        <div class="tp-detail-meta">
          <span class="tp-status-badge" :class="'tp-status-' + detail.status">{{ statusLabel(detail.status) }}</span>
          <span class="tp-meta-item"><Clock :size="13" :stroke-width="2" /> 每日 {{ detail.plan_config?.daily_time || '09:00' }}</span>
          <span class="tp-meta-item"><CalendarDays :size="13" :stroke-width="2" /> {{ detail.published_days }}/{{ detail.total_days }} 天已发布</span>
          <span v-if="detail.failed_days" class="tp-meta-item tp-meta-warn">失败 {{ detail.failed_days }} 天</span>
          <button v-if="detail.status === 'active'" class="tp-btn tp-btn-sm" @click="handlePause(detail); refreshDetail()"><Pause :size="13" :stroke-width="2" /> 暂停</button>
          <button v-if="detail.status === 'paused'" class="tp-btn tp-btn-sm tp-btn-primary" @click="handleResume(detail); refreshDetail()"><Play :size="13" :stroke-width="2" /> 恢复</button>
        </div>

        <div class="tp-detail-section">
          <h3 class="tp-detail-title">原始意图</h3>
          <pre class="tp-pre">{{ detail.intent_text }}</pre>
        </div>

        <div class="tp-detail-section">
          <h3 class="tp-detail-title">逐日安排</h3>
          <div class="tp-timeline">
            <div v-for="it in detail.items" :key="it.id" class="tp-tl-item" :class="'tp-tl-' + it.status">
              <div class="tp-tl-marker"></div>
              <div class="tp-tl-body">
                <div class="tp-tl-head">
                  <span class="tp-tl-day">Day {{ it.day_index }}</span>
                  <span class="tp-item-status" :class="'tp-item-' + it.status">{{ itemStatusLabel(it.status) }}</span>
                  <span class="tp-tl-time">{{ formatDateTime(it.plan_time) }}</span>
                </div>
                <div class="tp-tl-topic">{{ it.topic }}</div>
                <div class="tp-tl-sub" v-if="it.keyword">关键词：{{ it.keyword }}</div>
                <div class="tp-tl-error" v-if="it.last_error?.reason">
                  <AlertTriangle :size="12" :stroke-width="2" /> {{ it.last_error.reason }}
                  <span v-if="it.retry_count > 0">（已重试 {{ it.retry_count }} 次）</span>
                </div>
                <div class="tp-tl-sub tp-tl-confirm" v-if="it.latest_run?.status === 'awaiting_confirmation'">
                  <Bell :size="12" :stroke-width="2" /> 已发飞书卡片等待确认（确认 / 打回 / 跳过）
                </div>
                <div class="tp-tl-sub" v-if="it.workflow_id">
                  <a class="tp-tl-link" @click.stop="goToWorkflow(it.workflow_id!)">查看当日工作流</a>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>

</div>

<ConfirmDialog
  :visible="confirmState.visible"
  :title="confirmState.title"
  :message="confirmState.message"
  :confirm-text="confirmState.confirmText"
  :cancel-text="confirmState.cancelText"
  :danger="confirmState.danger"
  @confirm="onConfirm"
  @cancel="onCancel"
/>

</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Plus, RefreshCw, Clock, CalendarDays, ShieldCheck, MousePointerClick,
  Pause, Play, X, Sparkles, FileText, Check, AlertTriangle, Bell,
} from 'lucide-vue-next'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import { useUIState } from '@/composables/useUIState'
import { useAccountStore } from '@/stores/account'
import {
  listTaskPlans, getTaskPlanDetail, decomposeIntent, createTaskPlan,
  pauseTaskPlan, resumeTaskPlan, cancelTaskPlan,
  type TaskPlanSummary, type TaskPlanDetail, type DecomposeResult,
} from '@/api/taskPlan'
import { useConfirm } from '@/composables/useConfirm'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const router = useRouter()
const { state: confirmState, confirm, onConfirm, onCancel } = useConfirm()
const accountStore = useAccountStore()
const { isSidebarCollapsed, toggleSidebar: toggleSidebarBase } = useUIState()

function toggleSidebar() { toggleSidebarBase() }
function handleNavClick(pageName: string) {
  if (pageName === 'home') { router.push('/').catch(() => {}); return }
  if (pageName === 'task-plans') return
  if (pageName === 'topic-pool') { router.push('/topic-pool').catch(() => {}); return }
  if (pageName === 'my-works') { router.push('/my-works').catch(() => {}); return }
  if (pageName === 'portfolio') { router.push('/portfolio').catch(() => {}); return }
  router.push({ path: '/workbench', query: { page: pageName } })
}
function goToEco() { router.push('/eco') }
function openSettings() {
  window.dispatchEvent(new Event('open-settings'))
}
function goToWorkbench() { router.push({ path: '/workbench', query: { page: 'workflow' } }) }
function goToChat() { router.push('/workbench') }
function goToWorkflow(workflowId: string) {
  router.push({ path: '/workbench', query: { page: 'workflow', workflow: workflowId } })
}
import { useResizeHandle } from '@/composables/useResizeHandle'
const {
  width: leftSidebarWidth,
  isResizing: isLeftResizing,
  startResize: startSidebarResize,
  resetWidth: resetLeftSidebarWidth,
} = useResizeHandle({
  direction: 'left',
  minWidth: 170,
  maxWidth: 520,
  storageKey: 'mint-left-sidebar-width-v2',
})

// ---------- 状态 ----------
const plans = ref<TaskPlanSummary[]>([])
const loading = ref(false)

const createVisible = ref(false)
const decomposing = ref(false)
const creating = ref(false)
const preview = ref<DecomposeResult | null>(null)

const detailVisible = ref(false)
const detail = ref<TaskPlanDetail | null>(null)

const createForm = ref({
  intent: '',
  dailyTime: '09:00',
  accountId: '',
  reviewMode: 'quality_gate' as 'quality_gate' | 'auto' | 'manual',
  publishStrategy: 'manual' as 'manual' | 'auto',
})

// ---------- 计算属性 ----------
const activeCount = computed(() => plans.value.filter(p => p.status === 'active').length)
const totalPublishedDays = computed(() => plans.value.reduce((s, p) => s + (p.published_days || 0), 0))
const totalFailedDays = computed(() => plans.value.reduce((s, p) => s + (p.failed_days || 0), 0))
const totalPendingDays = computed(() =>
  plans.value.filter(p => p.status === 'active').reduce((s, p) => s + Math.max(0, p.total_days - p.published_days - p.failed_days), 0),
)
const previewTitle = computed(() => preview.value?.title || '')
const validPreview = computed(() =>
  !!preview.value && preview.value.items.length > 0 &&
  preview.value.items.every(it => it.topic.trim().length > 0),
)

// ---------- 标签 ----------
const STATUS_LABELS: Record<string, string> = { active: '进行中', paused: '已暂停', completed: '已完成', cancelled: '已取消' }
function statusLabel(s: string) { return STATUS_LABELS[s] || s }

const ITEM_STATUS_LABELS: Record<string, string> = {
  pending: '待发布', running: '执行中', published: '已发布',
  failed: '失败', skipped: '已跳过', cancelled: '已取消',
}
function itemStatusLabel(s: string) { return ITEM_STATUS_LABELS[s] || s }

function reviewModeLabel(mode?: string) {
  const m: Record<string, string> = { quality_gate: '质量门审核', auto: '全自动', manual: '人工确认' }
  return m[mode || 'quality_gate'] || mode || '质量门审核'
}

function progressPercent(p: TaskPlanSummary) {
  if (!p.total_days) return 0
  return Math.round(((p.published_days + p.failed_days) / p.total_days) * 100)
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ---------- 列表 ----------
async function loadPlans() {
  loading.value = true
  try {
    plans.value = await listTaskPlans()
  } catch (e: any) {
    console.error('[TaskPlan] load plans failed:', e)
  } finally {
    loading.value = false
  }
}

// ---------- 创建流 ----------
function openCreate() {
  createVisible.value = true
  preview.value = null
  if (!accountStore.accounts.length) accountStore.fetchAccounts()
}
function closeCreate() {
  createVisible.value = false
  preview.value = null
}

async function handleDecompose(dryRun: boolean) {
  const intent = createForm.value.intent.trim()
  if (!intent) return
  decomposing.value = true
  try {
    preview.value = await decomposeIntent(intent, createForm.value.dailyTime, dryRun)
    if (dryRun && !preview.value.items.length) preview.value = null
  } catch (e: any) {
    console.error('[TaskPlan] decompose failed:', e)
    alert(e.response?.data?.detail || e.response?.data?.message || '拆解失败，请稍后重试')
  } finally {
    decomposing.value = false
  }
}

async function handleCreate() {
  if (!preview.value || !validPreview.value) return
  creating.value = true
  try {
    await createTaskPlan({
      intent_text: createForm.value.intent.trim(),
      title: createForm.value.intent.trim().split('\n')[0].slice(0, 100),
      account_id: createForm.value.accountId || null,
      items: preview.value.items
        .filter(it => it.topic.trim())
        .map((it, i) => ({
          day_index: i + 1,
          topic: it.topic.trim(),
          keyword: it.keyword?.trim() || null,
        })),
      plan_config: {
        daily_time: createForm.value.dailyTime,
        review_mode: createForm.value.reviewMode,
        publish_strategy: createForm.value.publishStrategy,
      },
    })
    closeCreate()
    createForm.value.intent = ''
    await loadPlans()
  } catch (e: any) {
    console.error('[TaskPlan] create failed:', e)
    alert(e.response?.data?.detail || e.response?.data?.message || '创建失败，请稍后重试')
  } finally {
    creating.value = false
  }
}

// ---------- 生命周期 ----------
async function handlePause(p: TaskPlanSummary | TaskPlanDetail) {
  try {
    await pauseTaskPlan(p.id)
    await loadPlans()
  } catch (e: any) {
    alert(e.response?.data?.detail || '暂停失败')
  }
}
async function handleResume(p: TaskPlanSummary | TaskPlanDetail) {
  try {
    await resumeTaskPlan(p.id)
    await loadPlans()
  } catch (e: any) {
    alert(e.response?.data?.detail || '恢复失败')
  }
}
async function handleCancel(p: TaskPlanSummary | TaskPlanDetail) {
  const ok = await confirm({
    title: '取消任务清单',
    message: `确定取消清单「${p.title}」？\n未执行的条目将全部取消，不可恢复。`,
    danger: true,
  })
  if (!ok) return
  try {
    await cancelTaskPlan(p.id)
    await loadPlans()
    if (detail.value?.id === p.id) await refreshDetail()
  } catch (e: any) {
    alert(e.response?.data?.detail || '取消失败')
  }
}

// ---------- 详情 ----------
async function openDetail(planId: string) {
  detailVisible.value = true
  detail.value = null
  try {
    detail.value = await getTaskPlanDetail(planId)
  } catch (e: any) {
    console.error('[TaskPlan] load detail failed:', e)
    detailVisible.value = false
  }
}
function closeDetail() {
  detailVisible.value = false
  detail.value = null
}
async function refreshDetail() {
  if (!detail.value) return
  try {
    detail.value = await getTaskPlanDetail(detail.value.id)
  } catch { /* 静默 */ }
}

onMounted(() => {
  loadPlans()
})
</script>

<style scoped>
.da-shell { grid-template-columns: auto auto 1fr !important; }
.da-shell.mint-collapsed { grid-template-columns: 56px 1fr !important; }
.da-sidebar-resizer { position: relative; width: 0; cursor: col-resize; flex-shrink: 0; align-self: stretch; z-index: 5; overflow: visible; }
.da-sidebar-resizer::before { content: ''; position: absolute; top: 0; bottom: 0; left: -4px; right: -4px; z-index: 1; }
.da-sidebar-resizer-line { display: none !important; }
.da-sidebar-resizer:hover { background: rgba(0, 0, 0, 0.04); }

.da-page { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; overflow: hidden; padding: 56px 20px 16px; }
.da-content-card-wrapper { display: flex; flex-direction: column; flex: 1; min-height: 0; min-width: 0; overflow: hidden; }
.da-content-card { flex: 1; min-height: 0; min-width: 0; background: #FFFFFF; border-radius: 16px; border: 1px solid var(--ma-border-default, #E5E7EB); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04); display: flex; flex-direction: column; overflow: hidden; }
.da-topbar { display: flex; align-items: center; justify-content: space-between; padding: 14px 24px; border-bottom: 1px solid var(--ma-border-default, #E5E7EB); flex-shrink: 0; background: var(--ma-bg-base, #FAFAFA); }
.da-topbar-title { font-size: 20px; font-weight: 700; margin: 0; color: #1a1a1a; }
.da-topbar-actions { display: flex; gap: 8px; }

/* ---------- 按钮（蓝色主色，线框风格图标） ---------- */
.tp-btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; border: 1px solid #E5E7EB; background: #fff; color: #374151; transition: all 0.15s; white-space: nowrap; }
.tp-btn:hover { border-color: #93C5FD; background: #F8FAFF; color: #1D4ED8; }
.tp-btn-primary { background: #2563EB; color: #fff; border-color: #2563EB; }
.tp-btn-primary:hover { background: #1D4ED8; border-color: #1D4ED8; color: #fff; }
.tp-btn-ghost { background: transparent; }
.tp-btn-ghost:hover { background: #F9FAFB; }
.tp-btn-sm { padding: 4px 10px; font-size: 12px; }
.tp-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.tp-spin { animation: tp-rotate 1s linear infinite; }
@keyframes tp-rotate { to { transform: rotate(360deg); } }

/* ---------- 容器 ---------- */
.tp-container { flex: 1; overflow-y: auto; padding: 20px 24px; }

/* ---------- 空态 ---------- */
.tp-empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 80px 20px; gap: 6px; }
.tp-empty-icon-wrap { margin-bottom: 10px; }
.tp-empty-title { font-size: 16px; font-weight: 600; color: #374151; margin: 0; }
.tp-empty-desc { font-size: 13px; color: #9CA3AF; margin: 0 0 16px; }

/* ---------- 指标卡 ---------- */
.tp-metrics-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 16px; }
.tp-metric-card { padding: 14px 16px; background: #F9FAFB; border: 1px solid #F3F4F6; border-radius: 10px; display: flex; flex-direction: column; }
.tp-metric-val { font-size: 22px; font-weight: 700; color: #1a1a1a; line-height: 1.2; }
.tp-metric-label { font-size: 11px; color: #9CA3AF; margin-top: 2px; }
.tp-metric-card-warn { background: #FFFBEB; border-color: #FEF3C7; }
.tp-metric-card-warn .tp-metric-val { color: #D97706; }

/* ---------- 清单卡片 ---------- */
.tp-plans-list { display: flex; flex-direction: column; gap: 10px; }
.tp-plan-card { display: flex; align-items: center; gap: 16px; padding: 16px 20px; background: #fff; border: 1px solid #E5E7EB; border-radius: 12px; cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s; }
.tp-plan-card:hover { border-color: #93C5FD; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.08); }
.tp-plan-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.tp-plan-title-row { display: flex; align-items: center; gap: 10px; }
.tp-plan-title { font-size: 15px; font-weight: 600; color: #1a1a1a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tp-plan-meta { display: flex; flex-wrap: wrap; gap: 14px; }
.tp-meta-item { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: #6B7280; }
.tp-meta-item svg { color: #2563EB; }
.tp-meta-warn { color: #D97706; }
.tp-progress-row { display: flex; align-items: center; gap: 10px; }
.tp-progress-bar { flex: 1; max-width: 320px; height: 6px; background: #F3F4F6; border-radius: 3px; overflow: hidden; }
.tp-progress-fill { height: 100%; background: #2563EB; border-radius: 3px; transition: width 0.3s; }
.tp-progress-text { font-size: 12px; color: #6B7280; white-space: nowrap; }
.tp-plan-actions { display: flex; gap: 6px; }
.tp-icon-btn { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 8px; border: 1px solid #E5E7EB; background: #fff; color: #6B7280; cursor: pointer; transition: all 0.15s; }
.tp-icon-btn:hover { border-color: #93C5FD; color: #2563EB; background: #F8FAFF; }
.tp-icon-btn-accent:hover { border-color: #86EFAC; color: #16A34A; background: #F0FDF4; }
.tp-icon-btn-danger:hover { border-color: #FCA5A5; color: #DC2626; background: #FEF2F2; }

/* ---------- 状态徽章 ---------- */
.tp-status-badge { display: inline-flex; align-items: center; padding: 2px 10px; border-radius: 999px; font-size: 11px; font-weight: 500; border: 1px solid transparent; flex-shrink: 0; }
.tp-status-active { background: #EFF6FF; color: #2563EB; border-color: #BFDBFE; }
.tp-status-paused { background: #FFFBEB; color: #D97706; border-color: #FDE68A; }
.tp-status-completed { background: #F0FDF4; color: #16A34A; border-color: #BBF7D0; }
.tp-status-cancelled { background: #F3F4F6; color: #9CA3AF; border-color: #E5E7EB; }

/* ---------- 抽屉 ---------- */
.tp-drawer-overlay { position: fixed; inset: 0; background: rgba(17, 24, 39, 0.4); z-index: 100; display: flex; justify-content: flex-end; }
.tp-drawer { width: 480px; max-width: 92vw; height: 100%; background: #fff; box-shadow: -4px 0 24px rgba(0, 0, 0, 0.1); display: flex; flex-direction: column; animation: tp-slide-in 0.2s ease-out; }
.tp-drawer-wide { width: 640px; }
@keyframes tp-slide-in { from { transform: translateX(30px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
.tp-drawer-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 24px; border-bottom: 1px solid #E5E7EB; flex-shrink: 0; }
.tp-drawer-header h2 { font-size: 17px; font-weight: 700; margin: 0; color: #1a1a1a; }
.tp-drawer-close { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 8px; border: 1px solid #E5E7EB; background: #fff; color: #6B7280; cursor: pointer; }
.tp-drawer-close:hover { border-color: #FCA5A5; color: #DC2626; }
.tp-drawer-body { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }

/* ---------- 表单 ---------- */
.tp-hint { font-size: 13px; color: #6B7280; margin: 0; line-height: 1.6; }
.tp-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tp-form-row { display: flex; flex-direction: column; gap: 6px; }
.tp-form-label { font-size: 12px; font-weight: 600; color: #374151; }
.tp-textarea, .tp-input, .tp-select { width: 100%; padding: 8px 10px; border: 1px solid #E5E7EB; border-radius: 8px; font-size: 13px; color: #1a1a1a; background: #fff; box-sizing: border-box; font-family: inherit; }
.tp-textarea { resize: vertical; line-height: 1.6; }
.tp-textarea:focus, .tp-input:focus, .tp-select:focus, .tp-pt-input:focus { outline: none; border-color: #2563EB; box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.08); }
.tp-form-actions { display: flex; gap: 8px; }

/* ---------- 拆解预览 ---------- */
.tp-preview-head { display: flex; align-items: baseline; gap: 10px; }
.tp-preview-head h3 { font-size: 14px; font-weight: 700; margin: 0; color: #1a1a1a; }
.tp-preview-title-hint { font-size: 12px; color: #9CA3AF; }
.tp-preview-warnings { display: flex; flex-direction: column; gap: 6px; }
.tp-warning-item { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 8px; font-size: 12px; color: #92400E; }
.tp-warning-item svg { color: #D97706; flex-shrink: 0; }
.tp-preview-table { border: 1px solid #E5E7EB; border-radius: 10px; overflow: hidden; }
.tp-pt-row { display: grid; grid-template-columns: 52px 1fr 1fr; gap: 0; border-bottom: 1px solid #F3F4F6; }
.tp-pt-row:last-child { border-bottom: none; }
.tp-pt-header { background: #F9FAFB; font-size: 11px; font-weight: 600; color: #6B7280; }
.tp-pt-header span { padding: 8px 10px; }
.tp-pt-row:not(.tp-pt-header) span, .tp-pt-row:not(.tp-pt-header) input { padding: 6px 10px; }
.tp-pt-day { display: flex; align-items: center; font-size: 12px; font-weight: 600; color: #2563EB; background: #F8FAFF; }
.tp-pt-input { border: none; font-size: 13px; color: #1a1a1a; background: transparent; min-width: 0; }
.tp-pt-input:focus { background: #fff; }
.tp-pt-topic-input { font-weight: 500; }

/* ---------- 详情 ---------- */
.tp-detail-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.tp-detail-section { display: flex; flex-direction: column; gap: 8px; }
.tp-detail-title { font-size: 14px; font-weight: 700; margin: 0; color: #1a1a1a; }
.tp-pre { margin: 0; padding: 12px 14px; background: #F9FAFB; border: 1px solid #F3F4F6; border-radius: 8px; font-size: 13px; color: #374151; white-space: pre-wrap; word-break: break-word; line-height: 1.7; font-family: inherit; }

/* ---------- 时间线 ---------- */
.tp-timeline { display: flex; flex-direction: column; }
.tp-tl-item { display: flex; gap: 12px; padding: 10px 0 14px; position: relative; }
.tp-tl-item:not(:last-child)::before { content: ''; position: absolute; left: 5px; top: 26px; bottom: -4px; width: 2px; background: #F3F4F6; }
.tp-tl-marker { width: 12px; height: 12px; border-radius: 50%; border: 2px solid #D1D5DB; background: #fff; margin-top: 4px; flex-shrink: 0; }
.tp-tl-published .tp-tl-marker { border-color: #2563EB; background: #2563EB; }
.tp-tl-running .tp-tl-marker { border-color: #2563EB; background: #fff; }
.tp-tl-failed .tp-tl-marker { border-color: #DC2626; background: #DC2626; }
.tp-tl-skipped .tp-tl-marker, .tp-tl-cancelled .tp-tl-marker { border-color: #D1D5DB; background: #E5E7EB; }
.tp-tl-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.tp-tl-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.tp-tl-day { font-size: 13px; font-weight: 700; color: #1a1a1a; }
.tp-tl-time { font-size: 12px; color: #9CA3AF; }
.tp-item-status { font-size: 11px; padding: 1px 8px; border-radius: 999px; }
.tp-item-pending { background: #F3F4F6; color: #6B7280; }
.tp-item-running { background: #EFF6FF; color: #2563EB; }
.tp-item-published { background: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; }
.tp-item-failed { background: #FEF2F2; color: #DC2626; }
.tp-item-skipped { background: #F3F4F6; color: #9CA3AF; }
.tp-item-cancelled { background: #F3F4F6; color: #9CA3AF; }
.tp-tl-topic { font-size: 13px; color: #374151; line-height: 1.5; }
.tp-tl-sub { font-size: 12px; color: #9CA3AF; display: inline-flex; align-items: center; gap: 4px; }
.tp-tl-confirm { color: #D97706; }
.tp-tl-error { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: #DC2626; background: #FEF2F2; border-radius: 6px; padding: 4px 8px; }
.tp-tl-error svg { flex-shrink: 0; }
.tp-tl-link { color: #2563EB; cursor: pointer; font-size: 12px; }
.tp-tl-link:hover { text-decoration: underline; }

@media (max-width: 900px) {
  .tp-metrics-row { grid-template-columns: repeat(2, 1fr); }
  .tp-form-grid { grid-template-columns: 1fr; }
  .tp-plan-card { flex-direction: column; align-items: flex-start; }
}
</style>