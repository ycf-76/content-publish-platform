import { onUnmounted } from 'vue'

let _controller: AbortController | null = null
let _retryTimer: ReturnType<typeof setTimeout> | null = null

export function useNotificationSSE() {
  function start() {
    if (_controller) return
    const token = localStorage.getItem('token')
    if (!token) {
      _retryTimer = setTimeout(start, 3000)
      return
    }
    _controller = new AbortController()
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api'
    const url = `${baseUrl}/sse/notifications`
    console.log('[NotificationSSE] connecting:', url)
    fetch(url, {
      headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
      signal: _controller.signal,
    }).then(response => {
      if (!response.ok) {
        console.warn('[NotificationSSE] failed:', response.status)
        _controller = null
        _retryTimer = setTimeout(start, 5000)
        return
      }
      if (!response.body) {
        console.warn('[NotificationSSE] no response body')
        return
      }
      console.log('[NotificationSSE] connected')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      function processChunk(result: { done: boolean; value?: Uint8Array }) {
        const { done, value } = result
        if (done) {
          console.log('[NotificationSSE] stream ended, reconnecting...')
          _controller = null
          _retryTimer = setTimeout(start, 3000)
          return
        }
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            console.log('[NotificationSSE] event type:', evt.type)
          } catch (e) {
            console.warn('[NotificationSSE] parse error:', e, 'line:', line.slice(0, 120))
          }
        }
        reader.read().then(processChunk).catch((readErr) => {
          if (readErr.name !== 'AbortError') {
            console.warn('[NotificationSSE] read error:', readErr)
            _controller = null
            _retryTimer = setTimeout(start, 5000)
          }
        })
      }
      reader.read().then(processChunk).catch((readErr) => {
        if (readErr.name !== 'AbortError') {
          console.warn('[NotificationSSE] initial read error:', readErr)
          _controller = null
          _retryTimer = setTimeout(start, 5000)
        }
      })
    }).catch((err) => {
      if (err.name !== 'AbortError') {
        console.warn('[NotificationSSE] error:', err)
        _controller = null
        _retryTimer = setTimeout(start, 5000)
      }
    })
  }

  function stop() {
    if (_retryTimer) {
      clearTimeout(_retryTimer)
      _retryTimer = null
    }
    if (_controller) {
      _controller.abort()
      _controller = null
    }
  }

  onUnmounted(stop)

  return { start, stop }
}