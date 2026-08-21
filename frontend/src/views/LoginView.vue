<template>
  <div class="login-page">
    <div class="login-content" :style="floatStyle">
      <div class="login-header">
        <div class="login-logo">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 180" width="40" height="36">
            <defs>
              <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
                <feDropShadow dx="0" dy="3" stdDeviation="2.5" flood-color="#000" flood-opacity="0.15"/>
              </filter>
            </defs>
            <path d="M52,86 Q36,76 30,68" stroke="#D94F44" stroke-width="11" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
            <path d="M148,86 Q164,76 170,68" stroke="#D94F44" stroke-width="11" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
            <g filter="url(#shadow)">
              <ellipse cx="26" cy="56" rx="18" ry="11" transform="rotate(-45 26 56)" fill="#E8655A"/>
              <ellipse cx="42" cy="80" rx="16" ry="10" transform="rotate(15 42 80)" fill="#E8655A"/>
            </g>
            <g filter="url(#shadow)">
              <ellipse cx="174" cy="56" rx="18" ry="11" transform="rotate(45 174 56)" fill="#E8655A"/>
              <ellipse cx="158" cy="80" rx="16" ry="10" transform="rotate(-15 158 80)" fill="#E8655A"/>
            </g>
            <ellipse cx="100" cy="105" rx="58" ry="48" fill="#E8655A" filter="url(#shadow)"/>
            <path d="M55,110 Q30,118 22,134" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
            <path d="M52,125 Q28,136 18,154" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
            <path d="M62,138 Q48,152 42,170" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
            <path d="M145,110 Q170,118 178,134" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
            <path d="M148,125 Q172,136 182,154" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
            <path d="M138,138 Q152,152 158,170" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#shadow)"/>
            <circle cx="30" cy="68" r="8" fill="#D94F44"/>
            <circle cx="170" cy="68" r="8" fill="#D94F44"/>
            <circle cx="78" cy="62" r="16" fill="white" filter="url(#shadow)"/>
            <circle cx="80" cy="62" r="8" fill="#1a1a1a"/>
            <circle cx="83" cy="59" r="3" fill="white"/>
            <circle cx="122" cy="62" r="16" fill="white" filter="url(#shadow)"/>
            <circle cx="120" cy="62" r="8" fill="#1a1a1a"/>
            <circle cx="123" cy="59" r="3" fill="white"/>
          </svg>
        </div>
        <img src="/icons/logo2.svg" alt="Logo" class="login-brand" />
      </div>

      <div v-if="activeTab === 'home' || activeTab === 'email'" class="login-main">
        <button class="login-option" @click="activeTab = 'qrcode'; initQRCode()" type="button">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/><rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3"/><path d="M21 21v.01"/><path d="M12 7v3a2 2 0 0 1-2 2H7"/><path d="M3 12h.01"/><path d="M12 3h.01"/><path d="M12 16v.01"/><path d="M16 12h1"/><path d="M21 12v.01"/><path d="M12 21v-1"/></svg>
          <span>小红书二维码登录</span>
        </button>

        <div class="login-divider"><span>或</span></div>

        <div class="login-email-section">
          <template v-if="emailStep === 'input'">
            <div class="login-input-wrapper">
              <input
                v-model="emailForm.email"
                type="email"
                class="login-input"
                placeholder="输入邮箱地址"
                @keyup.enter="handleSendCode"
                @focus="isInputFocused = true"
                @blur="isInputFocused = false"
              />
            </div>
            <button
              class="login-btn"
              :disabled="!emailForm.email || !agreedPrivacy || sendingCode"
              @click="handleSendCode"
              type="button"
            >
              {{ sendingCode ? '发送中...' : '发送验证码' }}
            </button>
            <div class="login-privacy">
              <label class="login-checkbox-label">
                <input v-model="agreedPrivacy" type="checkbox" class="login-checkbox" />
                <span>同意<span class="login-link" @click.stop="showPolicy = 'privacy'">隐私政策</span>和<span class="login-link" @click.stop="showPolicy = 'terms'">服务条款</span></span>
              </label>
            </div>
          </template>
          <template v-else>
            <div class="code-sent-to">验证码已发送至 {{ emailForm.email }}</div>
            <div class="code-boxes">
              <div v-for="i in 6" :key="i" class="code-box-wrapper">
                <input
                  :ref="el => { if (el) codeInputs[i - 1] = el as HTMLInputElement }"
                  v-model="codeDigits[i - 1]"
                  type="text"
                  class="code-box"
                  maxlength="1"
                  inputmode="numeric"
                  @input="onCodeInput(i - 1)"
                  @keydown.backspace="onCodeBackspace(i - 1, $event)"
                  @paste="onCodePaste"
                  @focus="isInputFocused = true"
                  @blur="isInputFocused = false"
                />
              </div>
            </div>
            <button
              class="login-btn"
              :disabled="codeDigits.join('').length < 6 || emailLoading"
              @click="handleEmailLogin"
              type="button"
            >
              {{ emailLoading ? '登录中...' : '验证' }}
            </button>
            <div class="code-actions">
              <button
                class="login-link"
                :disabled="countdown > 0"
                @click="handleSendCode"
                type="button"
              >
                {{ countdown > 0 ? `${countdown}s 后重发` : '重新发送' }}
              </button>
              <button class="login-link" @click="emailStep = 'input'; codeDigits = ['', '', '', '', '', '']" type="button">更换邮箱</button>
            </div>
          </template>
        </div>
      </div>

      <div v-else class="login-qrcode">
        <div v-if="workerOffline" class="qr-offline">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
          <p class="qr-offline-text">扫码服务未启动</p>
          <p class="qr-offline-hint">请在终端运行以下命令启动 Worker：</p>
          <code class="qr-offline-cmd">python -m app.account.qr_http_worker 9010</code>
          <button class="login-btn login-btn-outline" style="margin-top: 12px;" @click="generateQRCode" type="button">重试连接</button>
        </div>
        <div v-else-if="!qrCode" class="qr-placeholder">
          <div class="qr-loading">
            <svg class="qr-spin" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            <span style="margin-top: 8px; font-size: 13px; color: #94a3b8;">加载二维码中...</span>
          </div>
        </div>
        <div v-else class="qr-display">
          <img :src="qrCode.qrcode_base64" alt="小红书二维码登录" class="qr-image" />
          <div class="qr-status">
            <span v-if="qrStatus === 'pending'" class="qr-hint">打开小红书 APP 扫描二维码</span>
            <span v-else-if="qrStatus === 'scanned'" class="qr-hint qr-hint-scanned">已扫码，请在手机确认</span>
            <span v-else-if="qrStatus === 'confirmed'" class="qr-hint qr-hint-done">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -2px; margin-right: 4px;"><path d="M20 6 9 17l-5-5"/></svg>
              登录成功
            </span>
            <span v-else-if="qrStatus === 'expired'" class="qr-hint qr-hint-expired">
              二维码已过期
              <button class="login-link" @click="generateQRCode" type="button">刷新</button>
            </span>
          </div>
        </div>
        <div v-if="qrStatus === 'confirmed' && showManualInput" class="manual-input">
          <input v-model="manualNickname" type="text" class="login-input" placeholder="小红书昵称" @focus="isInputFocused = true" @blur="isInputFocused = false" />
          <input v-model="manualRedId" type="text" class="login-input" placeholder="小红书号（选填）" @focus="isInputFocused = true" @blur="isInputFocused = false" />
          <button class="login-btn" @click="bindManual" :disabled="!manualNickname || binding" type="button">
            {{ binding ? '绑定中...' : '确认绑定' }}
          </button>
        </div>
        <div class="login-back">
          <button class="login-link" @click="activeTab = 'home'; stopPolling()" type="button">返回</button>
        </div>
      </div>

      <div v-if="errorMsg" class="login-error">{{ errorMsg }}</div>
    </div>

    <Transition name="policy-fade">
      <div v-if="showPolicy" class="policy-overlay" @click.self="showPolicy = ''">
        <div class="policy-card">
          <div class="policy-header">
            <h3 class="policy-title">{{ showPolicy === 'privacy' ? '隐私政策' : '服务条款' }}</h3>
            <button class="policy-close" @click="showPolicy = ''" type="button">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="policy-body">
            <template v-if="showPolicy === 'privacy'">
              <p>更新日期：2025年1月1日</p>
              <p>欢迎使用脉冲工作室。我们非常重视您的隐私保护和个人信息保护。</p>
              <h4>一、信息收集</h4>
              <p>我们可能收集以下信息：邮箱地址（用于登录验证）、小红书账号信息（用于内容发布服务）、使用行为数据（用于优化服务体验）。</p>
              <h4>二、信息使用</h4>
              <p>收集的信息仅用于：提供和改善服务、发送服务通知、安全保障。我们不会将您的个人信息出售给第三方。</p>
              <h4>三、信息存储与安全</h4>
              <p>我们采用行业标准的安全措施保护您的信息，包括数据加密、访问控制等。数据存储在中国境内的服务器上。</p>
              <h4>四、Cookie 使用</h4>
              <p>我们使用 Cookie 和类似技术来维护会话状态、记住登录信息和分析使用情况。</p>
              <h4>五、您的权利</h4>
              <p>您有权访问、更正、删除您的个人信息，并可撤回授权同意。如需行使上述权利，请通过应用内设置或联系我们。</p>
              <h4>六、未成年人保护</h4>
              <p>我们非常注重对未成年人个人信息的保护。若您是18周岁以下的未成年人，建议在监护人指导下使用本服务。</p>
              <h4>七、政策更新</h4>
              <p>本政策可能不时更新，更新后将在应用内通知您。继续使用服务即视为同意更新后的政策。</p>
            </template>
            <template v-else>
              <p>更新日期：2025年1月1日</p>
              <p>欢迎使用脉冲工作室。请仔细阅读以下服务条款。</p>
              <h4>一、服务内容</h4>
              <p>脉冲工作室为您提供小红书内容创作与发布辅助服务，包括但不限于：热点搜索、文案生成、标题优化、自动发布等功能。</p>
              <h4>二、用户行为规范</h4>
              <p>您承诺：遵守中华人民共和国相关法律法规；不利用本服务发布违法、违规或侵权内容；不利用本服务进行任何恶意行为，包括但不限于刷量、恶意营销等。</p>
              <h4>三、知识产权</h4>
              <p>您通过本服务生成的内容，其知识产权归您所有。我们不会对您的内容主张任何权利，但有权在必要范围内处理内容以提供服务。</p>
              <h4>四、免责声明</h4>
              <p>因不可抗力、第三方服务故障等原因导致的服务中断，我们不承担责任。您使用本服务产生的法律后果由您自行承担。</p>
              <h4>五、服务变更与终止</h4>
              <p>我们有权根据业务需要变更或终止部分服务，届时将提前通知您。您有权随时停止使用本服务并注销账号。</p>
              <h4>六、争议解决</h4>
              <p>因本条款产生的争议，双方应友好协商解决；协商不成的，任何一方均可向我们所在地有管辖权的人民法院提起诉讼。</p>
            </template>
          </div>
          <div class="policy-footer">
            <button class="policy-agree-btn" @click="showPolicy = ''; agreedPrivacy = true" type="button">我已阅读并同意</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { accountApi, type QRCodeResponse } from '@/api/account'
