import { ref, computed } from 'vue'
import * as chatSessionsApi from '@/api/chatSessions'

export interface ChatHistoryItem {
  id: string
  title: string
  folderId?: string
  sessionId?: string
  workId?: string | null
  createdAt: number
}

const MAX_DISPLAY = 20

const history = ref<ChatHistoryItem[]>([])
const allExpanded = ref(false)
const loaded = ref(false)

export function useChatHistory() {
  const displayItems = computed(() => {
    if (allExpanded.value) return history.value
    return history.value.slice(0, MAX_DISPLAY)
  })
  const hasMore = computed(() => history.value.length > MAX_DISPLAY)
  const totalCount = computed(() => history.value.length)

  async function loadFromBackend(workId?: string | null) {
    try {
      const sessions = await chatSessionsApi.listSessions(workId)
      if (workId) {
        const filtered = history.value.filter(h => h.workId !== workId)
        for (const s of sessions) {
          const exists = filtered.find(h => h.sessionId === s.id || h.id === s.id)
          if (!exists) {
            filtered.push({
              id: s.id,
              title: s.title || '新会话',
              sessionId: s.id,
              workId: s.work_id,
              createdAt: s.created_at ? new Date(s.created_at).getTime() : Date.now(),
            })
          }
        }
        filtered.sort((a, b) => b.createdAt - a.createdAt)
        history.value = filtered
      } else {
        for (const s of sessions) {
          const exists = history.value.find(h => h.sessionId === s.id || h.id === s.id)
          if (!exists) {
            history.value.push({
              id: s.id,
              title: s.title || '新会话',
              sessionId: s.id,
              workId: s.work_id,
              createdAt: s.created_at ? new Date(s.created_at).getTime() : Date.now(),
            })
          }
        }
        history.value.sort((a, b) => b.createdAt - a.createdAt)
      }
      loaded.value = true
    } catch {
      loaded.value = true
    }
  }

  function addConversation(id: string, title: string, folderId?: string, sessionId?: string, workId?: string | null) {
    const exists = history.value.find(item => item.id === id)
    if (exists) {
      exists.title = title
      if (folderId) exists.folderId = folderId
      if (sessionId) exists.sessionId = sessionId
      if (workId !== undefined) exists.workId = workId
      console.log('[useChatHistory] addConversation: updated existing', id, 'history.length=', history.value.length)
      return
    }
    history.value.unshift({
      id,
      title: title || '新会话',
      folderId,
      sessionId,
      workId,
      createdAt: Date.now()
    })
    console.log('[useChatHistory] addConversation: added new', id, 'history.length=', history.value.length)
  }

  function getConversationsForFolder(folderId: string) {
    return history.value.filter(item => item.folderId === folderId)
  }

  function getConversationsForWork(workId: string) {
    return history.value.filter(item => item.workId === workId)
  }

  function removeConversation(id: string) {
    const idx = history.value.findIndex(item => item.id === id)
    if (idx !== -1) history.value.splice(idx, 1)
  }

  function updateTitle(id: string, title: string) {
    const item = history.value.find(item => item.id === id)
    if (item) item.title = title || '新会话'
  }

  function getSessionId(convId: string): string | null {
    const item = history.value.find(h => h.id === convId)
    return item?.sessionId || null
  }

  function findBySessionId(sessionId: string): ChatHistoryItem | null {
    return history.value.find(h => h.sessionId === sessionId) || null
  }

  function clearAll() {
    history.value = []
    allExpanded.value = false
  }

  function toggleExpand() {
    allExpanded.value = !allExpanded.value
  }

  return {
    history,
    displayItems,
    hasMore,
    totalCount,
    allExpanded,
    loaded,
    addConversation,
    getConversationsForFolder,
    getConversationsForWork,
    removeConversation,
    updateTitle,
    getSessionId,
    findBySessionId,
    loadFromBackend,
    clearAll,
    toggleExpand
  }
}