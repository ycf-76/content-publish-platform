<template>
  <div class="pa-wrap">
    <div v-if="loading" class="pa-loading">
      <div class="pa-spinner"></div>
      <span>加载账号信息...</span>
    </div>

    <div v-else class="pa-content">
      <div v-if="errorMsg" class="pa-error-bar">
        <span>{{ errorMsg }}</span>
        <button @click="loadAccounts" class="pa-retry-btn">重试</button>
      </div>

      <h3 style="margin:0 0 6px;color:#1A1A1A;font-size:14px;font-weight:600;">绑定你的平台账号</h3>
      <p style="margin:0 0 16px;color:#9CA3AF;font-size:13px;">绑定后可一键同步回收全部已发布作品数据，智能体自动分析诊断</p>

      <div class="pa-platform-list">
        <div v-for="account in accounts" :key="account.platform" class="pa-platform-card">
          <div class="pa-platform-row">
            <div class="pa-platform-icon" :class="{ 'pa-platform-icon-avatar': account.bound && account.platform_avatar_url }">
              <img v-if="account.bound && account.platform_avatar_url" :src="account.platform_avatar_url" :alt="account.platform_label" class="pa-avatar-img" />
              <img v-else-if="platformIcons[account.platform]" :src="platformIcons[account.platform]" :alt="account.platform_label" />
              <span v-else class="pa-platform-icon-text">{{ account.platform_label?.charAt(0) }}</span>
            </div>

            <div class="pa-platform-info">
              <div class="pa-platform-header">
                <span class="pa-platform-name">{{ account.platform_label }}</span>
                <span v-if="account.bound && account.sync_status === 'idle'" class="pa-badge pa-badge-success">
                  <span class="pa-badge-dot"></span>已绑定
                </span>
                <span v-else-if="account.sync_status === 'running'" class="pa-badge pa-badge-warning">
                  <span class="pa-spinner-sm"></span>同步中
                </span>
                <span v-else-if="!account.bound" class="pa-badge pa-badge-default">未绑定</span>
              </div>
              <div class="pa-platform-desc">
                <template v-if="account.bound">
                  <span v-if="account.platform_nickname">{{ account.platform_nickname }}</span>
                  <span v-if="account.works_count > 0"> · {{ account.works_count }}篇作品</span>
                  <span v-if="account.fans_count && account.fans_count > 0"> · {{ formatFans(account.fans_count) }}粉丝</span>
                  <span v-if="account.last_synced_at"> · 上次同步 {{ formatTime(account.last_synced_at) }}</span>
                </template>
                <template v-else>
                  扫码绑定后可同步作品数据
                </template>
              </div>
              <div v-if="account.sync_error" class="pa-sync-error">{{ account.sync_error }}</div>
            </div>

            <div class="pa-platform-actions">
              <template v-if="!account.bound">
                <button @click="bindAccount(account.platform, account.platform_label)" :disabled="bindingPlatform === account.platform" class="pa-btn pa-btn-primary">
                  {{ bindingPlatform === account.platform ? '获取二维码...' : '扫码绑定' }}
                </button>
              </template>
              <template v-else>
                <button @click="confirmSync(account)" :disabled="account.sync_status === 'running'" class="pa-btn pa-btn-primary">
                  {{ account.sync_status === 'running' ? '同步中...' : '同步作品' }}
                </button>
                <button @click="unbindAccount(account)" class="pa-btn pa-btn-ghost">解绑</button>
              </template>
            </div>
          </div>
          <div v-if="account.bound" class="pa-sync-warning">
            ⚠️ 频繁同步可能触发平台风控，建议每周 1-2 次
          </div>
        </div>
      </div>

      <div v-if="hasBoundAccounts" class="pa-sync-all">
        <button @click="confirmSyncAll" :disabled="syncingAll" class="pa-btn pa-btn-primary pa-btn-lg">
          {{ syncingAll ? '同步中...' : '一键同步所有平台' }}
        </button>
        <p class="pa-sync-all-warning">⚠️ 频繁同步可能触发平台风控，建议每周 1-2 次</p>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showQrModal" class="qr-overlay" @click.self="closeQrModal">
        <div class="qr-modal">
          <div class="qr-modal-header">
            <span class="qr-modal-title">扫码登录{{ qrPlatformLabel }}</span>
            <button @click="closeQrModal" class="qr-close-btn">×</button>
          </div>
          <div class="qr-modal-body">
            <div v-if="qrLoading" class="qr-loading-state">
              <div class="pa-spinner"></div>
              <span>正在获取二维码...</span>
            </div>
            <div v-else-if="qrError" class="qr-error-state">
              <span class="qr-error-text">{{ qrError }}</span>
              <button @click="retryQrBind" class="pa-btn pa-btn-primary" style="margin-top:12px;">刷新二维码</button>
            </div>
            <div v-else class="qr-code-display">
              <div class="qr-img-wrap">
                <img v-if="qrCodeSrc" :src="qrCodeSrc" alt="QR Code" class="qr-img" />
                <div v-else class="qr-no-img">二维码加载失败</div>
              </div>
              <p class="qr-hint">请使用{{ qrPlatformLabel }}App扫描上方二维码</p>
              <div class="qr-countdown-row">
                <span v-if="qrCountdown > 0" class="qr-countdown">二维码有效期：{{ qrCountdown }}秒</span>
                <span v-else class="qr-expired">二维码已过期</span>
                <button @click="retryQrBind" class="qr-refresh-btn">刷新</button>
              </div>
            </div>
            <div v-if="qrPolling" class="qr-polling-hint">
              <span class="pa-spinner-sm"></span>
              <span>等待扫码中...</span>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { authFetch } from '@/api/client'
