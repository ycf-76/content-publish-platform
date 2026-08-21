<template>
  <div class="mint-shell we-shell" :class="{ 'mint-collapsed': isSidebarCollapsed, 'settings-blur': showSettings }">
    <SidebarNav
      current-page="workflow-templates"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @go-eco="goEco"
      @open-settings="openSettings"
    />

    <main class="mint-main we-page">
      <div class="mint-content-card-wrapper">
        <div class="mint-content-card we-content-card">
          <div class="we-topbar">
            <div class="we-title-group">
              <button class="mint-icon-btn" @click="goBack" title="返回">
                <i data-lucide="arrow-left"></i>
              </button>
              <div>
                <div class="we-kicker">
                  <i data-lucide="git-branch"></i>
                  Visual Flow Builder
                </div>
                <h1>{{ definitionName }}</h1>
              </div>
            </div>
            <div class="we-top-actions">
              <button v-if="activeWorkflowId" class="mint-btn mint-btn-outline" @click="showRunPanel = !showRunPanel">
                <i data-lucide="activity"></i>
                执行进度
                <span v-if="workflowStatus" class="we-status-dot" :class="`we-dot-${workflowStatus}`"></span>
              </button>
              <button class="mint-btn mint-btn-outline" @click="showHelp = true">
                <i data-lucide="help-circle"></i>
                帮助
              </button>
              <button class="mint-btn mint-btn-primary" @click="toggleFullscreen">
                <i :data-lucide="isFullscreen ? 'minimize-2' : 'maximize-2'"></i>
                {{ isFullscreen ? '退出全屏' : '全屏' }}
              </button>
            </div>
          </div>

          <div class="we-editor-area" :class="{ fullscreen: isFullscreen, 'with-panel': showRunPanel && activeWorkflowId }">
            <div class="we-editor">
              <WorkflowEditor
                ref="editorRef"
                :definition-id="definitionId"
                @saved="onSaved"
                @run="onRun"
                @fullscreen="isFullscreen = $event"
              />
            </div>

            <!-- 执行进度面板 -->
            <transition name="we-slide">
              <div v-if="showRunPanel && activeWorkflowId" class="we-run-panel">
                <div class="we-run-panel-header">
                  <div class="we-run-panel-title">
                    <i data-lucide="play-circle"></i>
                    <span>执行进度</span>
                  </div>
                  <button class="mint-icon-btn" @click="showRunPanel = false"><i data-lucide="x"></i></button>
                </div>

                <div class="we-run-status-bar">
                  <span class="we-run-status-label">状态</span>
                  <span class="we-run-status-value" :class="`we-status-${workflowStatus}`">
                    {{ statusLabel(workflowStatus) }}
                  </span>
                  <span class="we-run-progress-pct">{{ workflowProgress }}%</span>
                </div>

                <div class="we-run-progress-bar">
                  <div class="we-run-progress-fill" :style="{ width: workflowProgress + '%' }"></div>
                </div>

                <div class="we-run-nodes">
                  <div v-for="node in workflowNodes" :key="node.node_id" class="we-run-node" :class="`we-node-${node.status}`">
                    <span class="we-run-node-dot"></span>
                    <span class="we-run-node-name">{{ nodeName(node) }}</span>
                    <span class="we-run-node-status">{{ nodeStatusLabel(node.status) }}</span>
                  </div>
                  <div v-if="workflowNodes.length === 0" class="we-run-empty">暂无节点数据</div>
                </div>

                <div class="we-run-actions">
                  <button v-if="workflowStatus === 'running'" class="mint-btn mint-btn-outline" @click="controlWorkflow('pause')">
                    <i data-lucide="pause"></i> 暂停
                  </button>
                  <button v-if="workflowStatus === 'paused'" class="mint-btn mint-btn-primary" @click="controlWorkflow('resume')">
                    <i data-lucide="play"></i> 继续
                  </button>
                  <button v-if="['running', 'paused'].includes(workflowStatus)" class="mint-btn mint-btn-outline" style="color:#dc2626;border-color:#dc2626" @click="controlWorkflow('terminate')">
                    <i data-lucide="square"></i> 终止
                  </button>
                </div>
              </div>
            </transition>
          </div>
        </div>
      </div>
    </main>

    <div v-if="showHelp" class="we-modal-overlay" @click.self="showHelp = false">
      <div class="we-modal">
        <div class="we-modal-header">
          <h3>可视化编辑器</h3>
          <button class="mint-icon-btn" @click="showHelp = false"><i data-lucide="x"></i></button>
        </div>
        <div class="we-modal-body">
          <div class="we-help-grid">
            <div><strong>添加节点</strong><span>从左侧节点库拖拽到画布。</span></div>
            <div><strong>连接节点</strong><span>从右侧圆点拖到下一个节点左侧。</span></div>
            <div><strong>保存运行</strong><span>先保存，再运行，点击"执行进度"查看结果。</span></div>
            <div><strong>快捷操作</strong><span>Delete 删除，Ctrl+S 保存，F1 帮助。</span></div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="runWorkflowId && !showRunPanel" class="we-run-toast">
      <i data-lucide="check-circle"></i>
      <span>工作流已启动</span>
      <button class="mint-btn mint-btn-primary" @click="openRunPanel(runWorkflowId)">查看进度</button>
    </div>

    <SettingsView v-if="showSettings" @close="showSettings = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createIcons, icons } from 'lucide'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import SettingsView from '@/views/SettingsView.vue'
