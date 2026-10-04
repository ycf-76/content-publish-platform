import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useWorkStore, type WorkItem, type WorkContext } from './work'

export type ContextItemType = 'work' | 'analysis' | 'file' | 'url' | 'rule' | 'memory'

export interface ContextItem {
  id: string
  type: ContextItemType
  label: string
  summary: string
  pinned: boolean
  addedAt: number
  meta: Record<string, any>
}

export interface SidebarSignal {
  type: 'show-work' | 'show-analysis' | 'show-creation' | 'highlight-metric' | 'show-file' | 'show-workspace'
  payload: Record<string, string | number | boolean | null>
  source: 'ai-message' | 'user-action'
}

export interface StyleMemory {
  id: string
  content: string
  source: 'ai-auto' | 'user-set'
  createdAt: number
}

const MAX_TRACK_ITEMS = 10
const MAX_STYLE_MEMORIES = 20
const CONTEXT_RING_WARN = 0.9
const ESTIMATED_TOKEN_LIMIT = 8000

export const useChatContextStore = defineStore('chatContext', () => {
  const workStore = useWorkStore()

  const contextTrack = ref<ContextItem[]>([])

  const boundConversationId = ref<string | null>(null)

  const conversationBuckets = ref<Map<string, ContextItem[]>>(new Map())

  const sidebarVisible = ref(false)

  const sidebarWidth = ref(
    (() => {
      const stored = Number(localStorage.getItem('ctx-sidebar-width'))
      const valid = Number.isFinite(stored) && stored >= 240 && stored <= 600
      return valid ? stored : Math.max(280, Math.min(420, Math.floor(window.innerWidth / 4)))
    })()
  )

  const pendingSignals = ref<SidebarSignal[]>([])

  const activeWorkId = computed(() => workStore.activeWorkId)

  const activeWork = computed(() => workStore.activeWork)

  const pinnedItems = computed(() => contextTrack.value.filter(i => i.pinned))

  const unpinnedItems = computed(() => contextTrack.value.filter(i => !i.pinned))

  const trackFull = ref(false)

  const previewItem = ref<ContextItem | null>(null)

  const styleMemories = ref<StyleMemory[]>([])
  ;(() => {
    try {
      const raw = localStorage.getItem('ctx-style-memories')
      if (raw) styleMemories.value = JSON.parse(raw)
    } catch {}
  })()

  watch(styleMemories, (val) => {
    try {
      localStorage.setItem('ctx-style-memories', JSON.stringify(val))
    } catch {}
  }, { deep: true })

  function addStyleMemory(input: { content: string; source: 'ai-auto' | 'user-set' }): StyleMemory | null {
    const trimmed = input.content.trim()
    if (!trimmed) return null

    const existing = styleMemories.value.find(m => {
      if (m.content === trimmed) return true
      const shorter = m.content.length < trimmed.length ? m.content : trimmed
      const longer = m.content.length < trimmed.length ? trimmed : m.content
      if (longer.includes(shorter) && shorter.length > longer.length * 0.6) return true
      return false
    })
    if (existing) {
      existing.createdAt = Date.now()
      return existing
    }

    if (styleMemories.value.length >= MAX_STYLE_MEMORIES) {
      const oldestAuto = styleMemories.value.find(m => m.source === 'ai-auto')
      if (oldestAuto) {
        styleMemories.value.splice(styleMemories.value.indexOf(oldestAuto), 1)
      } else {
        return null
      }
    }

    const mem: StyleMemory = {
      id: `mem-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      content: trimmed,
      source: input.source,
      createdAt: Date.now(),
    }
    styleMemories.value.unshift(mem)
    return mem
  }

  function removeStyleMemory(id: string) {
    const idx = styleMemories.value.findIndex(m => m.id === id)
    if (idx !== -1) {
      const mem = styleMemories.value[idx]
      if (mem.source === 'user-set') return
      styleMemories.value.splice(idx, 1)
    }
  }

  function editStyleMemory(id: string, newContent: string) {
    const mem = styleMemories.value.find(m => m.id === id)
    if (mem) mem.content = newContent.trim()
  }

  const estimatedTokenCount = computed(() => {
    const prompt = buildSystemPrompt()
    if (!prompt) return 0
    const cjkCount = (prompt.match(/[\u4e00-\u9fff]/g) || []).length
    const asciiCount = prompt.length - cjkCount
    return Math.ceil(cjkCount * 1.5 + asciiCount * 0.25)
  })

  const contextRingRatio = computed(() => {
    return Math.min(1, estimatedTokenCount.value / ESTIMATED_TOKEN_LIMIT)
  })

  const contextRingWarn = computed(() => contextRingRatio.value >= CONTEXT_RING_WARN)

  function addContextItem(item: Omit<ContextItem, 'id' | 'addedAt'>): ContextItem | null {
    const MAX_TRACK_SIZE = MAX_TRACK_ITEMS
    const existing = contextTrack.value.find(
      i => i.type === item.type && i.meta.refId === item.meta.refId
    )
    if (existing) {
      existing.label = item.label
      existing.summary = item.summary
      existing.pinned = item.pinned || existing.pinned
      existing.meta = { ...existing.meta, ...item.meta }
      trackFull.value = false
      return existing
    }
    if (contextTrack.value.length >= MAX_TRACK_SIZE) {
      const lastUnpinned = contextTrack.value.find(i => !i.pinned)
      if (lastUnpinned) {
        removeContextItem(lastUnpinned.id)
      } else {
        console.warn('[chatContext] track full (all pinned), cannot add new item')
        trackFull.value = true
        return null
      }
    }
    trackFull.value = false
    const full: ContextItem = {
      ...item,
      id: `ctx-${item.type}-${item.meta.refId || Date.now()}`,
      addedAt: Date.now(),
    }
    contextTrack.value.unshift(full)
    return full
  }

  function removeContextItem(id: string) {
    const idx = contextTrack.value.findIndex(i => i.id === id)
    if (idx !== -1) {
      contextTrack.value.splice(idx, 1)
      trackFull.value = false
    }
  }

  function togglePin(id: string) {
    const item = contextTrack.value.find(i => i.id === id)
    if (item) {
      item.pinned = !item.pinned
      trackFull.value = false
    }
  }

  function clearUnpinned() {
    contextTrack.value = contextTrack.value.filter(i => i.pinned)
    trackFull.value = false
  }

  function clearAll() {
    contextTrack.value = []
    boundConversationId.value = null
    pendingSignals.value = []
    trackFull.value = false
  }

  const MAX_BUCKETS = 20

  function saveCurrentBucket() {
    if (!boundConversationId.value) return
    if (contextTrack.value.length === 0) {
      conversationBuckets.value.delete(boundConversationId.value)
      return
    }
    conversationBuckets.value.set(boundConversationId.value, [...contextTrack.value])
    if (conversationBuckets.value.size > MAX_BUCKETS) {
      const oldest = conversationBuckets.value.keys().next().value
      if (oldest) conversationBuckets.value.delete(oldest)
    }
  }

  function bindConversation(convId: string | null) {
    if (convId === boundConversationId.value) return
    saveCurrentBucket()
    boundConversationId.value = convId
    pendingSignals.value = []
    orphanItemIds.value = new Set()
    if (convId && conversationBuckets.value.has(convId)) {
      const bucket = conversationBuckets.value.get(convId)!
      conversationBuckets.value.delete(convId)
      conversationBuckets.value.set(convId, bucket)
      contextTrack.value = [...bucket]
      revalidateOrphans()
    } else {
      contextTrack.value = []
    }
    trackFull.value = false
  }

  function unbindConversation() {
    bindConversation(null)
  }

  function isContextForConversation(convId: string | null): boolean {
    if (!boundConversationId.value) return true
    return boundConversationId.value === convId
  }

  function stableStringify(obj: Record<string, string | number | boolean | null>): string {
    try {
      const keys = Object.keys(obj).sort()
      return '{' + keys.map(k => `"${k}":${JSON.stringify(obj[k])}`).join(',') + '}'
    } catch {
      return JSON.stringify(obj)
    }
  }

  function emitSignal(signal: SidebarSignal) {
    const MAX_SIGNALS = 10
    const dedupeKey = `${signal.type}:${stableStringify(signal.payload)}`
    const isDup = pendingSignals.value.some(
      s => `${s.type}:${stableStringify(s.payload)}` === dedupeKey
    )
    if (isDup) return
    if (pendingSignals.value.length >= MAX_SIGNALS) {
      pendingSignals.value.shift()
    }
    pendingSignals.value.push(signal)
  }

  function consumeSignal(): SidebarSignal | null {
    return pendingSignals.value.shift() || null
  }

  function setSidebarVisible(v: boolean) {
    sidebarVisible.value = v
    workStore.showWorkDetail = v
  }

  function toggleSidebar() {
    setSidebarVisible(!sidebarVisible.value)
  }

  function setSidebarWidth(w: number) {
    sidebarWidth.value = Math.max(240, Math.min(600, w))
    localStorage.setItem('ctx-sidebar-width', String(sidebarWidth.value))
  }

  async function linkWork(workId: string) {
    let work = workStore.works.find(w => w.id === workId)
    if (!work) {
      try {
        await workStore.fetchWorks()
        work = workStore.works.find(w => w.id === workId)
      } catch {}
    }
    if (!work) {
      console.warn('[chatContext] linkWork: work not found in store, id=', workId, 'works count=', workStore.works.length)
      return
    }
    if (workStore.activeWorkId !== workId) {
      workStore.setActiveWork(workId)
    }
    sidebarVisible.value = true
    const added = addContextItem({
      type: 'work',
      label: work.title || '未命名作品',
      summary: `${workStore.getPlatformLabel(work.platform)} · ${workStore.getContentTypeLabel(work.contentType)} · ${work.performanceTier}级`,
      pinned: true,
      meta: {
        refId: work.id,
        platform: work.platform,
        contentType: work.contentType,
        performanceTier: work.performanceTier,
      },
    })
    if (added) {
      previewItem.value = { ...added }
    } else {
      trackFull.value = true
    }
  }

  function unlinkWork(workId?: string) {
    const targetId = workId || workStore.activeWorkId
    if (!targetId) return
    const targetItem = contextTrack.value.find(i => i.type === 'work' && i.meta.refId === targetId)
    if (!targetItem) return
    removeContextItem(targetItem.id)
    if (targetId === workStore.activeWorkId) {
      workStore.setActiveWork(null)
    }
  }

  function linkAnalysis(data: Record<string, any>) {
    workStore.setAnalysisContext(data)
    const overview = data.overview
    const added = addContextItem({
      type: 'analysis',
      label: '数据分析报告',
      summary: overview
        ? `${overview.total}篇 · 爆款${overview.replicated}篇 · 均分${((overview.avg_score || 0) * 100).toFixed(0)}`
        : '分析数据已联动',
      pinned: false,
      meta: { refId: 'analysis-latest', overview },
    })
    if (!added) return
  }

  function unlinkAnalysis() {
    workStore.setAnalysisContext(null)
    const items = contextTrack.value.filter(i => i.type === 'analysis')
    for (const item of items) removeContextItem(item.id)
  }

  const MAX_SYSTEM_PROMPT_LEN = 6000
  const MAX_CONTENT_SLICE = 800

  const orphanItemIds = ref<Set<string>>(new Set())

  function revalidateOrphans() {
    if (workStore.isLoading) return
    orphanItemIds.value = new Set()
    for (const item of contextTrack.value) {
      if (item.type === 'work' && item.pinned) {
        const work = workStore.works.find(w => w.id === item.meta.refId)
        if (!work) {
          orphanItemIds.value.add(item.id)
          item.pinned = false
        }
      }
    }
  }

  watch(() => workStore.isLoading, (loading, wasLoading) => {
    if (wasLoading && !loading) {
      revalidateOrphans()
    }
  })

  function buildSystemPrompt(): string | null {
    const pinned = pinnedItems.value
    if (pinned.length === 0) return null

    const parts: string[] = []

    for (const item of pinned) {
      const local: string[] = []

      switch (item.type) {
        case 'work': {
          const work = workStore.works.find(w => w.id === item.meta.refId)
          if (!work) {
            orphanItemIds.value.add(item.id)
            if (item.pinned) {
              togglePin(item.id)
            }
            console.warn(`[chatContext] work not found for refId=${item.meta.refId}, auto-unpinned and skipped in prompt`)
            break
          }
          orphanItemIds.value.delete(item.id)
          local.push('=== 作品信息 ===')
          if (work.title) local.push(`标题: ${work.title}`)
          if (work.platform) local.push(`平台: ${workStore.getPlatformLabel(work.platform)}`)
          if (work.contentType) local.push(`类型: ${workStore.getContentTypeLabel(work.contentType)}`)
          if (work.performanceTier) local.push(`等级: ${work.performanceTier}`)
          if (work.contentText) {
            const s = work.contentText.length > MAX_CONTENT_SLICE
              ? work.contentText.slice(0, MAX_CONTENT_SLICE) + '…'
              : work.contentText
            local.push(`\n正文内容:\n${s}`)
          }
          if (work.scriptText) {
            const s = work.scriptText.length > MAX_CONTENT_SLICE
              ? work.scriptText.slice(0, MAX_CONTENT_SLICE) + '…'
              : work.scriptText
            local.push(`\n脚本内容:\n${s}`)
          }
          if (Array.isArray(work.tags) && work.tags.length) local.push(`标签: ${work.tags.slice(0, 10).join(', ')}`)
          const ir = work.interactionRate ?? 0
          const views = work.views ?? work.playCount ?? 0
          const likes = work.likes ?? 0
          const collects = work.collects ?? 0
          local.push(`数据: 浏览${views} | 点赞${likes} | 收藏${collects} | 互动率${(ir * 100).toFixed(1)}%`)
          if (work.aiDiagnosis) {
            if (work.aiDiagnosis.performanceReason) local.push(`\nAI诊断: ${work.aiDiagnosis.performanceReason}`)
            if (work.aiDiagnosis.nextAction) local.push(`下一步: ${work.aiDiagnosis.nextAction}`)
          }
          break
        }
        case 'analysis': {
          const prompt = workStore.buildAnalysisPrompt()
          if (prompt) local.push(prompt)
          break
        }
        case 'file': {
          if (item.meta.fileName) local.push(`关联文件: ${item.meta.fileName}`)
          if (item.meta.contentPreview) {
            const raw = String(item.meta.contentPreview)
            const s = raw.length > MAX_CONTENT_SLICE ? raw.slice(0, MAX_CONTENT_SLICE) + '…' : raw
            local.push(`文件内容预览:\n${s}`)
          }
          break
        }
        case 'url': {
          if (item.meta.url) local.push(`关联链接: ${item.meta.url}`)
          if (item.meta.contentPreview) {
            const raw = String(item.meta.contentPreview)
            const s = raw.length > MAX_CONTENT_SLICE ? raw.slice(0, MAX_CONTENT_SLICE) + '…' : raw
            local.push(`链接内容预览:\n${s}`)
          }
          break
        }
        case 'rule': {
          if (item.meta.ruleName) local.push(`创作规范: ${item.meta.ruleName}`)
          if (item.meta.ruleContent) local.push(`规范内容: ${item.meta.ruleContent}`)
          break
        }
        case 'memory': {
          if (item.meta.memoryContent) local.push(`风格记忆: ${item.meta.memoryContent}`)
          break
        }
      }

      if (local.length > 0) {
        parts.push(...local)
      }
    }

    if (parts.length === 0 && styleMemories.value.length === 0) return null

    if (styleMemories.value.length > 0) {
      const memLines = styleMemories.value.map(m => `- ${m.content}`)
      parts.push('', '=== 用户风格偏好 ===', ...memLines)
    }

    let result = [
      '【重要】以下上下文已由用户钉选，你必须基于这些实际内容来回答问题：',
      '',
      ...parts,
      '',
      '=== 强制要求 ===',
      '1. 回答时必须引用上述上下文中的实际内容，不要说"没有内容"或"未保存"',
      '2. 如果用户要求分析/优化/改写，直接针对上述内容进行操作',
      '3. 绝对禁止回复"草稿文件还没有保存"或类似的内容缺失提示',
      '4. 上下文内容已经完整提供给你，立即开始工作！',
    ].join('\n')

    if (result.length > MAX_SYSTEM_PROMPT_LEN) {
      console.warn(`[chatContext] system prompt truncated from ${result.length} to ${MAX_SYSTEM_PROMPT_LEN}`)
      result = result.slice(0, MAX_SYSTEM_PROMPT_LEN) + '\n\n[注意: 上下文内容已截断，总长度超出限制]'
    }

    return result
  }

  function shouldInjectContext(): boolean {
    return pinnedItems.value.length > 0 || styleMemories.value.length > 0
  }

  return {
    contextTrack,
    boundConversationId,
    conversationBuckets,
    sidebarVisible,
    sidebarWidth,
    pendingSignals,
    activeWorkId,
    activeWork,
    pinnedItems,
    unpinnedItems,
    orphanItemIds,
    trackFull,
    previewItem,
    styleMemories,
    estimatedTokenCount,
    contextRingRatio,
    contextRingWarn,
    addContextItem,
    removeContextItem,
    togglePin,
    clearUnpinned,
    clearAll,
    bindConversation,
    unbindConversation,
    isContextForConversation,
    emitSignal,
    consumeSignal,
    setSidebarVisible,
    toggleSidebar,
    setSidebarWidth,
    linkWork,
    unlinkWork,
    linkAnalysis,
    unlinkAnalysis,
    addStyleMemory,
    removeStyleMemory,
    editStyleMemory,
    buildSystemPrompt,
    shouldInjectContext,
  }
})