import { authApi, saveLogin } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const SK_HAS_LOGGED_IN = 'mint_has_logged_in_before'
const SK_FIRST_LOGIN = 'mint_first_login_session'

function saveLoginAndSync(data: { token: string; refresh_token?: string; user_id: string; xhs_user_id: string; nickname: string; avatar_url: string; has_xhs_auth?: boolean; login_method?: string }) {
  saveLogin(data)
  authStore.token = data.token
  authStore.user = {
    user_id: data.user_id,
    xhs_user_id: data.xhs_user_id,
    nickname: data.nickname,
    avatar_url: data.avatar_url,
    has_xhs_auth: data.has_xhs_auth ?? !!data.xhs_user_id,
    login_method: data.login_method || '',
  }
}

function markFirstLoginAndPush() {
  if (!localStorage.getItem(SK_HAS_LOGGED_IN)) {
    sessionStorage.setItem(SK_FIRST_LOGIN, '1')
    localStorage.setItem(SK_HAS_LOGGED_IN, '1')
  }
  const redirect = (route.query.redirect as string) || sessionStorage.getItem('redirect_after_login') || '/workbench'
  sessionStorage.removeItem('redirect_after_login')
  router.push(redirect)
}

const activeTab = ref<'home' | 'email' | 'qrcode'>('home')
const errorMsg = ref('')
const isInputFocused = ref(false)
const floatStyle = ref<Record<string, string>>({})

