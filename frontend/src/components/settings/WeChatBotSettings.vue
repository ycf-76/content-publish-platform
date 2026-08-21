<template>
  <div class="wb-wrap">
    <div class="wb-header">
      <div class="wb-header-left">
        <span class="wb-icon">💬</span>
        <span class="wb-title">微信机器人</span>
      </div>
      <label class="wb-switch" :class="{ active: isRunning }">
        <input type="checkbox" v-model="toggleValue" @change="onToggle" />
        <span class="wb-slider"></span>
      </label>
    </div>

    <div class="wb-body">
      <div v-if="!isRunning" class="wb-off">
        <span class="wb-off-text">未启动</span>
        <span class="wb-off-hint">打开开关以连接微信</span>
      </div>

      <div v-else-if="status === 'waiting_qr'" class="wb-qr">
        <div class="wb-qr-img-wrap">
          <img v-if="qrCode" :src="qrCode" class="wb-qr-img" />
          <div v-else class="wb-qr-loading">
            <div class="wb-spinner"></div>
          </div>
        </div>
        <span class="wb-qr-hint">扫码登录微信</span>
        <span class="wb-qr-timer" v-if="qrExpiry > 0">{{ qrExpiry }}s</span>
      </div>

      <div v-else-if="status === 'logged_in'" class="wb-connected">
        <div class="wb-connected-header">
          <div class="wb-on">
            <div class="wb-status-dot green"></div>
            <div class="wb-on-info">
              <span class="wb-on-label">已连接</span>
              <span class="wb-on-wxid">{{ wxidShort }}</span>
            </div>
          </div>
        </div>

        <div class="wb-msg-list" ref="msgListRef">
          <div v-if="messages.length === 0" class="wb-msg-empty">
            暂无消息
          </div>
          <div
            v-for="(msg, i) in messages"
            :key="i"
            class="wb-msg-item"
            :class="{ sent: msg.direction === 'sent' || msg.from_user_id === 'bot' }"
          >
            <span class="wb-msg-dir">{{ msg.direction === 'sent' || msg.from_user_id === 'bot' ? '↗' : '↙' }}</span>
            <span class="wb-msg-text">{{ msg.text }}</span>
            <span class="wb-msg-time">{{ formatTime(msg) }}</span>
          </div>
        </div>

        <div class="wb-send-bar">
          <input
            v-model="sendText"
            class="wb-send-input"
            placeholder="发送消息..."
            @keydown.enter="onSend"
            :disabled="sending"
          />
          <button class="wb-send-btn" @click="onSend" :disabled="!sendText.trim() || sending">
            {{ sending ? '...' : '发' }}
          </button>
        </div>
      </div>

      <div v-else-if="status === 'error'" class="wb-on">
        <div class="wb-status-dot red"></div>
        <div class="wb-on-info">
          <span class="wb-on-label" style="color:var(--color-error)">连接失败</span>
          <span class="wb-on-wxid">{{ errorMsg }}</span>
        </div>
      </div>

      <div v-else class="wb-on">
        <div class="wb-status-dot yellow"></div>
        <div class="wb-on-info">
          <span class="wb-on-label">{{ statusLabel }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'

const API_BASE = '/api/wechat'

const isRunning = ref(false)
const status = ref('stopped')
const qrCode = ref('')
const wxid = ref('')
const nickname = ref('')
const errorMsg = ref('')
const qrExpiry = ref(0)
const toggleValue = ref(false)
const messages = ref<any[]>([])
const sendText = ref('')
const sending = ref(false)
const msgListRef = ref<HTMLElement | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null
let expiryTimer: ReturnType<typeof setInterval> | null = null

const wxidShort = computed(() => {
  if (!wxid.value) return ''
  const s = wxid.value.split('@')[0]
  return s.length > 12 ? s.slice(0, 12) + '...' : s
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    stopped: '已停止',
    starting: '启动中...',
    waiting_qr: '等待扫码',
    scanned: '已扫码，确认中...',
    confirming: '登录确认中...',
    polling: '登录中...',
    logged_in: '已连接',
    error: '错误',
  }
  return map[status.value] || status.value
})

