<template>
  <div class="dsh-tc-wrap">
    <!-- 极简状态行 -->
    <div class="dsh-tc-status-bar" @click="detailOpen = !detailOpen">
      <div class="dsh-tc-status-left">
        <Loader2 v-if="isAnyRunning" :size="14" :stroke-width="2" class="dsh-tc-spin" />
        <CheckCircle2 v-else-if="!hasAnyError" :size="14" :stroke-width="2" class="dsh-tc-ok" />
        <AlertCircle v-else :size="14" :stroke-width="2" class="dsh-tc-warn" />
        <span class="dsh-tc-status-text">{{ statusText }}</span>
      </div>
      <div class="dsh-tc-status-right">
        <span v-if="totalDurationMs" class="dsh-tc-total-dur">{{ formatDuration(totalDurationMs) }}</span>
        <ChevronDown :size="13" class="dsh-tc-toggle" :class="{ 'dsh-tc-toggle-open': detailOpen }" />
      </div>
    </div>

    <!-- 折叠详情 -->
    <Transition name="dsh-slide">
      <div v-if="detailOpen" class="dsh-tc-detail-panel">
        <!-- 子智能体分组 -->
        <div v-for="group in subAgentGroups" :key="group.subAgentId" class="dsh-tc-sub-section">
          <div class="dsh-tc-sub-label">
            <span class="dsh-tc-sub-dot" :class="group.isRunning ? 'dsh-tc-sub-dot--run' : group.hasError ? 'dsh-tc-sub-dot--err' : 'dsh-tc-sub-dot--ok'"></span>
            <span>{{ group.displayName }}</span>
            <span class="dsh-tc-sub-hint">{{ group.items.length }}步 · {{ group.shortId }}</span>
          </div>
          <div v-for="tc in group.items" :key="tc.id" class="dsh-tc-step">
            <component :is="statusIcon(tc).icon" :size="12" :stroke-width="1.5" class="dsh-tc-step-si" :class="'dsh-tc-step-si--'+(tc.status||'pending')" />
            <span class="dsh-tc-step-name">{{ toolLabel(tc) }}</span>
            <span v-if="tc.durationMs" class="dsh-tc-step-dur">{{ formatDuration(tc.durationMs) }}</span>
          </div>
        </div>

        <!-- 父 Agent 工具 -->
        <div v-if="parentCalls.length" class="dsh-tc-sub-section">
          <div class="dsh-tc-sub-label">
            <span class="dsh-tc-sub-dot dsh-tc-sub-dot--ok"></span>
            <span>主流程</span>
          </div>
          <div v-for="tc in parentCalls" :key="tc.id" class="dsh-tc-step">
            <component :is="statusIcon(tc).icon" :size="12" :stroke-width="1.5" class="dsh-tc-step-si" :class="'dsh-tc-step-si--'+(tc.status||'pending')" />
            <span class="dsh-tc-step-name">{{ toolLabel(tc) }}</span>
            <span v-if="tc.durationMs" class="dsh-tc-step-dur">{{ formatDuration(tc.durationMs) }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  CircleDot,
  XCircle,
  ChevronDown,
} from 'lucide-vue-next'
import { getToolDisplayLabel } from './cell-types'
import type { ToolCall } from './cell-types'

const props = defineProps<{
  toolCalls: ToolCall[]
  msgIdx: number
}>()

const detailOpen = ref(false)

interface SubGroup {
  subAgentId: string; shortId: string; displayName: string
  items: ToolCall[]; hasError: boolean; isRunning: boolean
}

const isAnyRunning = computed(() => props.toolCalls.some(t => t.status === 'running'))
const hasAnyError = computed(() => props.toolCalls.some(t => t.status === 'error'))
const allDone = computed(() => props.toolCalls.length > 0 && props.toolCalls.every(t => t.status === 'done' || t.status === 'error'))