import { useWorkStore } from '@/stores/work'

interface PlatformAccount {
  id: string | null
  platform: string
  platform_label: string
  platform_uid: string | null
  platform_nickname: string | null
  platform_avatar_url: string | null
  platform_home_url: string | null
  last_synced_at: string | null
  sync_status: string
  sync_error: string | null
  works_count: number
  fans_count: number | null
  bound: boolean
}

const DEFAULT_ACCOUNTS: PlatformAccount[] = [
  { id: null, platform: 'xiaohongshu', platform_label: '小红书', platform_uid: null, platform_nickname: null, platform_avatar_url: null, platform_home_url: null, last_synced_at: null, sync_status: 'idle', sync_error: null, works_count: 0, fans_count: null, bound: false },
  { id: null, platform: 'douyin', platform_label: '抖音', platform_uid: null, platform_nickname: null, platform_avatar_url: null, platform_home_url: null, last_synced_at: null, sync_status: 'idle', sync_error: null, works_count: 0, fans_count: null, bound: false },
  { id: null, platform: 'bilibili', platform_label: 'B站', platform_uid: null, platform_nickname: null, platform_avatar_url: null, platform_home_url: null, last_synced_at: null, sync_status: 'idle', sync_error: null, works_count: 0, fans_count: null, bound: false },
]

const workStore = useWorkStore()
const accounts = ref<PlatformAccount[]>([...DEFAULT_ACCOUNTS])
const loading = ref(true)
const errorMsg = ref('')
const bindingPlatform = ref('')
const syncingAll = ref(false)

const showQrModal = ref(false)
const qrLoading = ref(false)
const qrError = ref('')
const qrCodeSrc = ref('')
const qrPlatformLabel = ref('')
const qrPlatform = ref('')
const qrTaskId = ref('')
const qrPolling = ref(false)
const qrCountdown = ref(120)

let pollTimer: ReturnType<typeof setInterval> | null = null
let countdownTimer: ReturnType<typeof setInterval> | null = null

const platformIcons: Record<string, string> = {
  xiaohongshu: '/icons/xiaohongshu-app.png',
  douyin: '/icons/douyin-app.png',
  bilibili: '/icons/bilibili-app.png',
}

const hasBoundAccounts = computed(() => accounts.value.some(a => a.bound))

async function loadAccounts() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await authFetch('/api/accounts')
    if (!res.ok) {
      const text = await res.text()
      console.error('[PlatformAccounts] loadAccounts failed:', res.status, text)
      throw new Error(`请求失败 (${res.status})`)
    }
    const data = await res.json()
    if (data.success && data.data) {
      accounts.value = data.data
    } else {
      errorMsg.value = data.message || '加载失败'
    }
  } catch (e: any) {
    console.error('[PlatformAccounts] loadAccounts error:', e)
    errorMsg.value = e.message || '网络错误'
    accounts.value = [...DEFAULT_ACCOUNTS]
  } finally {
    loading.value = false
  }
}

