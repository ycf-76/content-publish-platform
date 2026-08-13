<template>
  <div class="mint-wf-card wf-node-card wf-node-search" id="card-search" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">01</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="search" class="wf-node-icon"></i>
            搜索热点
            <code class="wf-node-key">search</code>
          </div>

        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>

    <div class="wf-node-body">
      <div class="wf-search-input-row">
        <input
          type="text"
          class="mint-input"
          placeholder="输入关键词，回车或点击搜索启动工作流..."
          v-model="keyword"
          :disabled="workflowStore.isStreaming || workflowStore.isLoading"
          @keydown.enter="$emit('start-flow')"
        >
        <button class="mint-btn mint-btn-primary" :disabled="workflowStore.isStreaming || workflowStore.isLoading" @click="$emit('start-flow')">
          <i data-lucide="play" style="width:14px; height:14px;"></i>
          {{ workflowStore.isStreaming ? '执行中...' : '启动工作流' }}
        </button>
      </div>

      <!-- 平台选择器 -->
      <div class="wf-platform-selector">
        <span class="wf-platform-label">
          <i data-lucide="globe" style="width:12px; height:12px;"></i>
          数据源
        </span>
        <button
          v-for="p in searchPlatforms"
          :key="p.name || 'all'"
          class="wf-platform-chip"
          :class="{ 'is-active': selectedPlatform === p.name }"
          :title="p.desc"
          :disabled="workflowStore.isStreaming || workflowStore.isLoading"
          @click="$emit('select-platform', p.name)"
        >
          {{ p.label }}
        </button>
      </div>

      <!-- 搜索结果区 -->
      <div class="search-results">
        <div v-if="searchStatus === 'idle'" class="wf-empty-hint">
          <i data-lucide="info" style="width:14px; height:14px;"></i>
          输入关键词并启动，将顺序执行 8 个节点
        </div>

        <div v-else-if="searchStatus === 'loading'" class="mint-search-loading">
          <div class="mint-loader">
            <div class="mint-loader-ball"></div>
          </div>
          <div class="mint-search-loading-text">正在搜索热门内容...</div>
        </div>

        <div v-else-if="searchStatus === 'error'" class="mint-search-error">
          <i data-lucide="alert-circle" style="width:20px; height:20px;"></i>
          <span>{{ searchError }}</span>
        </div>

        <div v-else-if="searchStatus === 'completed' && searchResults.length === 0" class="mint-search-empty">
          未搜到相关笔记，请换个关键词试试
        </div>
        <div v-else-if="searchStatus === 'completed'" class="mint-search-grid">
          <div
            v-for="(note, i) in searchResults"
            :key="i"
            class="mint-note-card"
            :style="{ animation: `resultSlideIn 0.4s ease ${i * 60}ms both` }"
          >
            <div class="mint-note-cover">
              <img
                v-if="note.cover_img"
                :src="coverSrc(note.cover_img)"
                :alt="note.title"
                loading="lazy"
                referrerpolicy="no-referrer"
                @error="onCoverError($event, note)"
              />
              <div
                v-else
                class="mint-note-cover-letter"
                :style="{ background: letterColor(note.platform).bg, color: letterColor(note.platform).fg }"
              >
                <span class="mint-note-cover-letter-text">{{ letterLabel(note) }}</span>
              </div>
            </div>
            <div class="mint-note-body">
              <a v-if="note.url" :href="note.url" target="_blank" rel="noopener" class="mint-note-title-link">
                <div class="mint-note-title">{{ note.title || '无标题' }}</div>
              </a>
              <div v-else class="mint-note-title">{{ note.title || '无标题' }}</div>
              <div v-if="note.summary" class="mint-note-summary">{{ note.summary }}</div>
              <div class="mint-note-meta">
                <span v-if="note.author" class="mint-note-author">
                  <i data-lucide="user" style="width:12px; height:12px;"></i>{{ note.author }}
                </span>
                <span class="mint-note-likes">
                  <i data-lucide="heart" style="width:12px; height:12px;"></i>{{ note.likes || 0 }}
                </span>
                <div class="mint-note-actions">
                  <button class="mint-note-action-btn mint-note-action-analyze" @click.stop="$emit('start-from-result', note)" title="以此内容为参考发起工作流分析">
                    <i data-lucide="zap" style="width:11px; height:11px;"></i>
                    发起分析
                  </button>
                  <button class="mint-note-action-btn mint-note-action-search" @click.stop="$emit('search-similar', note.title || note.summary || '')" title="搜索同类内容">
                    <i data-lucide="search" style="width:11px; height:11px;"></i>
                    搜索同款
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="wf-node-bottom-row" v-if="nodeMeta || searchStatus === 'completed' || searchStatus === 'error' || workflowStore.isStreaming">
      <div class="wf-node-meta" v-if="nodeMeta">
        <span class="wf-meta-item"><i data-lucide="clock" style="width:12px;height:12px;"></i>{{ nodeMeta.duration }}</span>
        <span class="wf-meta-item"><i data-lucide="cpu" style="width:12px;height:12px;"></i>{{ nodeMeta.model }}</span>
        <span class="wf-meta-item"><i data-lucide="zap" style="width:12px;height:12px;"></i>{{ nodeMeta.tokens }} tokens</span>
      </div>
      <div class="mint-wf-footer">
        <button
          class="mint-btn mint-btn-outline"
          :disabled="workflowStore.isLoading"
          @click="handleRefresh"
        >
          <i data-lucide="refresh-cw" style="width:14px; height:14px;"></i>
          {{ workflowStore.isStreaming ? '取消并重新搜索' : '重新搜索' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'
import { useWorkflowStore } from '@/stores/workflow'
import type { SearchNote, SearchStatus } from '@/composables/useSearchFlow'

const props = defineProps<{
  keyword: string
  searchPlatforms: { name: string; label: string; desc?: string }[]
  selectedPlatform: string
  searchStatus: SearchStatus
  searchResults: SearchNote[]
  searchError: string
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
}>()

const emit = defineEmits<{
  'update:keyword': [value: string]
  'start-flow': []
  'cancel-and-restart': []
  'select-platform': [name: string]
  'start-from-result': [note: SearchNote]
  'search-similar': [keyword: string]
}>()

const workflowStore = useWorkflowStore()

function handleRefresh() {
  if (workflowStore.isStreaming) {
    if (confirm('当前有工作流正在执行，是否取消并开始新搜索？')) {
      emit('cancel-and-restart')
    }
  } else {
    emit('start-flow')
  }
}

const keyword = computed({
  get: () => props.keyword,
  set: (v: string) => emit('update:keyword', v),
})

const statusColor = computed(() => {
  const map: Record<string, string> = {
    idle: '#9CA3AF',
    loading: '#FF2442',
    completed: '#60A5FA',
    error: '#EF4444',
  }
  return map[props.searchStatus] || '#9CA3AF'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    idle: '待执行',
    loading: '执行中',
    completed: '已完成',
    error: '失败',
  }
  return map[props.searchStatus] || '待执行'
})

const statusBadgeStyle = computed(() => {
  if (props.searchStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.searchStatus === 'completed') return { background: '#D1FAE5', color: '#059669' }
  if (props.searchStatus === 'loading') return { background: '#DBEAFE', color: '#2563EB' }
  return {}
})

function coverSrc(cover: string): string {
  const needsProxy = cover.includes('xhscdn.com') ||
    cover.includes('xiaohongshu.com') ||
    cover.includes('picasso-static')
  return needsProxy ? '/api/proxy/image?url=' + encodeURIComponent(cover) : cover
}

function letterColor(platform: string) {
  const palette: Record<string, { bg: string; fg: string }> = {
    hackernews: { bg: '#FF6600', fg: '#FFFFFF' },
    reddit: { bg: '#FF4500', fg: '#FFFFFF' },
    xiaohongshu: { bg: '#FF2442', fg: '#FFFFFF' },
    builtin: { bg: '#FF2442', fg: '#FFFFFF' },
  }
  return palette[platform] || { bg: '#6B7280', fg: '#FFFFFF' }
}

function letterLabel(note: SearchNote): string {
  const palette: Record<string, string> = {
    hackernews: 'HN',
    reddit: 'RD',
    xiaohongshu: 'XHS',
    builtin: '热门',
  }
  if (palette[note.platform]) return palette[note.platform]
  let letter = '?'
  try {
    const u = new URL(note.url)
    const host = u.hostname.replace(/^www./, '')
    letter = host.charAt(0).toUpperCase() || '?'
  } catch {
    letter = (note.title || '?').charAt(0).toUpperCase()
  }
  return letter
}

function onCoverError(e: Event, note: SearchNote) {
  const img = e.target as HTMLImageElement
  const color = letterColor(note.platform)
  const label = letterLabel(note)
  const fallback = document.createElement('div')
  fallback.className = 'mint-note-cover-letter'
  fallback.style.background = color.bg
  fallback.style.color = color.fg
  fallback.innerHTML = `<span class="mint-note-cover-letter-text">${label}</span>`
  img.outerHTML = fallback.outerHTML
}

watch(() => props.searchResults, () => {
  nextTick(() => createIcons({ icons }))
}, { deep: true })

watch(() => props.searchStatus, () => {
  nextTick(() => createIcons({ icons }))
})
</script>