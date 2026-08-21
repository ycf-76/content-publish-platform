<template>
  <div class="page-container" id="page-history">
    <div class="mint-hero mint-glass">
      <div>
        <h1 class="font-cal mint-hero-title">工作流历史</h1>
        <p class="mint-hero-sub">查看所有工作流执行记录，点击可在工作台查看</p>
      </div>
      <div style="display:flex; gap:8px; align-items:center;">
        <select class="mint-select" style="width:140px;" v-model="statusFilter" @change="onFilterChange">
          <option value="">全部状态</option>
          <option value="running">执行中</option>
          <option value="suspended">待审核</option>
          <option value="completed">已完成</option>
          <option value="error">出错</option>
          <option value="failed">失败</option>
          <option value="terminated">已终止</option>
          <option value="cancelled">已取消</option>
        </select>
        <button class="mint-btn mint-btn-primary" @click="$emit('new-workflow')" style="white-space:nowrap;">
          <i data-lucide="plus" style="width:16px;height:16px;"></i>
          新建工作流
        </button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="workflowStore.workflowListLoading" class="wf-history-loading">
      <div class="wf-history-spinner"></div>
      <span>加载中...</span>
    </div>

    <!-- 空状态 -->
    <div v-else-if="workflowStore.workflowList.length === 0" class="wf-history-empty">
      <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#CBD5E1" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 6v6l4 2"/>
      </svg>
      <p>暂无工作流记录</p>
      <button class="mint-btn mint-btn-primary" @click="$emit('new-workflow')">
        <i data-lucide="plus" style="width:16px;height:16px;"></i>
        创建第一个工作流
      </button>
    </div>

    <!-- 工作流列表 -->
    <div v-else class="mint-workflow-cards mint-workflow-cards-bento bento-grid bento-grid-4 overflow-y-auto">
      <div
        v-for="wf in workflowStore.workflowList"
        :key="wf.workflow_id"
        class="mint-wf-card wf-history-card"
        :class="{ 'wf-history-card-active': isActive(wf.workflow_id) }"
        @click="onCardClick(wf)"
      >
        <div class="mint-wf-header">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step" :style="{ background: statusColor(wf.status) }">
              <span v-html="statusIcon(wf.status)"></span>
            </div>
            <div style="min-width:0; flex:1;">
              <div class="mint-wf-title" :title="wf.topic">{{ wf.topic || '无主题' }}</div>
              <div class="mint-wf-desc">{{ formatDate(wf.created_at) }} · {{ statusLabel(wf.status) }}</div>
            </div>
          </div>
          <span class="mint-badge" :style="badgeStyle(wf.status)">
            <span class="mint-status-dot" :style="{ background: statusDotColor(wf.status) }"></span>
            {{ statusLabel(wf.status) }}
          </span>
        </div>
        <div style="display:flex; gap:12px; padding:8px 0; flex-wrap:wrap;">
          <div v-if="wf.current_node" style="font-size: 14px; color:#6B7280;">
            <i data-lucide="git-branch" style="width:12px;height:12px;margin-right:4px;"></i>
            {{ nodeLabel(wf.current_node) }}
          </div>
          <div v-if="wf.updated_at" style="font-size: 14px; color:#6B7280;">
            <i data-lucide="clock" style="width:12px;height:12px;margin-right:4px;"></i>
            {{ formatRelativeTime(wf.updated_at) }}
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-ghost" @click.stop="onCardClick(wf)">
            <i data-lucide="external-link" style="width:16px;height:16px;"></i>
            在工作台查看
          </button>
          <button
            v-if="isTerminal(wf.status)"
            class="mint-btn mint-btn-outline"
            @click.stop="$emit('restart-workflow', wf)"
          >
            <i data-lucide="rotate-ccw" style="width:16px;height:16px;"></i>
            重新执行
          </button>
          <button
            class="mint-btn mint-btn-ghost mint-btn-delete"
            @click.stop="confirmDelete(wf)"
          >
            <i data-lucide="trash-2" style="width:16px;height:16px;"></i>
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="workflowStore.workflowListTotal > pageSize" class="wf-history-pagination">
      <span class="wf-history-pagination-info">
        共 {{ workflowStore.workflowListTotal }} 条
      </span>
      <button
        class="mint-btn mint-btn-ghost"
        :disabled="currentOffset === 0"
        @click="prevPage"
      >
        上一页
      </button>
      <span class="wf-history-pagination-page">
        {{ currentPage }} / {{ totalPages }}
      </span>
      <button
        class="mint-btn mint-btn-ghost"
        :disabled="currentOffset + pageSize >= workflowStore.workflowListTotal"
        @click="nextPage"
      >
        下一页
      </button>
    </div>

    <!-- 删除确认对话框 -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="wf-delete-overlay" @click.self="showDeleteConfirm = false">
        <div class="wf-delete-dialog">
          <h3 class="wf-delete-title">确认删除</h3>
          <p class="wf-delete-msg">确定要删除工作流"{{ deleteTarget?.topic || '无主题' }}"吗？此操作不可恢复。</p>
          <div class="wf-delete-actions">
            <button class="mint-btn mint-btn-ghost" @click="showDeleteConfirm = false">取消</button>
            <button class="mint-btn mint-btn-danger" :disabled="deleteLoading" @click="handleDelete">
              {{ deleteLoading ? '删除中...' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onActivated } from 'vue'
import { createIcons, icons } from 'lucide'
import { useWorkflowStore } from '@/stores/workflow'
import { workflowApi } from '@/api/workflow'
import type { WorkflowListItem } from '@/api/workflow'

const emit = defineEmits<{
  'new-workflow': []
  'open-workflow': [workflowId: string]
  'restart-workflow': [wf: WorkflowListItem]
}>()

const props = defineProps<{
  visible?: boolean
}>()

const workflowStore = useWorkflowStore()

const statusFilter = ref('')
const pageSize = 20
const currentOffset = ref(0)

const showDeleteConfirm = ref(false)
const deleteTarget = ref<WorkflowListItem | null>(null)
const deleteLoading = ref(false)

const currentPage = computed(() => Math.floor(currentOffset.value / pageSize) + 1)
const totalPages = computed(() => Math.ceil(workflowStore.workflowListTotal / pageSize) || 1)

function isActive(workflowId: string): boolean {
  return workflowStore.currentWorkflow?.workflow_id === workflowId
}

function isTerminal(status: string): boolean {
  return ['completed', 'error', 'failed', 'terminated', 'cancelled'].includes(status)
}

const STATUS_MAP: Record<string, { label: string; color: string; dotColor: string; badgeBg: string; badgeColor: string }> = {
  running:    { label: '执行中', color: '#3B6CF6', dotColor: '#3B6CF6', badgeBg: '#EFF6FF', badgeColor: '#1E40AF' },
  suspended:  { label: '待审核', color: '#F59E0B', dotColor: '#F59E0B', badgeBg: '#FFFBEB', badgeColor: '#92400E' },
  completed:  { label: '已完成', color: '#10B981', dotColor: '#059669', badgeBg: '#ECFDF5', badgeColor: '#065F46' },
  error:      { label: '出错',   color: '#EF4444', dotColor: '#EF4444', badgeBg: '#FEF2F2', badgeColor: '#991B1B' },
  failed:     { label: '失败',   color: '#EF4444', dotColor: '#EF4444', badgeBg: '#FEF2F2', badgeColor: '#991B1B' },
  terminated: { label: '已终止', color: '#EF4444', dotColor: '#EF4444', badgeBg: '#FEF2F2', badgeColor: '#991B1B' },
  cancelled:  { label: '已取消', color: '#9CA3AF', dotColor: '#9CA3AF', badgeBg: '#F3F4F6', badgeColor: '#6B7280' },
}

function statusLabel(status: string): string {
  return STATUS_MAP[status]?.label || status
}

function statusColor(status: string): string {
  return STATUS_MAP[status]?.color || '#9CA3AF'
}

function statusDotColor(status: string): string {
  return STATUS_MAP[status]?.dotColor || '#9CA3AF'
}

function badgeStyle(status: string): Record<string, string> {
  const m = STATUS_MAP[status]
  return {
    background: m?.badgeBg || '#F3F4F6',
    color: m?.badgeColor || '#6B7280',
  }
}

function statusIcon(status: string): string {
  switch (status) {
    case 'running': return '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation:spin 1s linear infinite;"><path d="M12 2v4"/><path d="M12 18v4"/><path d="m4.93 4.93 2.83 2.83"/><path d="m16.24 16.24 2.83 2.83"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="m4.93 19.07 2.83-2.83"/><path d="m16.24 7.76 2.83-2.83"/></svg>'
    case 'suspended': return '审'
    case 'completed': return '✓'
    case 'error':
    case 'failed': return '✕'
    case 'terminated': return '✕'
    case 'cancelled': return '—'
    default: return '?'
  }
}

const NODE_LABELS: Record<string, string> = {
  search: '搜索',
  analyze: '分析',
  copywrite: '文案',
  image_plan: '图片规划',
  image_gen: '图片生成',
  image_review: '图片审核',
  audit: '合规审核',
  final_review: '终审',
  publish: '发布',
}

function nodeLabel(nodeId: string): string {
  return NODE_LABELS[nodeId] || nodeId
}

function formatDate(isoStr: string): string {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return isoStr
  }
}