async function bindAccount(platform: string, label: string) {
  console.log('[PlatformAccounts] bindAccount called:', platform, label)
  bindingPlatform.value = platform
  qrPlatform.value = platform
  qrPlatformLabel.value = label
  qrLoading.value = true
  qrError.value = ''
  qrCodeSrc.value = ''
  showQrModal.value = true

  try {
    const res = await authFetch('/api/accounts/bind', {
      method: 'POST',
      body: JSON.stringify({ platform }),
    })
    if (!res.ok) {
      const text = await res.text()
      console.error('[PlatformAccounts] bind failed:', res.status, text)
      throw new Error(`绑定请求失败 (${res.status})`)
    }
    const data = await res.json()
    qrLoading.value = false
    console.log('[PlatformAccounts] bind response:', data)

    if (data.success && data.data?.task_id) {
      qrTaskId.value = data.data.task_id
      const qrCode = data.data.qr_code || {}

      if (qrCode.qr_base64) {
        qrCodeSrc.value = qrCode.qr_base64
      } else if (qrCode.qr_url) {
        qrCodeSrc.value = qrCode.qr_url
      } else if (qrCode.error) {
        qrError.value = qrCode.error
      } else {
        qrError.value = '无法获取二维码'
      }

      if (!qrError.value) {
        startQrPolling(data.data.task_id)
        startCountdown()
      }
    } else {
      qrError.value = data.message || '绑定失败'
    }
  } catch (e: any) {
    qrLoading.value = false
    qrError.value = e.message || '绑定请求失败'
    console.error('[PlatformAccounts] bindAccount error:', e)
  } finally {
    bindingPlatform.value = ''
  }
}

function retryQrBind() {
  stopQrPolling()
  stopCountdown()
  bindAccount(qrPlatform.value, qrPlatformLabel.value)
}

function closeQrModal() {
  showQrModal.value = false
  stopQrPolling()
  stopCountdown()
  qrPolling.value = false
}

function startQrPolling(taskId: string) {
  qrPolling.value = true
  stopQrPolling()
  console.log('[PlatformAccounts] start polling, taskId:', taskId)
  pollTimer = setInterval(async () => {
    try {
      const res = await authFetch(`/api/accounts/qr-status/${taskId}`)
      const data = await res.json()
      console.log('[PlatformAccounts] poll result:', data)
      if (data.success && data.data) {
        const status = data.data.status
        if (status === 'confirmed') {
          console.log('[PlatformAccounts] login confirmed!')
          stopQrPolling()
          stopCountdown()
          qrPolling.value = false
          showQrModal.value = false
          await loadAccounts()
        } else if (status === 'failed' || status === 'expired') {
          stopQrPolling()
          stopCountdown()
          qrPolling.value = false
          qrError.value = status === 'expired' ? '扫码超时，请刷新重试' : (data.data.error || '登录失败，请重试')
        }
      }
    } catch (e) {
      console.error('[PlatformAccounts] poll error:', e)
      stopQrPolling()
      qrPolling.value = false
      qrError.value = '网络异常'
    }
  }, 3000)
}

function stopQrPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startCountdown() {
  qrCountdown.value = 120
  stopCountdown()
  countdownTimer = setInterval(() => {
    qrCountdown.value--
    if (qrCountdown.value <= 0) {
      stopCountdown()
      qrError.value = '二维码已过期，请刷新'
    }
  }, 1000)
}

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

function confirmSync(account: PlatformAccount) {
  if (account.last_synced_at) {
    const last = new Date(account.last_synced_at).getTime()
    const hours = Math.floor((Date.now() - last) / 3600000)
    if (hours < 24) {
      if (!confirm(`距上次同步仅 ${hours} 小时，频繁同步可能触发平台风控。确定继续？`)) return
    }
  }
  syncAccount(account)
}

async function syncAccount(account: PlatformAccount) {
  if (!account.id) return
  account.sync_status = 'running'
  account.sync_error = null
  try {
    await authFetch(`/api/accounts/${account.id}/sync`, {
      method: 'POST',
      body: JSON.stringify({ force: true }),
    })
    startSyncPolling()
  } catch (e: any) {
    account.sync_status = 'idle'
    account.sync_error = e.message
  }
}