import WorkflowEditor from '@/components/workflow/WorkflowEditor.vue'
import workflowDefinitionsApi from '@/api/workflowDefinitions'
import { workflowApi } from '@/api/workflow'
import { useUIState } from '@/composables/useUIState'

const route = useRoute()
const router = useRouter()

const showSettings = ref(false)
function openSettings() {
  showSettings.value = true
}
const { isSidebarCollapsed, toggleSidebar } = useUIState()

const editorRef = ref<InstanceType<typeof WorkflowEditor> | null>(null)
const showHelp = ref(false)
const isFullscreen = ref(false)
const runWorkflowId = ref<string | null>(null)
const definitionName = ref('新工作流')

const definitionId = computed(() => route.query.id as string | undefined)
const activeWorkflowId = computed(() => (route.query.workflow as string) || runWorkflowId.value)

// 执行进度面板
const showRunPanel = ref(false)
const workflowStatus = ref<string>('')
const workflowProgress = ref(0)
const workflowNodes = ref<any[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const STATUS_MAP: Record<string, string> = {
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
  failed: '失败',
  terminated: '已终止',
  error: '错误',
  pending: '等待中',
  started: '已启动',
}

const NODE_STATUS_MAP: Record<string, string> = {
  idle: '等待',
  pending: '排队',
  running: '运行中',
  completed: '完成',
  passed: '通过',
  rejected: '驳回',
  awaiting_review: '待审核',
  error: '错误',
  suspended: '挂起',
  terminated: '终止',
}

const NODE_NAME_MAP: Record<string, string> = {
  search: '搜索素材',
  analyze: '分析选题',
  copywrite: '文案创作',
  image_plan: '图片规划',
  image_gen: '图片生成',
  image_review: '图片审核',
  audit: '内容审核',
  final_review: '终审',
  publish: '发布',
}

function statusLabel(s: string) { return STATUS_MAP[s] || s || '--' }
function nodeStatusLabel(s: string) { return NODE_STATUS_MAP[s] || s || '--' }
function nodeName(node: any) { return node.node_type && node.node_type !== node.node_id ? node.node_type : (NODE_NAME_MAP[node.node_id] || node.node_id) }

async function pollWorkflowStatus() {
  const wfId = activeWorkflowId.value
  if (!wfId) return
  try {
    const [detailRes, nodesRes] = await Promise.all([
      workflowApi.getDetail(wfId),
      workflowApi.getNodes(wfId),
    ])
    const detail = (detailRes as any)?.data ?? detailRes
    workflowStatus.value = detail?.status || ''

    const nodesData = (nodesRes as any)?.data ?? nodesRes
    workflowNodes.value = nodesData?.nodes || []

    const totalNodes = workflowNodes.value.length
    if (totalNodes > 0) {
      const doneCount = workflowNodes.value.filter(n => ['completed', 'passed'].includes(n.status)).length
      workflowProgress.value = Math.round((doneCount / totalNodes) * 100)
    } else {
      workflowProgress.value = detail?.progress || 0
    }

    if (['completed', 'failed', 'terminated', 'error'].includes(workflowStatus.value)) {
      stopPolling()
    }
  } catch (e) {
    console.warn('[WorkflowEditorView] poll error:', e)
  }
}

function startPolling() {
  stopPolling()
  pollWorkflowStatus()
  pollTimer = setInterval(pollWorkflowStatus, 3000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function openRunPanel(workflowId: string) {
  runWorkflowId.value = workflowId
  showRunPanel.value = true
  startPolling()
}

async function controlWorkflow(action: 'pause' | 'resume' | 'terminate') {
  const wfId = activeWorkflowId.value
  if (!wfId) return
  try {
    if (action === 'pause') await workflowApi.pause(wfId)
    else if (action === 'resume') await workflowApi.resume(wfId)
    else if (action === 'terminate') await workflowApi.terminate?.(wfId)
    await pollWorkflowStatus()
  } catch (e: any) {
    console.error(`[WorkflowEditorView] ${action} failed:`, e)
  }
}

watch(activeWorkflowId, (newId) => {
  if (newId && showRunPanel.value) startPolling()
  else if (!newId) stopPolling()
})

function handleNavClick(pageName: string) {
  if (pageName === 'workflow-templates') return
  router.push({ path: '/workbench', query: pageName === 'workflow' ? {} : { page: pageName } })
}

function goToEco() {
  router.push('/eco')
}

function goBack() {
  router.push('/workflow-templates')
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.()
    isFullscreen.value = true
  } else {
    document.exitFullscreen?.()
    isFullscreen.value = false
  }
}

function onSaved(savedDefinitionId: string) {
  if (route.query.id !== savedDefinitionId) {
    router.replace({ query: { id: savedDefinitionId } })
  }
}

function onRun(workflowId: string) {
  runWorkflowId.value = workflowId
  showRunPanel.value = true
  startPolling()
}

function goToWorkbench(workflowId: string) {
  openRunPanel(workflowId)
}

async function loadDefinitionName() {
  if (!definitionId.value) return
  try {
    const defn = await workflowDefinitionsApi.getWorkflowDefinition(definitionId.value)
    definitionName.value = defn.name
  } catch {
    definitionName.value = '未找到工作流'
  }
}

function loadTemplateInitData() {
  const raw = sessionStorage.getItem('workflow-editor-init')
  if (!raw) return
  try {
    const templateData = JSON.parse(raw)
    sessionStorage.removeItem('workflow-editor-init')
    nextTick(() => {
      const editor = editorRef.value as any
      if (editor?.loadFromTemplateData) editor.loadFromTemplateData(templateData)
      definitionName.value = templateData.name || '新工作流'
    })
  } catch (error) {
    console.error('[WorkflowEditorView] parse template data failed:', error)
  }
}

function handleKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key === 's') {
    event.preventDefault()
    ;(editorRef.value as any)?.saveWorkflow()
  }
  if (event.key === 'F1') {
    event.preventDefault()
    showHelp.value = true
  }
  if (event.key === 'Escape' && isFullscreen.value) {
    toggleFullscreen()
  }
}