const emailStep = ref<'input' | 'code'>('input')
const emailForm = ref({ email: '', code: '' })
const sendingCode = ref(false)
const emailLoading = ref(false)
const agreedPrivacy = ref(false)
const showPolicy = ref<'' | 'privacy' | 'terms'>('')
const countdown = ref(0)
let countdownTimer: number | null = null

const codeDigits = ref<string[]>(['', '', '', '', '', ''])
const codeInputs = ref<HTMLInputElement[]>([])

function onCodeInput(index: number) {
  const val = codeDigits.value[index]
  codeDigits.value[index] = val.replace(/[^0-9]/g, '').slice(0, 1)
  if (codeDigits.value[index] && index < 5) {
    codeInputs.value[index + 1]?.focus()
  }
  if (codeDigits.value.join('').length === 6) {
    handleEmailLogin()
  }
}

function onCodeBackspace(index: number, e: KeyboardEvent) {
  if (!codeDigits.value[index] && index > 0) {
    codeDigits.value[index - 1] = ''
    codeInputs.value[index - 1]?.focus()
    e.preventDefault()
  }
}

function onCodePaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text')?.replace(/[^0-9]/g, '').slice(0, 6) || ''
  if (text.length > 0) {
    for (let i = 0; i < 6; i++) {
      codeDigits.value[i] = text[i] || ''
    }
    const focusIdx = Math.min(text.length, 5)
    codeInputs.value[focusIdx]?.focus()
    if (text.length === 6) {
      handleEmailLogin()
    }
  }
  e.preventDefault()
}