function startSyncPolling() {
  const timer = setInterval(async () => {
    await loadAccounts()
    if (!accounts.value.some(a => a.sync_status === 'running')) {
      clearInterval(timer)
      try { await workStore.fetchWorks() } catch {}
      const errorAccount = accounts.value.find(a => a.sync_error)
      if (errorAccount?.sync_error) {
        showToast(`${errorAccount.platform_label} 同步失败：${errorAccount.sync_error}`, 'error')
      } else {
        const syncedPlatforms = accounts.value.filter(a => a.bound && a.last_synced_at)
        if (syncedPlatforms.length > 0) {
          const names = syncedPlatforms.map(a => a.platform_label).join('、')
          showToast(`${names} 同步完成`, 'success')
        }
      }
    }
  }, 5000)
}

function showToast(message: string, type: 'success' | 'error' | 'info' = 'success') {
  const el = document.createElement('div')
  el.textContent = message
  const bgMap = { success: '#059669', error: '#dc2626', info: '#2563eb' }
  el.style.cssText = `
    position:fixed; top:24px; right:24px; z-index:99999;
    padding:12px 20px; border-radius:8px; font-size:14px; color:#fff;
    background:${bgMap[type]}; box-shadow:0 4px 12px rgba(0,0,0,0.15); transition:opacity 0.3s;
  `
  document.body.appendChild(el)
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300) }, 3000)
}

function confirmSyncAll() {
  const boundAccounts = accounts.value.filter(a => a.bound)
  const recentSync = boundAccounts.some(a => {
    if (!a.last_synced_at) return false
    return (Date.now() - new Date(a.last_synced_at).getTime()) < 86400000
  })
  if (recentSync) {
    if (!confirm('部分平台 24 小时内已同步过，频繁同步可能触发平台风控。确定继续？')) return
  }
  syncAll()
}

async function syncAll() {
  syncingAll.value = true
  try {
    await authFetch('/api/accounts/sync-all', {
      method: 'POST',
      body: JSON.stringify({ force: true }),
    })
    startSyncPolling()
  } catch (e: any) {
    errorMsg.value = e.message
  } finally {
    syncingAll.value = false
  }
}

async function unbindAccount(account: PlatformAccount) {
  if (!account.id) return
  if (!confirm(`确定解绑 ${account.platform_label}？解绑后已同步的作品数据仍保留。`)) return
  try {
    await authFetch(`/api/accounts/${account.id}`, { method: 'DELETE' })
    await loadAccounts()
  } catch (e: any) {
    errorMsg.value = e.message
  }
}

function formatFans(count: number): string {
  if (count >= 10000) return (count / 10000).toFixed(1) + 'w'
  if (count >= 1000) return (count / 1000).toFixed(1) + 'k'
  return String(count)
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  return Math.floor(diff / 86400000) + '天前'
}

onMounted(() => loadAccounts())
onUnmounted(() => {
  stopQrPolling()
  stopCountdown()
})
</script>