function formatRelativeTime(isoStr: string | null): string {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    const now = Date.now()
    const diff = now - d.getTime()
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
    return `${Math.floor(diff / 86400000)} 天前`
  } catch {
    return ''
  }
}

async function loadList() {
  await workflowStore.loadWorkflowList({
    status: statusFilter.value || undefined,
    limit: pageSize,
    offset: currentOffset.value,
  })
  nextTick(() => createIcons({ icons }))
}

function onFilterChange() {
  currentOffset.value = 0
  loadList()
}

function prevPage() {
  if (currentOffset.value >= pageSize) {
    currentOffset.value -= pageSize
    loadList()
  }
}

function nextPage() {
  if (currentOffset.value + pageSize < workflowStore.workflowListTotal) {
    currentOffset.value += pageSize
    loadList()
  }
}

async function onCardClick(wf: WorkflowListItem) {
  emit('open-workflow', wf.workflow_id)
}

function confirmDelete(wf: WorkflowListItem) {
  deleteTarget.value = wf
  showDeleteConfirm.value = true
}

async function handleDelete() {
  if (!deleteTarget.value) return
  deleteLoading.value = true
  try {
    await workflowApi.delete(deleteTarget.value.workflow_id)
    showDeleteConfirm.value = false
    deleteTarget.value = null
    await loadList()
  } catch (err: any) {
    console.error('删除工作流失败:', err)
    alert(err?.message || '删除失败，请重试')
  } finally {
    deleteLoading.value = false
  }
}