const qrCode = ref<QRCodeResponse | null>(null)
const qrStatus = ref<'pending' | 'scanned' | 'confirmed' | 'expired'>('pending')
const qrLoading = ref(false)
const workerOffline = ref(false)
const pollTimer = ref<number | null>(null)
const showManualInput = ref(false)
const manualNickname = ref('')
const manualRedId = ref('')
const binding = ref(false)

function initQRCode() {
  if (!qrCode.value && !qrLoading.value) {
    generateQRCode()
  }
}

async function generateQRCode() {
  qrLoading.value = true
  errorMsg.value = ''
  qrCode.value = null
  qrStatus.value = 'pending'
  showManualInput.value = false
  workerOffline.value = false

  try {
    const response = await accountApi.generateQRCode()
    if (response && response.data) {
      qrCode.value = response.data
      startPolling()
    }
  } catch (e: any) {
    const detail = e.response?.data?.detail || e.message || '获取二维码失败'
    if (detail.includes('QR_WORKER_OFFLINE')) {
      workerOffline.value = true
    } else {
      errorMsg.value = detail
    }
  } finally {
    qrLoading.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer.value = window.setInterval(async () => {
    if (!qrCode.value) return
    try {
      const response = await accountApi.pollQRCode(qrCode.value.qr_id)
      if (response && response.data) {
        const data = response.data
        qrStatus.value = data.status

        if (data.qrcode_base64 && qrCode.value) {
          qrCode.value.qrcode_base64 = data.qrcode_base64
        }

        if (qrStatus.value === 'confirmed') {
          stopPolling()
          await bindAccount()
        } else if (qrStatus.value === 'expired') {
          stopPolling()
        }
      }
    } catch (_e) {
      // silent
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
  errorMsg.value = ''
  try {
    const response = await authApi.qrLogin(qrCode.value.qr_id)
    if (response && response.data) {
      saveLoginAndSync(response.data)
      markFirstLoginAndPush()
    } else {
      errorMsg.value = '登录返回数据异常'
    }
  } catch (e: any) {
    const detail = e.response?.data?.detail || ''
    if (detail.includes('need_manual')) {
      showManualInput.value = true
      errorMsg.value = '请手动输入昵称'
    } else {
      errorMsg.value = detail || e.message || '登录失败'
    }
  } finally {
    binding.value = false
  }
}

async function bindManual() {
  if (!qrCode.value || !manualNickname.value) return
  binding.value = true
  errorMsg.value = ''
  try {
    const response = await authApi.qrLoginManual(
      qrCode.value.qr_id,
      manualNickname.value,
      manualRedId.value
    )
    if (response && response.data) {
      saveLoginAndSync(response.data)
      markFirstLoginAndPush()
    }
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '绑定失败'
  } finally {
    binding.value = false
  }
}

async function handleSendCode() {
  const { email } = emailForm.value
  if (!email || !email.includes('@')) {
    errorMsg.value = '请输入正确的邮箱'
    return
  }
  localStorage.removeItem('token')
  localStorage.removeItem('refresh_token')
  sendingCode.value = true
  errorMsg.value = ''
  try {
    await authApi.sendEmailCode(email)
    emailStep.value = 'code'
    startCountdown()
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '发送验证码失败'
  } finally {
    sendingCode.value = false
  }
}

function startCountdown() {
  countdown.value = 60
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = window.setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      clearInterval(countdownTimer!)
      countdownTimer = null
    }
  }, 1000)
}

async function handleEmailLogin() {
  const email = emailForm.value.email
  const code = codeDigits.value.join('')
  if (!email || code.length < 6) {
    errorMsg.value = '请输入6位验证码'
    return
  }
  localStorage.removeItem('token')
  localStorage.removeItem('refresh_token')
  emailLoading.value = true
  errorMsg.value = ''
  try {
    const response = await authApi.emailLogin(email, code)
    if (response && response.data) {
      saveLoginAndSync(response.data)
      authStore.token = response.data.token
      authStore.user = {
        user_id: response.data.user_id,
        xhs_user_id: response.data.xhs_user_id,
        nickname: response.data.nickname,
        avatar_url: response.data.avatar_url,
        has_xhs_auth: response.data.has_xhs_auth ?? !!response.data.xhs_user_id,
        login_method: response.data.login_method || 'email',
      }
      markFirstLoginAndPush()
    }
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '登录失败'
  } finally {
    emailLoading.value = false
  }
}

onMounted(() => {
  let rafId: number | null = null
  let floatStart: number | null = null
  const entryFrom = 120
  const entryDuration = 1000
  const mountTime = performance.now()

  function tick(now: number) {
    const sinceMount = now - mountTime

    if (sinceMount < entryDuration) {
      const t = sinceMount / entryDuration
      const ease = 1 - Math.pow(1 - t, 3)
      const y = entryFrom * (1 - ease)
      floatStyle.value = {
        transform: `translateY(${y}px)`,
        opacity: String(ease),
        transition: 'none',
      }
    } else if (isInputFocused.value) {
      floatStyle.value = {
        transform: 'translateY(0)',
        opacity: '1',
        transition: 'transform 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
      }
    } else {
      if (!floatStart) floatStart = now
      const elapsed = now - floatStart
      const y = Math.sin(elapsed / 800) * 8
      floatStyle.value = {
        transform: `translateY(${y}px)`,
        opacity: '1',
        transition: 'none',
      }
    }

    rafId = requestAnimationFrame(tick)
  }

  rafId = requestAnimationFrame(tick)

  onUnmounted(() => {
    if (rafId) cancelAnimationFrame(rafId)
  })
})

onUnmounted(() => {
  stopPolling()
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
})
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #fff7ed 0%, #ffedd5 35%, #fecdd3 100%);
  padding: 20px;
}