<style scoped>
.pa-wrap { padding: 0; }
.pa-loading {
  display: flex; align-items: center; gap: 8px;
  padding: 20px; color: #9CA3AF; font-size: 13px;
}
.pa-error-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; margin-bottom: 12px;
  background: #FEF2F2; border-radius: 8px;
  color: #EF4444; font-size: 13px;
}
.pa-spinner {
  width: 18px; height: 18px; border: 2px solid #E5E7EB;
  border-top-color: #3B6CF6; border-radius: 50%;
  animation: pa-spin 0.8s linear infinite;
}
@keyframes pa-spin { to { transform: rotate(360deg); } }
.pa-retry-btn {
  padding: 4px 10px; border: none; background: #3B6CF6;
  color: #fff; font-size: 12px; border-radius: 4px; cursor: pointer;
}
.pa-platform-list {
  display: flex; flex-direction: column; gap: 1px;
  background: #EDEDED; border-radius: 10px; overflow: hidden;
}
.pa-platform-card {
  padding: 14px 16px; background: #FFFFFF;
}
.pa-platform-row {
  display: flex; align-items: center; gap: 12px;
}
.pa-platform-icon {
  width: 36px; height: 36px; border-radius: 8px;
  background: #F3F4F6; display: flex; align-items: center;
  justify-content: center; flex-shrink: 0; overflow: hidden;
}
.pa-platform-icon img { width: 28px; height: 28px; object-fit: contain; }
.pa-platform-icon-avatar { border-radius: 50%; }
.pa-avatar-img { width: 36px !important; height: 36px !important; object-fit: cover; border-radius: 50%; }
.pa-platform-icon-text { font-size: 14px; font-weight: 600; color: #6B7280; }
.pa-platform-info { flex: 1; min-width: 0; }
.pa-platform-header { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
.pa-platform-name { color: #1A1A1A; font-size: 15px; font-weight: 500; }
.pa-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 1px 7px; font-size: 11px; border-radius: 10px; font-weight: 500;
}
.pa-badge-success { background: #ECFDF5; color: #059669; }
.pa-badge-warning { background: #FEF3C7; color: #D97706; }
.pa-badge-default { background: #F3F4F6; color: #9CA3AF; }
.pa-badge-dot { width: 5px; height: 5px; background: #10B981; border-radius: 50%; }
.pa-spinner-sm {
  width: 5px; height: 5px; border: 1.5px solid #D97706;
  border-top-color: transparent; border-radius: 50%;
  display: inline-block; animation: pa-spin 0.8s linear infinite;
}
.pa-platform-desc { color: #9CA3AF; font-size: 13px; }
.pa-sync-error { color: #EF4444; font-size: 12px; margin-top: 2px; }
.pa-platform-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.pa-btn {
  padding: 7px 12px; border: none; font-size: 13px; font-weight: 500;
  cursor: pointer; border-radius: 6px; white-space: nowrap;
  transition: opacity 0.15s;
}
.pa-btn:disabled { cursor: not-allowed; opacity: 0.6; }
.pa-btn-primary { background: #3B6CF6; color: #FFFFFF; }
.pa-btn-primary:hover:not(:disabled) { opacity: 0.85; }
.pa-btn-ghost { background: #F3F4F6; color: #6B7280; }
.pa-btn-ghost:hover { background: #E5E7EB; }
.pa-btn-lg { padding: 9px 20px; font-size: 14px; }
.pa-sync-all { margin-top: 16px; text-align: center; }
.pa-sync-warning {
  margin-top: 6px; padding-left: 48px;
  color: #D97706; font-size: 11px; line-height: 1.4;
}
.pa-sync-all-warning {
  margin: 6px 0 0; color: #D97706; font-size: 11px;
}

.qr-overlay {
  position: fixed; inset: 0; z-index: 10010;
  background: rgba(0,0,0,0.45); display: flex;
  align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
}
.qr-modal {
  background: #fff; border-radius: 16px; width: 360px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
  overflow: hidden; animation: qr-in 0.2s ease-out;
}
@keyframes qr-in { from { opacity:0; transform:scale(0.95); } to { opacity:1; transform:scale(1); } }
.qr-modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #F3F4F6;
}
.qr-modal-title { font-size: 15px; font-weight: 600; color: #1A1A1A; }
.qr-close-btn {
  width: 28px; height: 28px; border: none; background: #F3F4F6;
  border-radius: 50%; font-size: 16px; color: #6B7280;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.qr-close-btn:hover { background: #E5E7EB; }
.qr-modal-body { padding: 24px 20px; text-align: center; }
.qr-loading-state {
  display: flex; flex-direction: column; align-items: center;
  gap: 12px; padding: 20px 0; color: #9CA3AF; font-size: 13px;
}
.qr-error-state {
  display: flex; flex-direction: column; align-items: center;
  padding: 16px 0;
}
.qr-error-text { color: #EF4444; font-size: 13px; }
.qr-code-display { display: flex; flex-direction: column; align-items: center; }
.qr-img-wrap {
  width: 200px; height: 200px; border: 1px solid #E5E7EB;
  border-radius: 12px; overflow: hidden; display: flex;
  align-items: center; justify-content: center;
  background: #FAFAFA;
}
.qr-img { width: 180px; height: 180px; object-fit: contain; }
.qr-no-img { color: #9CA3AF; font-size: 12px; }
.qr-hint { margin: 14px 0 8px; color: #374151; font-size: 13px; font-weight: 500; }
.qr-countdown-row {
  display: flex; align-items: center; justify-content: center;
  gap: 12px; margin-top: 4px;
}
.qr-countdown { color: #9CA3AF; font-size: 12px; }
.qr-expired { color: #EF4444; font-size: 12px; }
.qr-refresh-btn {
  padding: 3px 10px; border: 1px solid #E5E7EB; background: #fff;
  color: #6B7280; font-size: 12px; border-radius: 4px; cursor: pointer;
}
.qr-refresh-btn:hover { background: #F9FAFB; }
.qr-polling-hint {
  display: flex; align-items: center; justify-content: center;
  gap: 6px; margin-top: 16px; color: #9CA3AF; font-size: 12px;
}
</style>