import { ref, computed } from 'vue'

export interface ChatHistoryItem {
  id: string
  title: string
  createdAt: number
}

const MAX_DISPLAY = 6

const history = ref<ChatHistoryItem[]>([])
const allExpanded = ref(false)

export function useChatHistory() {
  const displayItems = computed(() => {
    if (allExpanded.value) return history.value
    return history.value.slice(0, MAX_DISPLAY)
  })
  const hasMore = computed(() => history.value.length > MAX_DISPLAY)
  const totalCount = computed(() => history.value.length)

  function addConversation(id: string, title: string) {
    const exists = history.value.find(item => item.id === id)
    if (exists) {
      exists.title = title
      return
    }
    history.value.unshift({
      id,
      title: title || '新会话',
      createdAt: Date.now()
    })
  }

  function removeConversation(id: string) {
    const idx = history.value.findIndex(item => item.id === id)
    if (idx !== -1) history.value.splice(idx, 1)
  }

  function updateTitle(id: string, title: string) {
    const item = history.value.find(item => item.id === id)
    if (item) item.title = title || '新会话'
  }

  function clearAll() {
    history.value = []
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
    addConversation,
    removeConversation,
    updateTitle,
    clearAll,
    toggleExpand
  }
}