.login-content {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  align-items: center;
  opacity: 0;
  transform: translateY(120px);
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
  margin-top: 0;
  transform: translateY(-18px);
}

.login-logo {
  width: 48px;
  height: 48px;
  margin: 0 auto;
  border-radius: 16px;
  background: #ffffff;
  border: 1.5px solid #d1d5db;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  position: relative;
  z-index: 1;
}

.login-brand {
  width: 140px;
  height: auto;
  margin-top: -8px;
}

.login-main {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.login-option {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 14px 18px;
  border: none;
  border-radius: 999px;
  background: transparent !important;
  font-size: 15px;
  font-weight: var(--weight-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.login-option::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 999px;
  padding: 1.5px;
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(255,255,255,0.2) 10%,
    rgba(255,255,255,0.5) 30%,
    rgba(255,255,255,0.9) 50%,
    rgba(255,255,255,0.5) 70%,
    rgba(255,255,255,0.2) 90%,
    transparent 100%
  );
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask-composite: exclude;
  -webkit-mask-composite: xor;
  pointer-events: none;
}

.login-option:hover::before {
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(255,255,255,0.3) 10%,
    rgba(255,255,255,0.65) 30%,
    rgba(255,255,255,1) 50%,
    rgba(255,255,255,0.65) 70%,
    rgba(255,255,255,0.3) 90%,
    transparent 100%
  );
}