onMounted(async () => {
  await loadDefinitionName()
  loadTemplateInitData()
  window.addEventListener('keydown', handleKeydown)

  if (route.query.workflow) {
    showRunPanel.value = true
    startPolling()
  }

  nextTick(() => createIcons({ icons }))
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  stopPolling()
})
</script>

<style scoped>
.we-shell {
  grid-template-columns: auto minmax(0, 1fr) !important;
}

.we-page {
  min-width: 0;
  min-height: 0;
}

.we-content-card {
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

.we-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 20px;
  border-bottom: 1px solid #ededed;
  flex-shrink: 0;
}

.we-title-group {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.we-kicker {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #ff2442;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.we-kicker svg { width: 13px; height: 13px; }

.we-topbar h1 {
  margin: 2px 0 0;
  color: #1a1a1a;
  font-size: 20px;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.we-top-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.we-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: 4px;
  vertical-align: middle;
}
.we-dot-running, .we-dot-started { background: #10b981; animation: we-pulse 1.5s infinite; }
.we-dot-paused { background: #f59e0b; }
.we-dot-completed { background: #059669; }
.we-dot-failed, .we-dot-error, .we-dot-terminated { background: #dc2626; }
@keyframes we-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.we-editor-area {
  position: relative;
  flex: 1;
  min-height: 500px;
  overflow: hidden;
  display: flex;
}

.we-editor-area.fullscreen {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: #fff;
}

.we-editor {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.we-editor-area.with-panel .we-editor {
  flex: 1;
}

/* ===== 执行进度面板 ===== */
.we-run-panel {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #e5e7eb;
  background: #fafafa;
  overflow-y: auto;
}

.we-run-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.we-run-panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
}

.we-run-panel-title svg { width: 16px; height: 16px; color: #ff2442; }

.we-run-status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #f3f4f6;
}

.we-run-status-label {
  font-size: 12px;
  color: #6b7280;
}

.we-run-status-value {
  font-size: 13px;
  font-weight: 600;
}

.we-status-running, .we-status-started { color: #10b981; }
.we-status-paused { color: #f59e0b; }
.we-status-completed { color: #059669; }
.we-status-failed, .we-status-error, .we-status-terminated { color: #dc2626; }

.we-run-progress-pct {
  margin-left: auto;
  font-size: 12px;
  color: #6b7280;
  font-variant-numeric: tabular-nums;
}

.we-run-progress-bar {
  margin: 0 16px 12px;
  height: 4px;
  background: #e5e7eb;
  border-radius: 2px;
  overflow: hidden;
}

.we-run-progress-fill {
  height: 100%;
  background: #ff2442;
  border-radius: 2px;
  transition: width 0.5s ease;
}

.we-run-nodes {
  flex: 1;
  padding: 8px 16px;
  overflow-y: auto;
}

.we-run-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 4px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #e5e7eb;
  font-size: 13px;
}

.we-run-node-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #d1d5db;
}

.we-node-idle .we-run-node-dot { background: #d1d5db; }
.we-node-pending .we-run-node-dot { background: #f59e0b; }
.we-node-running .we-run-node-dot { background: #10b981; animation: we-pulse 1.5s infinite; }
.we-node-completed .we-run-node-dot,
.we-node-passed .we-run-node-dot { background: #059669; }
.we-node-error .we-run-node-dot,
.we-node-failed .we-run-node-dot,
.we-node-terminated .we-run-node-dot { background: #dc2626; }
.we-node-awaiting_review .we-run-node-dot { background: #8b5cf6; }
.we-node-rejected .we-run-node-dot { background: #dc2626; }
.we-node-suspended .we-run-node-dot { background: #f59e0b; }

.we-run-node-name {
  flex: 1;
  color: #1a1a1a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.we-run-node-status {
  font-size: 11px;
  color: #6b7280;
  flex-shrink: 0;
}

.we-run-empty {
  text-align: center;
  padding: 24px 0;
  color: #9ca3af;
  font-size: 13px;
}

.we-run-actions {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #e5e7eb;
}

.we-run-actions .mint-btn {
  flex: 1;
  justify-content: center;
}

/* slide transition */
.we-slide-enter-active,
.we-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.we-slide-enter-from,
.we-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.we-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.35);
}

.we-modal {
  width: min(520px, 100%);
  max-height: 85vh;
  overflow: auto;
  background: #fff;
  border: 1px solid #ededed;
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.16);
}

.we-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #f3f4f6;
}

.we-modal-header h3 { margin: 0; color: #1a1a1a; font-size: 16px; }
.we-modal-body { padding: 20px; }

.we-help-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.we-help-grid > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: #fafafa;
  border: 1px solid #ededed;
  border-radius: 8px;
}

.we-help-grid strong { color: #1a1a1a; font-size: 13px; }
.we-help-grid span { color: #6b7280; font-size: 12px; line-height: 1.5; }

.we-run-toast {
  position: fixed;
  top: 76px;
  right: 28px;
  z-index: 1100;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 10px 14px;
  background: #059669;
  color: #fff;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(5, 150, 105, 0.24);
  font-size: 13px;
}

.we-run-toast svg { width: 17px; height: 17px; }

@media (max-width: 760px) {
  .we-help-grid { grid-template-columns: 1fr; }
  .we-run-panel { width: 260px; }
}
</style>