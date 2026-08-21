import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

export interface AppNotification {
  id: string
  type: string
  message: string
  payload: Record<string, unknown>
  timestamp: string
  read: boolean
}

const notifications = ref<AppNotification[]>([])
let sseConnection: { close: () => void } | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function addNotification(event: { type: string; payload: Record<string, unknown>; timestamp: string }) {
  const n: AppNotification = {
    id: `notif-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    type: event.type,
    message: (event.payload?.message as string) || '新通知',
    payload: event.payload,
    timestamp: event.timestamp,
    read: false,
  }
  notifications.value.unshift(n)
  if (notifications.value.length > 20) {
    notifications.value = notifications.value.slice(0, 20)
  }
}

function markAsRead(id: string) {
  const n = notifications.value.find(x => x.id === id)
  if (n) n.read = true
}

function dismissNotification(id: string) {
  notifications.value = notifications.value.filter(x => x.id !== id)
}

function clearAll() {
  notifications.value = []
}

const unreadCount = () => notifications.value.filter(n => !n.read).length

function connectSSE() {
  const token = localStorage.getItem('token')
  if (!token) return

  if (sseConnection) {
    try { sseConnection.close() } catch {}
    sseConnection = null
  }

  const es = new EventSource(`/api/sse/notifications?token=${encodeURIComponent(token)}`)

  es.addEventListener('topic_pool_monitor', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      addNotification({ type: data.type, payload: data.payload, timestamp: data.timestamp })
    } catch {}
  })

  es.addEventListener('error', () => {
    es.close()
    sseConnection = null
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(connectSSE, 15000)
  })

  sseConnection = { close: () => es.close() }
}

function disconnectSSE() {
  if (sseConnection) {
    try { sseConnection.close() } catch {}
    sseConnection = null
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

export function useNotifications() {
  const router = useRouter()

  function handleNotificationClick(n: AppNotification) {
    markAsRead(n.id)
    if (n.type === 'topic_pool_monitor') {
      router.push('/topic-pool')
    }
  }

  onMounted(() => {
    connectSSE()
  })

  onUnmounted(() => {
    disconnectSSE()
  })

  return {
    notifications,
    unreadCount,
    handleNotificationClick,
    markAsRead,
    dismissNotification,
    clearAll,
    connectSSE,
    disconnectSSE,
  }
}