.login-option span {
  text-align: center;
}

.login-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #94a3b8;
  font-size: 13px;
}

.login-divider::before {
  content: '';
  flex: 1;
  height: 3px;
  background: linear-gradient(to right,
    transparent 0%,
    rgba(148,163,184,0.1) 20%,
    rgba(148,163,184,0.35) 45%,
    rgba(148,163,184,0.6) 70%,
    rgba(148,163,184,0.7) 100%
  );
  border-radius: 2px;
}

.login-divider::after {
  content: '';
  flex: 1;
  height: 3px;
  background: linear-gradient(to left,
    transparent 0%,
    rgba(148,163,184,0.1) 20%,
    rgba(148,163,184,0.35) 45%,
    rgba(148,163,184,0.6) 70%,
    rgba(148,163,184,0.7) 100%
  );
  border-radius: 2px;
}

.login-privacy {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  line-height: 1.5;
}

.login-checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.login-checkbox {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  accent-color: #f97316;
  cursor: pointer;
  flex-shrink: 0;
}

.login-privacy .login-link {
  font-size: 12px;
}

.login-email-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.login-email-section .login-btn {
  margin-top: 12px;
}

.login-input-wrapper {
  border-radius: 999px;
  padding: 1.5px;
  background: linear-gradient(to right, transparent 0%, rgba(148, 163, 184, 0.35) 50%, transparent 100%);
}

.login-input-wrapper .login-input {
  border: none;
  background: transparent !important;
}

.login-input {
  width: 100%;
  padding: 12px 18px;
  border: none;
  border-radius: 999px;
  background: transparent !important;
  font-size: var(--text-body);
  color: var(--text-primary);
  outline: none;
  transition: box-shadow 0.2s ease;
  box-sizing: border-box;
  text-align: center;
}

.login-input-wrapper .login-input:focus {
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.15);
}

.login-input::placeholder {
  color: #94a3b8;
}

.login-input:focus {
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.15);
}

.login-btn {
  width: auto;
  min-width: 120px;
  padding: 12px 24px;
  border: none;
  border-radius: 999px;
  background: #f97316;
  color: #fff;
  font-size: var(--text-body);
  font-weight: var(--weight-medium);
  cursor: pointer;
  transition: background 0.2s ease, opacity 0.2s ease;
  align-self: center;
}

.login-btn:hover:not(:disabled) {
  background: #ea580c;
}

.login-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.login-btn-outline {
  background: transparent;
  color: #f97316;
  border: 1px solid rgba(255, 36, 66, 0.3);
}

.login-btn-outline:hover:not(:disabled) {
  background: rgba(249, 115, 22, 0.06);
}

.login-back {
  text-align: center;
  margin-top: 20px;
}

.login-link {
  background: none;
  border: none;
  color: #f97316;
  font-size: 13px;
  cursor: pointer;
  padding: 0;
}

.login-link:hover {
  text-decoration: underline;
}