function formatTime(msg: any) {
  const ts = msg.received_at || msg.sent_at
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

async function apiFetch(path: string, opts?: RequestInit) {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}${path}`, {
    headers,
    ...opts,
  })
  if (res.status === 401) {
    throw new Error('未登录或登录已过期，请重新登录')
  }
  return res.json()
}

async function onToggle() {
  if (toggleValue.value) {
    try {
      const r = await apiFetch('/start', { method: 'POST' })
      if (r.success) {
        isRunning.value = true
        status.value = r.data?.status || 'starting'
        if (r.data?.qr_code_base64) {
          qrCode.value = r.data.qr_code_base64
        }
        startPolling()
      } else {
        toggleValue.value = false
        errorMsg.value = r.message || '启动失败'
        status.value = 'error'
      }
    } catch (e: any) {
      toggleValue.value = false
      errorMsg.value = e.message || '网络错误'
      status.value = 'error'
    }
  } else {
    try {
      await apiFetch('/stop', { method: 'POST' })
    } catch {}
    stopPolling()
    isRunning.value = false
    status.value = 'stopped'
    qrCode.value = ''
    wxid.value = ''
    nickname.value = ''
    errorMsg.value = ''
    messages.value = []
  }
}

async function pollStatus() {
  try {
    const r = await apiFetch('/status')
    if (!r.success || !r.data) return

    const d = r.data
    status.value = d.status || 'stopped'
    isRunning.value = d.is_running ?? (d.status !== 'stopped')
    wxid.value = d.wxid || ''
    nickname.value = d.nickname || ''
    errorMsg.value = d.error || ''

    if (d.status === 'waiting_qr') {
      if (d.qr_code_base64) {
        qrCode.value = d.qr_code_base64
      } else if (!qrCode.value) {
        fetchQrCode()
      }
    }

    if (d.status === 'logged_in') {
      qrCode.value = ''
      qrExpiry.value = 0
      fetchMessages()
    }
  } catch {}
}

async function fetchMessages() {
  try {
    const r = await apiFetch('/messages?limit=20')
    if (r.success && r.data?.messages) {
      messages.value = r.data.messages
      await nextTick()
      scrollToBottom()
    }
  } catch {}
}

async function onSend() {
  const text = sendText.value.trim()
  if (!text || sending.value) return

  if (messages.value.length === 0) {
    alert('请先让对方发一条消息，才能回复')
    return
  }

  const lastIncoming = [...messages.value].reverse().find((m: any) => m.from_user_id !== 'bot')
  if (!lastIncoming) {
    alert('请先让对方发一条消息，才能回复')
    return
  }

  sending.value = true
  try {
    const r = await apiFetch('/send', {
      method: 'POST',
      body: JSON.stringify({
        to_user_id: lastIncoming.from_user_id,
        content: text,
        context_token: lastIncoming.context_token || '',
      }),
    })
    if (r.success) {
      sendText.value = ''
      setTimeout(fetchMessages, 1000)
    } else {
      alert(r.detail || r.message || '发送失败')
    }
  } catch (e: any) {
    alert(e.message || '发送失败')
  } finally {
    sending.value = false
  }
}

function scrollToBottom() {
  if (msgListRef.value) {
    msgListRef.value.scrollTop = msgListRef.value.scrollHeight
  }
}

async function fetchQrCode() {
  try {
    const r = await apiFetch('/qrcode')
    if (r.success && r.data?.qrcode) {
      qrCode.value = r.data.qrcode
      qrExpiry.value = r.data.expires_in || 120
      startExpiryCountdown()
    }
  } catch {}
}

function startExpiryCountdown() {
  if (expiryTimer) clearInterval(expiryTimer)
  expiryTimer = setInterval(() => {
    if (qrExpiry.value > 0) {
      qrExpiry.value -= 1
    } else {
      if (expiryTimer) clearInterval(expiryTimer)
    }
  }, 1000)
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollStatus, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (expiryTimer) {
    clearInterval(expiryTimer)
    expiryTimer = null
  }
}

onMounted(async () => {
  try {
    const r = await apiFetch('/status')
    if (r.success && r.data) {
      const d = r.data
      status.value = d.status || 'stopped'
      isRunning.value = d.is_running ?? (d.status !== 'stopped')
      toggleValue.value = isRunning.value
      wxid.value = d.wxid || ''
      nickname.value = d.nickname || ''
      if (d.status === 'waiting_qr') {
        fetchQrCode()
      }
      if (d.status === 'logged_in') {
        fetchMessages()
      }
      if (isRunning.value && d.status !== 'stopped') {
        startPolling()
      }
    }
  } catch {}
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.wb-wrap {
  background: var(--ma-card, #fff);
  border: 1px solid var(--ma-border, #ededed);
  border-radius: 12px;
  overflow: hidden;
}

.wb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--ma-border, #ededed);
}

.wb-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.wb-icon {
  font-size: 16px;
}

.wb-title {
  font-size: var(--text-body, 14px);
  font-weight: var(--weight-semibold, 600);
  color: var(--text-primary, #1a1a1a);
}

.wb-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  cursor: pointer;
}

.wb-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.wb-slider {
  position: absolute;
  inset: 0;
  background: #d1d5db;
  border-radius: 9999px;
  transition: background 0.2s;
}

.wb-slider::before {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  left: 2px;
  top: 2px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}

.wb-switch.active .wb-slider {
  background: var(--color-accent, #ff2442);
}

.wb-switch.active .wb-slider::before {
  transform: translateX(16px);
}

.wb-body {
  padding: 16px;
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wb-off {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.wb-off-text {
  font-size: var(--text-sm, 13px);
  color: var(--text-muted, #9a9a9a);
}

.wb-off-hint {
  font-size: var(--text-xs, 12px);
  color: var(--text-muted, #9a9a9a);
  opacity: 0.7;
}

.wb-qr {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.wb-qr-img-wrap {
  width: 140px;
  height: 140px;
  border: 1px solid var(--ma-border, #ededed);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fafafa;
}

.wb-qr-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.wb-qr-loading {
  display: flex;
  align-items: center;
  justify-content: center;
}

.wb-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #e5e7eb;
  border-top-color: var(--color-accent, #ff2442);
  border-radius: 50%;
  animation: wb-spin 0.6s linear infinite;
}

@keyframes wb-spin {
  to { transform: rotate(360deg); }
}

.wb-qr-hint {
  font-size: var(--text-xs, 12px);
  color: var(--text-secondary, #4b4b4b);
}

.wb-qr-timer {
  font-size: var(--text-xs, 12px);
  color: var(--text-muted, #9a9a9a);
}

.wb-on {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.wb-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.wb-status-dot.green {
  background: var(--color-success, #10b981);
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15);
}

.wb-status-dot.red {
  background: var(--color-error, #ef4444);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15);
}

.wb-status-dot.yellow {
  background: var(--color-warning, #f59e0b);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15);
}

.wb-on-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.wb-on-label {
  font-size: var(--text-sm, 13px);
  font-weight: var(--weight-medium, 500);
  color: var(--text-primary, #1a1a1a);
}

.wb-on-wxid {
  font-size: var(--text-xs, 12px);
  color: var(--text-muted, #9a9a9a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-connected {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wb-connected-header {
  display: flex;
  align-items: center;
}

.wb-msg-list {
  max-height: 180px;
  overflow-y: auto;
  border: 1px solid var(--ma-border, #ededed);
  border-radius: 8px;
  padding: 8px;
  background: #fafafa;
}

.wb-msg-empty {
  text-align: center;
  font-size: var(--text-xs, 12px);
  color: var(--text-muted, #9a9a9a);
  padding: 12px 0;
}

.wb-msg-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px 0;
  font-size: var(--text-xs, 12px);
  line-height: 1.4;
}

.wb-msg-item.sent {
  flex-direction: row-reverse;
}

.wb-msg-dir {
  flex-shrink: 0;
  font-size: 10px;
  opacity: 0.5;
}

.wb-msg-text {
  flex: 1;
  color: var(--text-primary, #1a1a1a);
  word-break: break-all;
}

.wb-msg-item.sent .wb-msg-text {
  color: var(--color-accent, #ff2442);
}

.wb-msg-time {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-muted, #9a9a9a);
  opacity: 0.6;
}

.wb-send-bar {
  display: flex;
  gap: 6px;
}

.wb-send-input {
  flex: 1;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--ma-border, #ededed);
  border-radius: 6px;
  font-size: var(--text-xs, 12px);
  outline: none;
  background: #fff;
}

.wb-send-input:focus {
  border-color: var(--color-accent, #ff2442);
}

.wb-send-btn {
  width: 36px;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: var(--color-accent, #ff2442);
  color: #fff;
  font-size: var(--text-xs, 12px);
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.wb-send-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>