const parentCalls = computed(() => props.toolCalls.filter(t => !t.subAgentId))

const subAgentGroups = computed<SubGroup[]>(() => {
  const map = new Map<string, SubGroup>()
  for (const tc of props.toolCalls) {
    if (!tc.subAgentId) continue
    let g = map.get(tc.subAgentId)
    if (!g) {
      g = { subAgentId: tc.subAgentId, shortId: tc.subAgentId.slice(0, 6), displayName: inferName(tc), items: [], hasError: false, isRunning: false }
      map.set(tc.subAgentId, g)
    }
    g.items.push(tc)
    if (tc.status === 'error') g.hasError = true
    if (tc.status === 'running') g.isRunning = true
  }
  return [...map.values()]
})

const statusText = computed(() => {
  if (isAnyRunning.value) {
    const runningNames = subAgentGroups.value.filter(g => g.isRunning).map(g => g.displayName)
    const parentRunning = parentCalls.value.filter(t => t.status === 'running')
    if (runningNames.length >= 2) {
      return `正在并行处理${runningNames.join('与')}任务…`
    }
    if (runningNames.length === 1) {
      return `正在${runningNames[0]}…`
    }
    if (parentRunning.length) {
      const names = parentRunning.map(t => friendlyToolName(t.name))
      return `正在${names.join('、')}…`
    }
    return '正在处理…'
  }

  if (hasAnyError.value) {
    const errGroups = subAgentGroups.value.filter(g => g.hasError)
    const okGroups = subAgentGroups.value.filter(g => !g.hasError && g.items.length > 0)
    if (errGroups.length && okGroups.length) {
      const errWhat = errGroups.map(g => g.displayName).join('、')
      const okWhat = okGroups.map(g => g.displayName).join('与')
      return `${errWhat}遇到问题，已跳过，正在为你${okWhat}…`
    }
    return '部分步骤遇到问题，已自动处理'
  }

  if (allDone.value) {
    const subCount = subAgentGroups.value.length
    if (subCount >= 2) return `已完成 ${subCount} 项并行任务`
    if (subCount === 1) return `已完成：${subAgentGroups.value[0].displayName}`
    return '处理完成'
  }

  return '准备中…'
})

const totalDurationMs = computed(() => {
  let total = 0
  for (const t of props.toolCalls) {
    if (t.durationMs) total += t.durationMs
  }
  return total || 0
})

function statusIcon(tc: ToolCall) {
  switch (tc.status) {
    case 'running': return { icon: Loader2 }
    case 'done': return { icon: CheckCircle2 }
    case 'error': return { icon: XCircle }
    default: return { icon: CircleDot }
  }
}

function toolLabel(tc: ToolCall): string {
  if (tc.name === 'spawn_agent') {
    const n = tc.arguments?.task_name || tc.arguments?.name || ''
    return n ? `派发「${n}」` : '派发子智能体'
  }
  if (tc.name === 'wait_agent') return '等待完成'
  return getToolDisplayLabel(tc.name).label || tc.name
}

function friendlyToolName(name: string): string {
  const m: Record<string, string> = {
    spawn_agent: '规划任务', wait_agent: '等待结果',
    xhs_search: '搜索热点', trending_search: '搜索趋势',
    write_copy: '撰写文案', generate_copywriting: '生成文案',
    create_image: '生成图片', generate_image: '生成图片',
    publish_content: '发布内容', analyze_competitor: '竞品分析',
  }
  return m[name] || name
}

function inferName(tc: ToolCall): string {
  const m: Record<string, string> = {
    xhs_search: '搜索热点', trending_search: '搜索热点',
    write_copy: '撰写文案', generate_copywriting: '撰写文案',
    create_image: '生成图片', generate_image: '生成图片',
    publish_content: '发布内容', analyze_competitor: '竞品分析',
  }
  return m[tc.name] || '子智能体'
}

function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}
</script>