.login-error {
  margin-top: 14px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(239, 68, 68, 0.08);
  color: #b91c1c;
  font-size: 13px;
  text-align: center;
}

.code-sent-to {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
  margin-bottom: 0;
}

.code-boxes {
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: nowrap;
  max-width: 320px;
  margin: 0 auto;
}.code-box-wrapper {
  border-radius: 12px;
  padding: 1.5px;
  background: linear-gradient(to bottom, rgba(148, 163, 184, 0.05), rgba(148, 163, 184, 0.3), rgba(148, 163, 184, 0.05));
  flex: 0 0 auto;
}

.code-box-wrapper .code-box {
  border: none;
}

.code-box {
  width: 44px;
  height: 50px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 12px;
  background: transparent !important;
  text-align: center;
  font-size: 24px;
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  caret-color: #f97316;
  letter-spacing: 4px;
}

.code-box-wrapper .code-box:focus {
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.15);
}

.code-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 0;
}

.code-actions .login-link:disabled {
  color: #94a3b8;
  cursor: not-allowed;
}

.code-actions .login-link:disabled:hover {
  text-decoration: none;
}

.qr-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 180px;
}

.qr-offline {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  gap: 8px;
  color: #94a3b8;
}

.qr-offline svg {
  color: #f87171;
  margin-bottom: 4px;
}

.qr-offline-text {
  font-size: 15px;
  font-weight: var(--weight-medium);
  color: var(--text-secondary);
  margin: 0;
}

.qr-offline-hint {
  font-size: 12px;
  color: #94a3b8;
  margin: 0;
}

.qr-offline-cmd {
  font-size: 11px;
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  padding: 6px 12px;
  color: #475569;
  font-family: 'Consolas', 'Monaco', monospace;
  word-break: break-all;
}

.qr-spin {
  animation: qr-spin-anim 1s linear infinite;
  color: rgba(255, 36, 66, 0.3);
}

@keyframes qr-spin-anim {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.qr-display {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.qr-image {
  width: 140px;
  height: 140px;
  border-radius: 16px;
  border: 1px solid rgba(253, 186, 116, 0.3);
}

.qr-status {
  text-align: center;
}

.qr-hint {
  font-size: 13px;
  color: var(--text-secondary);
}

.qr-hint-scanned {
  color: #f59e0b;
}

.qr-hint-done {
  color: #f97316;
}

.qr-hint-expired {
  color: #94a3b8;
}

.manual-input {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.policy-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.policy-card {
  width: 100%;
  max-width: 380px;
  max-height: 80vh;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12);
}

.policy-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.policy-title {
  font-size: 16px;
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.policy-close {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s, background 0.2s;
}

.policy-close:hover {
  color: #475569;
  background: rgba(148, 163, 184, 0.1);
}

.policy-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  font-size: 13px;
  color: #475569;
  line-height: 1.7;
}

.policy-body h4 {
  font-size: 13px;
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  margin: 14px 0 6px;
}

.policy-body h4:first-child {
  margin-top: 0;
}

.policy-body p {
  margin: 4px 0;
}

.policy-footer {
  padding: 14px 20px 18px;
  border-top: 1px solid rgba(148, 163, 184, 0.15);
  text-align: center;
}

.policy-agree-btn {
  padding: 10px 32px;
  border: none;
  border-radius: 999px;
  background: #f97316;
  color: #fff;
  font-size: var(--text-body);
  font-weight: var(--weight-medium);
  cursor: pointer;
  transition: background 0.2s;
}

.policy-agree-btn:hover {
  background: #ea580c;
}

.policy-fade-enter-active,
.policy-fade-leave-active {
  transition: opacity 0.25s ease;
}

.policy-fade-enter-active .policy-card,
.policy-fade-leave-active .policy-card {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.policy-fade-enter-from {
  opacity: 0;
}

.policy-fade-enter-from .policy-card {
  transform: translateY(20px) scale(0.97);
  opacity: 0;
}

.policy-fade-leave-to {
  opacity: 0;
}

.policy-fade-leave-to .policy-card {
  transform: translateY(10px) scale(0.98);
  opacity: 0;
}

</style>