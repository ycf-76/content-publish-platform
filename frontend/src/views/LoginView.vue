<template>
  <div class="login-page">
    <div class="login-container mint-glass">
      <div class="login-header">
        <div class="login-logo">
          <div class="login-logo-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
              <path d="M5 3v4"/>
              <path d="M19 17v4"/>
              <path d="M3 5h4"/>
              <path d="M17 19h4"/>
            </svg>
          </div>
          <span class="login-logo-text">灵犀工坊</span>
        </div>
        <h1 class="login-title">登录小红书账号</h1>
        <p class="login-desc">扫码登录小红书账号，开始智能创作之旅</p>
      </div>

      <div class="login-content">
        <div class="qrcode-section">
          <div v-if="!qrCode" class="qrcode-placeholder">
            <button class="mint-btn mint-btn-primary" @click="generateQRCode" :disabled="loading">
              <i data-lucide="qr-code" style="width:18px;height:18px;"></i>
              {{ loading ? '生成中...' : '生成二维码' }}
            </button>
          </div>

          <div v-else class="qrcode-display">
            <img :src="qrCode.qrcode_base64" alt="小红书登录二维码" class="qrcode-image" />
            <div class="qrcode-status">
              <div v-if="qrStatus === 'pending'" class="status-pending">
                <i data-lucide="smartphone" style="width:20px;height:20px;"></i>
                <span>请使用小红书APP扫码登录</span>
              </div>
              <div v-else-if="qrStatus === 'scanned'" class="status-scanned">
                <span class="mint-status-dot" style="background:#F59E0B;"></span>
                <span>已扫码，请在手机上确认登录</span>
              </div>
              <div v-else-if="qrStatus === 'confirmed'" class="status-confirmed">
                <span class="mint-status-dot" style="background:#FF2442;"></span>
                <span>登录成功，正在跳转...</span>
              </div>
              <div v-else-if="qrStatus === 'expired'" class="status-expired">
                <i data-lucide="refresh-cw" style="width:20px;height:20px;"></i>
                <span>二维码已过期，点击刷新</span>
                <button class="mint-btn mint-btn-ghost" @click="generateQRCode">刷新二维码</button>
              </div>
            </div>

            <div v-if="qrStatus === 'confirmed' && showManualInput" class="manual-input">
              <p class="manual-hint">自动获取用户信息失败，请手动输入：</p>
              <div class="mint-form-group">
                <label class="mint-label">昵称 *</label>
                <input
                  v-model="manualNickname"
                  type="text"
                  class="mint-input"
                  placeholder="请输入小红书昵称"
                />
              </div>
              <div class="mint-form-group">
                <label class="mint-label">小红书号（选填）</label>
                <input
                  v-model="manualRedId"
                  type="text"
                  class="mint-input"
                  placeholder="请输入小红书号"
                />
              </div>
              <button class="mint-btn mint-btn-primary" @click="bindManual" :disabled="!manualNickname || binding">
                {{ binding ? '绑定中...' : '确认绑定' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="error" class="login-error">
        <i data-lucide="alert-circle" style="width:18px;height:18px;"></i>
        <span>{{ error }}</span>
      </div>

      <div class="login-footer">
        <p>登录即表示同意 <a href="#">服务条款</a> 和 <a href="#">隐私政策</a></p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { createIcons, icons } from 'lucide'
import { accountApi, type QRCodeResponse } from '@/api/account'
import { authApi, saveLogin } from '@/api/auth'

const router = useRouter()

// 首次登录标记：localStorage 记录是否曾经登录过，sessionStorage 作为一次性入场券
const SK_HAS_LOGGED_IN = 'mint_has_logged_in_before'
const SK_FIRST_LOGIN = 'mint_first_login_session'

// 登录成功后统一跳转：首次登录时设置一次性入场券，工作台读后即清
function markFirstLoginAndPush() {
  if (!localStorage.getItem(SK_HAS_LOGGED_IN)) {
    // 首次登录 → 设置一次性入场券
    sessionStorage.setItem(SK_FIRST_LOGIN, '1')
    localStorage.setItem(SK_HAS_LOGGED_IN, '1')
  }
  router.push('/workbench')
}

const loading = ref(false)
const binding = ref(false)
const error = ref('')

const qrCode = ref<QRCodeResponse | null>(null)
const qrStatus = ref<'pending' | 'scanned' | 'confirmed' | 'expired'>('pending')
const pollTimer = ref<number | null>(null)
const showManualInput = ref(false)

const manualNickname = ref('')
const manualRedId = ref('')

function initIcons() {
  createIcons({ icons })
}

async function generateQRCode() {
  loading.value = true
  error.value = ''
  qrCode.value = null
  qrStatus.value = 'pending'
  showManualInput.value = false

  try {
    const response = await accountApi.generateQRCode()
    console.log('QR Code response:', response)
    if (response && response.data) {
      qrCode.value = response.data
      startPolling()
    }
  } catch (e: any) {
    console.error('Generate QR error:', e)
    error.value = e.response?.data?.detail || e.message || '生成二维码失败，请重试'
  } finally {
    loading.value = false
    setTimeout(() => {
      initIcons()
    }, 0)
  }
}

function startPolling() {
  stopPolling()

  pollTimer.value = window.setInterval(async () => {
    if (!qrCode.value) return

    try {
      const response = await accountApi.pollQRCode(qrCode.value.qr_id)
      console.log('Poll response:', response)
      if (response && response.data) {
        const status = response.data.status
        console.log('QR status:', status)
        qrStatus.value = status

        if (status === 'confirmed') {
          stopPolling()
          await bindAccount()
        } else if (status === 'scanned') {
          console.log('User has scanned, waiting for confirmation...')
        } else if (status === 'expired') {
          stopPolling()
          error.value = '二维码已过期，请重新生成'
        } else if (status === 'pending' && response.data.qrcode_base64) {
          qrCode.value = { ...qrCode.value, qrcode_base64: response.data.qrcode_base64 }
        }
      }
    } catch (e: any) {
      console.error('Poll error:', e)
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

async function bindAccount() {
  if (!qrCode.value) return

  binding.value = true
  error.value = ''

  try {
    const response = await authApi.qrLogin(qrCode.value.qr_id)
    console.log('QR login response:', response)
    if (response && response.data) {
      saveLogin(response.data)
      markFirstLoginAndPush()
    }
  } catch (e: any) {
    console.error('QR login error:', e)
    const detail = e.response?.data?.detail || ''
    if (detail.includes('need_manual')) {
      showManualInput.value = true
      error.value = '自动获取用户信息失败，请手动输入'
    } else {
      error.value = detail || e.message || '登录失败，请重试'
    }
  } finally {
    binding.value = false
    setTimeout(() => {
      initIcons()
    }, 0)
  }
}

async function bindManual() {
  if (!qrCode.value || !manualNickname.value) return

  binding.value = true
  error.value = ''

  try {
    const response = await authApi.qrLoginManual(
      qrCode.value.qr_id,
      manualNickname.value,
      manualRedId.value
    )
    console.log('QR login manual response:', response)
    if (response && response.data) {
      saveLogin(response.data)
      markFirstLoginAndPush()
    }
  } catch (e: any) {
    console.error('QR login manual error:', e)
    error.value = e.response?.data?.detail || e.message || '登录失败，请重试'
  } finally {
    binding.value = false
  }
}

onMounted(() => {
  initIcons()
  // 页面加载即自动获取二维码，无需手动点击
  generateQRCode()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #F0FDF4 0%, #ECFDF5 100%);
  padding: 20px;
}

.login-container {
  width: 100%;
  max-width: 480px;
  padding: 40px;
  border-radius: 20px;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 24px;
}

.login-logo-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: var(--mint-gradient-3d, linear-gradient(135deg, #ECFDF5 0%, #A7F3D0 22%, #6EE7B7 50%, #34D399 78%, #059669 100%));
  box-shadow: 0 4px 14px rgba(16, 185, 129, 0.30);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.login-logo-text {
  font-family: 'LXGW WenKai', 'PingFang SC', cursive;
  font-size: 20px;
  font-weight: 700;
  color: #111827;
  letter-spacing: 1px;
}

.login-title {
  font-size: 36px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 8px;
}

.login-desc {
  font-size: 15px;
  color: #6B7280;
}

.login-content {
  margin-bottom: 24px;
}

.qrcode-section {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.qrcode-placeholder {
  padding: 60px 0;
}

.qrcode-display {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}

.qrcode-image {
  width: 256px;
  height: 256px;
  border-radius: 12px;
  border: 2px solid rgba(255, 36, 66, 0.2);
}

.qrcode-status {
  text-align: center;
}

.status-pending,
.status-scanned,
.status-confirmed,
.status-expired {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 12px;
  font-size: 15px;
}

.status-pending {
  background: rgba(255, 36, 66, 0.1);
  color: #FF2442;
}

.status-scanned {
  background: rgba(245, 158, 11, 0.1);
  color: #92400E;
}

.status-confirmed {
  background: rgba(255, 36, 66, 0.1);
  color: #FF2442;
}

.status-expired {
  flex-direction: column;
  gap: 12px;
  background: rgba(239, 68, 68, 0.1);
  color: #991B1B;
}

.manual-input {
  width: 100%;
  padding: 20px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.5);
  margin-top: 16px;
}

.manual-hint {
  font-size: 14px;
  color: #6B7280;
  margin-bottom: 16px;
}

.login-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.1);
  color: #991B1B;
  font-size: 14px;
  margin-bottom: 24px;
}

.login-footer {
  text-align: center;
}

.login-footer p {
  font-size: 13px;
  color: #6B7280;
}

.login-footer a {
  color: #FF2442;
  text-decoration: none;
}

.login-footer a:hover {
  text-decoration: underline;
}
</style>