onMounted(() => {
  loadList()
})

watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadList()
  }
})

watch(() => workflowStore.workflowList, () => {
  nextTick(() => createIcons({ icons }))
}, { deep: true })
</script>

<style scoped>
.wf-history-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 0;
  color: #9CA3AF;
  font-size: 15px;
}

.wf-history-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #E5E7EB;
  border-top-color: #3B6CF6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.wf-history-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 80px 0;
  color: #9CA3AF;
  font-size: 16px;
}

.wf-history-card {
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.15s ease;
}

.wf-history-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
  transform: translateY(-2px);
}

.wf-history-card-active {
  border: 2px solid #3B6CF6;
  box-shadow: 0 0 0 3px rgba(59, 108, 246, 0.15);
}

.wf-history-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px 0 8px;
  font-size: 14px;
  color: #6B7280;
}

.wf-history-pagination-info {
  margin-right: 8px;
}

.wf-history-pagination-page {
  min-width: 60px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.mint-btn-delete {
  color: #EF4444;
  margin-left: auto;
}

.mint-btn-delete:hover {
  color: #DC2626;
  background: #FEF2F2;
}

.mint-btn-danger {
  background: #EF4444;
  color: #fff;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.mint-btn-danger:hover {
  background: #DC2626;
}

.mint-btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.wf-delete-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.wf-delete-dialog {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  width: 380px;
  max-width: 90vw;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.wf-delete-title {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.wf-delete-msg {
  margin: 0 0 20px;
  font-size: 14px;
  color: #6B7280;
  line-height: 1.5;
}

.wf-delete-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>