<style scoped>
.dsh-tc-wrap { margin: 2px 0; }

/* ── 状态行 ── */
.dsh-tc-status-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px; border-radius: 8px;
  cursor: pointer; user-select: none;
  transition: background .12s;
}
.dsh-tc-status-bar:hover { background: rgba(0,0,0,.025); }

.dsh-tc-status-left { display: flex; align-items: center; gap: 7px; }
.dsh-tc-status-right { display: flex; align-items: center; gap: 6px; }

.dsh-tc-spin { color: #94a3b8; animation: dsh-rot .8s linear infinite; }
.dsh-tc-ok { color: #94a3b8; }
.dsh-tc-warn { color: #f59e0b; }

@keyframes dsh-rot { to { transform: rotate(360deg); } }

.dsh-tc-status-text {
  font-size: 12.5px; color: #64748b; line-height: 1.4;
}

.dsh-tc-total-dur {
  font-size: 11px; color: #94a3b8; font-variant-numeric: tabular-nums;
}

.dsh-tc-toggle {
  color: #cbd5e1; transition: transform .2s;
}
.dsh-tc-toggle-open { transform: rotate(180deg); }

/* ── 详情面板 ── */
.dsh-tc-detail-panel {
  padding: 6px 10px 8px 28px;
  border-left: 2px solid rgba(0,0,0,.06);
  margin-left: 16px;
}

.dsh-tc-sub-section { margin-bottom: 8px; }
.dsh-tc-sub-section:last-child { margin-bottom: 0; }

.dsh-tc-sub-label {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: #94a3b8; margin-bottom: 3px;
}

.dsh-tc-sub-dot {
  width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
}
.dsh-tc-sub-dot--ok { background: #22c55e; }
.dsh-tc-sub-dot--run { background: #f59e0b; animation: dsh-pulse 1.2s infinite; }
.dsh-tc-sub-dot--err { background: #ef4444; }

@keyframes dsh-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

.dsh-tc-sub-hint { opacity: .6; }

.dsh-tc-step {
  display: flex; align-items: center; gap: 6px;
  padding: 2px 0 2px 11px; font-size: 12px; color: #64748b;
}
.dsh-tc-step-si { flex-shrink: 0; }
.dsh-tc-step-si--done { color: #22c55e; }
.dsh-tc-step-si--running { color: #f59e0b; animation: dsh-rot .8s linear infinite; }
.dsh-tc-step-si--error { color: #ef4444; }
.dsh-tc-step-si--pending { color: #cbd5e1; }

.dsh-tc-step-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dsh-tc-step-dur { font-size: 10px; color: #94a3b8; font-variant-numeric: tabular-nums; flex-shrink: 0; }

/* ── 动画 ── */
.dsh-slide-enter-active { transition: all .2s ease; }
.dsh-slide-leave-active { transition: all .15s ease; }
.dsh-slide-enter-from, .dsh-slide-leave-to { opacity: 0; max-height: 0; }
.dsh-slide-enter-to, .dsh-slide-leave-from { max-height: 500px; }

/* ── 暗色 ── */
:global(.dsh-chat.is-dark) .dsh-tc-status-bar:hover { background: rgba(255,255,255,.03); }
:global(.dsh-chat.is-dark) .dsh-tc-status-text { color: #94a3b8; }
:global(.dsh-chat.is-dark) .dsh-tc-total-dur { color: #475569; }
:global(.dsh-chat.is-dark) .dsh-tc-toggle { color: #334155; }
:global(.dsh-chat.is-dark) .dsh-tc-detail-panel { border-left-color: rgba(255,255,255,.06); }
:global(.dsh-chat.is-dark) .dsh-tc-sub-label { color: #64748b; }
:global(.dsh-chat.is-dark) .dsh-tc-step { color: #94a3b8; }
:global(.dsh-chat.is-dark) .dsh-tc-step-dur { color: #475569; }
</style>