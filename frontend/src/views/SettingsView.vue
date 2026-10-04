1<template>
  <div style="position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,0.25);backdrop-filter:blur(2px);display:flex;align-items:center;justify-content:center;" @click.self="close">
    <div style="width:900px;max-width:92vh;height:620px;max-height:85vh;background:#FFFFFF;border-radius:16px;display:flex;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.15);">
      <div style="width:220px;flex-shrink:0;background:#F9FAFB;display:flex;flex-direction:column;border-right:1px solid #EDEDED;">
        <div class="settings-avatar-container" style="padding:16px 14px 12px;border-bottom:1px solid #EDEDED;display:flex;flex-direction:column;align-items:center;gap:6px;position:relative;">
          <div
            style="cursor:pointer;position:relative;"
            @click="userDropdownOpen = !userDropdownOpen"
          >
            <img
              v-if="authStore.user?.avatar_url"
              :src="authStore.user.avatar_url"
              alt="头像"
              style="width:48px;height:48px;border-radius:50%;object-fit:cover;border:2px solid #E5E7EB;transition:border-color 0.2s;"
              @mouseenter="($event.target as HTMLElement).style.borderColor='#3B6CF6'"
              @mouseleave="($event.target as HTMLElement).style.borderColor='#E5E7EB'"
            />
            <img
              v-else
              src="/images/avatar/@man.svg"
              alt="默认头像"
              style="width:48px;height:48px;border-radius:50%;object-fit:cover;border:2px solid #E5E7EB;transition:border-color 0.2s;"
              @mouseenter="($event.target as HTMLElement).style.borderColor='#3B6CF6'"
              @mouseleave="($event.target as HTMLElement).style.borderColor='#E5E7EB'"
            />
          </div>
          <span v-if="authStore.user" style="color:#1A1A1A;font-size:13px;font-weight:600;margin:0;">{{ authStore.user.nickname || '用户' }}</span>

          <transition name="settings-dropdown">
            <div
              v-if="userDropdownOpen && authStore.user"
              style="position:absolute;top:100%;left:50%;transform:translateX(-50%);margin-top:8px;background:#FFFFFF;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,0.15);min-width:180px;z-index:10;overflow:hidden;"
              @click.stop
            >
              <div style="padding:12px 16px;border-bottom:1px solid #F3F4F6;">
                <div style="color:#1A1A1A;font-size:14px;font-weight:600;margin-bottom:2px;">{{ authStore.user.nickname || '未设置' }}</div>
                <div style="color:#9CA3AF;font-size:12px;">{{ loginMethodLabel }}</div>
              </div>
              <button
                @click="handleLogout"
                style="display:flex;align-items:center;gap:8px;width:100%;padding:10px 16px;border:none;background:transparent;color:#EF4444;font-size:13px;cursor:pointer;text-align:left;transition:background 0.15s;"
                onmouseover="this.style.background='#FEF2F2'" onmouseout="this.style.background='transparent'"
              >
                <LogOut :size="14" /> 退出登录
              </button>
            </div>
          </transition>
        </div>
        <nav style="flex:1;padding:10px 8px 0;display:flex;flex-direction:column;gap:2px;">
          <button v-for="sec in sections" :key="sec.key"
            style="display:flex;align-items:center;gap:10px;padding:9px 11px;border:none;background:transparent;color:#4B4B4B;font-size:13px;cursor:pointer;border-radius:8px;text-align:left;width:100%;"
            :style="{ background: activeSection === sec.key ? '#E0E0E0' : 'transparent', color: '#4B4B4B', fontWeight: activeSection === sec.key ? 600 : 400 }"
            @click="activeSection = sec.key">
            {{ sec.label }}
          </button>
        </nav>
        <div style="padding:10px 8px 12px;border-top:1px solid #EDEDED;">
          <button @click="close" style="display:flex;align-items:center;gap:8px;padding:7px 11px;border:none;background:transparent;color:#9A9A9A;font-size:12px;cursor:pointer;border-radius:8px;width:100%;">
            返回工作台
          </button>
        </div>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;min-width:0;">
        <div style="padding:16px 20px 0;flex-shrink:0;">
          <h2 style="margin:0 0 2px;color:#1A1A1A;font-size:18px;font-weight:600;">{{ currentTitle }}</h2>
          <p style="margin:0;color:#9A9A9A;font-size:13px;">{{ currentDesc }}</p>
        </div>
        <div style="flex:1;padding:12px 20px 20px;overflow-y:auto;min-height:0;">
          <div v-if="childError" style="color:#EF4444;padding:20px;background:rgba(239,68,68,0.08);border-radius:8px;font-size:var(--text-sm);word-break:break-all;">
            {{ childError }}
          </div>
          <div v-else-if="activeSection === 'profile'" style="color:#374151;">
            <CreatorProfile />
          </div>
          <div v-else-if="activeSection === 'agents'" style="color:#374151;">
            <div class="settings-section-banner">
              <img src="/images/setting_images/agents-banner.png" alt="智能体管理" @error="($event.target as HTMLElement).style.display='none'" />
            </div>
            <AgentManager />
          </div>
          <div v-else-if="activeSection === 'wechat'">
            <img src="/images/setting_images/image-100-2.png" alt="自动化办公" style="width:100%;height:auto;display:block;border-radius:12px;margin-bottom:16px;" />

            <h3 style="margin:0 0 12px;color:#1A1A1A;font-size:14px;font-weight:600;">连接你的通讯工具，即可开始使用</h3>

            <div style="display:flex;flex-direction:column;gap:1px;background:#EDEDED;border-radius:10px;overflow:hidden;">
              <div style="display:flex;align-items:center;gap:12px;padding:14px 16px;background:#FFFFFF;border-bottom:1px solid #EDEDED;">
                <img src="/icons/feishu-app.svg" alt="飞书" style="width:32px;height:32px;border-radius:6px;" />
                <div style="flex:1;min-width:0;">
                  <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">
                    <span style="color:#1A1A1A;font-size:15px;font-weight:500;">飞书</span>
                    <span v-if="feishuStatus.connected" style="display:inline-flex;align-items:center;gap:4px;padding:1px 7px;background:#ECFDF5;color:#059669;font-size:11px;border-radius:10px;font-weight:500;">
                      <span style="width:5px;height:5px;background:#10B981;border-radius:50%;"></span>已连接
                    </span>
                    <span v-else-if="feishuStatus.loading" style="display:inline-flex;align-items:center;gap:4px;padding:1px 7px;background:#FEF3C7;color:#D97706;font-size:11px;border-radius:10px;font-weight:500;">
                      <span class="ao-spin" style="width:5px;height:5px;border:1.5px solid #D97706;border-top-color:transparent;border-radius:50%;display:inline-block;"></span>连接中
                    </span>
                  </div>
                  <div style="color:#9CA3AF;font-size:13px;">{{ feishuOAuthStatus.connected ? `已授权：${feishuOAuthStatus.account}` : '先授权账号，智能体才能找到你的 Wiki 和 Doc' }}</div>
                </div>
                <button v-if="!feishuOAuthStatus.connected && !feishuOAuthStatus.loading"
                  @click="bindFeishuAccount"
                  style="padding:7px 12px;border:none;background:#3B6CF6;color:#FFFFFF;font-size:13px;font-weight:500;cursor:pointer;border-radius:6px;white-space:nowrap;">授权 Wiki/Doc</button>
                <button v-else-if="feishuOAuthStatus.loading"
                  disabled
                  style="padding:7px 12px;border:none;background:#9CA3AF;color:#FFFFFF;font-size:13px;font-weight:500;cursor:not-allowed;border-radius:6px;white-space:nowrap;">授权中...</button>
                <button v-else
                  @click="unbindFeishuAccount"
                  style="padding:7px 12px;border:none;background:#F3F4F6;color:#6B7280;font-size:13px;font-weight:500;cursor:pointer;border-radius:6px;white-space:nowrap;">解除授权</button>
                <button v-if="!feishuStatus.connected && !feishuStatus.loading"
                  @click="toggleBot('feishu', true)"
                  style="padding:7px 18px;border:none;background:#3B6CF6;color:#FFFFFF;font-size:13px;font-weight:500;cursor:pointer;border-radius:6px;transition:opacity 0.15s;"
                  onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">去绑定</button>
                <button v-else-if="feishuStatus.loading"
                  disabled
                  style="padding:7px 18px;border:none;background:#9CA3AF;color:#FFFFFF;font-size:13px;font-weight:500;cursor:not-allowed;border-radius:6px;">连接中...</button>
                <button v-else
                  @click="toggleBot('feishu', false)"
                  style="padding:7px 18px;border:none;background:#F3F4F6;color:#6B7280;font-size:13px;font-weight:500;cursor:pointer;border-radius:6px;transition:background 0.15s;"
                  onmouseover="this.style.background='#E5E7EB'" onmouseout="this.style.background='#F3F4F6'">断开</button>
              </div>

              <div style="display:flex;align-items:center;gap:12px;padding:14px 16px;background:#FFFFFF;border-bottom:1px solid #EDEDED;">
                <img src="/icons/wechat-app.svg" alt="微信" style="width:32px;height:32px;border-radius:6px;" />
                <div style="flex:1;min-width:0;">
                  <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">
                    <span style="color:#1A1A1A;font-size:15px;font-weight:500;">微信</span>
                    <span v-if="wechatStatus.connected" style="display:inline-flex;align-items:center;gap:4px;padding:1px 7px;background:#ECFDF5;color:#059669;font-size:11px;border-radius:10px;font-weight:500;">
                      <span style="width:5px;height:5px;background:#10B981;border-radius:50%;"></span>已连接
                    </span>
                    <span v-else-if="wechatStatus.loading" style="display:inline-flex;align-items:center;gap:4px;padding:1px 7px;background:#FEF3C7;color:#D97706;font-size:11px;border-radius:10px;font-weight:500;">
                      <span class="ao-spin" style="width:5px;height:5px;border:1.5px solid #D97706;border-top-color:transparent;border-radius:50%;display:inline-block;"></span>{{ wechatStatus.statusLabel }}
                    </span>
                  </div>
                  <div style="color:#9CA3AF;font-size:13px;">{{ wechatStatus.connected ? wechatStatus.account : '随时询问问题，快速获取帮助' }}</div>
                </div>
                <button v-if="!wechatStatus.connected && !wechatStatus.loading"
                  @click="toggleBot('wechat', true)"
                  style="padding:7px 18px;border:none;background:#3B6CF6;color:#FFFFFF;font-size:13px;font-weight:500;cursor:pointer;border-radius:6px;transition:opacity 0.15s;"
                  onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">去绑定</button>
                <button v-else-if="wechatStatus.loading"
                  disabled
                  style="padding:7px 18px;border:none;background:#9CA3AF;color:#FFFFFF;font-size:13px;font-weight:500;cursor:not-allowed;border-radius:6px;">{{ wechatStatus.statusLabel }}...</button>
                <button v-else
                  @click="toggleBot('wechat', false)"
                  style="padding:7px 18px;border:none;background:#F3F4F6;color:#6B7280;font-size:13px;font-weight:500;cursor:pointer;border-radius:6px;transition:background 0.15s;"
                  onmouseover="this.style.background='#E5E7EB'" onmouseout="this.style.background='#F3F4F6'">断开</button>
              </div>

              <div v-if="wechatQrCode" style="display:flex;flex-direction:column;align-items:center;padding:16px;background:#FFFFFF;border-bottom:1px solid #EDEDED;">
                <p style="margin:0 0 10px;color:#6B7280;font-size:13px;">请用微信扫描下方二维码登录</p>
                <img :src="wechatQrCode" alt="微信登录二维码" style="width:180px;height:180px;border-radius:8px;border:1px solid #E5E7EB;" />
                <p style="margin:8px 0 0;color:#9CA3AF;font-size:12px;">扫码后将在手机微信上确认登录</p>
              </div>

              <div style="display:flex;align-items:center;gap:12px;padding:14px 16px;background:#FAFAFA;border-bottom:1px solid #EDEDED;opacity:0.55;">
                <div style="width:32px;height:32px;border-radius:6px;background:#E5E7EB;display:flex;align-items:center;justify-content:center;color:#6B7280;font-weight:bold;font-size:11px;">企微</div>
                <div style="flex:1;min-width:0;">
                  <div style="color:#374151;font-size:14px;font-weight:500;margin-bottom:2px;">企业微信</div>
                  <div style="color:#9CA3AF;font-size:12px;">企业微信支持即将上线</div>
                </div>
                <span style="padding:5px 14px;color:#9CA3AF;font-size:12px;">即将上线</span>
              </div>

              <div style="display:flex;align-items:center;gap:12px;padding:14px 16px;background:#FAFAFA;opacity:0.55;">
                <div style="width:32px;height:32px;border-radius:6px;background:#E5E7EB;display:flex;align-items:center;justify-content:center;color:#6B7280;font-weight:bold;font-size:11px;">钉钉</div>
                <div style="flex:1;min-width:0;">
                  <div style="color:#374151;font-size:14px;font-weight:500;margin-bottom:2px;">钉钉</div>
                  <div style="color:#9CA3AF;font-size:12px;">钉钉支持即将上线</div>
                </div>
                <span style="padding:5px 14px;color:#9CA3AF;font-size:12px;">即将上线</span>
              </div>
            </div>
          </div>
          <div v-else-if="activeSection === 'plugins'" style="color:#374151;">
            <img src="/images/setting_images/image-102-2.png" alt="插件管理" style="width:100%;height:auto;display:block;border-radius:12px;margin-bottom:16px;" />

            <PluginDetailView
              v-if="selectedPlugin"
              :plugin="selectedPlugin"
              @back="selectedPlugin = null"
            />
            <template v-else>
              <p>插件管理区域（加载中...）</p>
              <PluginManagerInline @select-plugin="selectedPlugin = $event" />
            </template>
          </div>
          <div v-else-if="activeSection === 'skills'" style="color:#374151;">
            <div class="settings-section-banner">
              <img src="/images/setting_images/skills-banner.png" alt="Skills 技能" @error="($event.target as HTMLElement).style.display='none'" />
            </div>
            <p>Skills 技能区域（加载中...）</p>
            <SkillsManager />
          </div>
          <div v-else-if="activeSection === 'accounts'" style="color:#374151;">
            <PlatformAccounts />
          </div>
          <div v-else-if="activeSection === 'config'" style="color:#374151;">
            <p>模型配置区域（加载中...）</p>
            <ConfigPage />
          </div>
          <div v-else-if="activeSection === 'display'" style="color:#374151;">
            <h3 style="margin:0 0 6px;color:#1A1A1A;font-size:14px;font-weight:600;">流式输出速度</h3>
            <p style="margin:0 0 16px;color:#9CA3AF;font-size:13px;">调节 AI 回复的逐字显示速度。改完即时生效，无需刷新。</p>

            <div style="display:flex;flex-direction:column;gap:16px;">
              <div style="background:#F9FAFB;border-radius:10px;padding:14px 16px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                  <label style="font-size:13px;font-weight:500;color:#374151;">显示延迟</label>
                  <span style="font-size:12px;color:#6B7280;font-variant-numeric:tabular-nums;">{{ streamSpeed.targetLag.value.toFixed(2) }}s</span>
                </div>
                <input type="range" :min="streamSpeedBounds.targetLag.min" :max="streamSpeedBounds.targetLag.max" :step="streamSpeedBounds.targetLag.step" v-model.number="streamSpeed.targetLag.value"
                  style="width:100%;accent-color:#3B6CF6;" />
                <div style="display:flex;justify-content:space-between;margin-top:4px;">
                  <span style="font-size:11px;color:#9CA3AF;">更跟手</span>
                  <span style="font-size:11px;color:#9CA3AF;">打字机</span>
                </div>
              </div>

              <div style="background:#F9FAFB;border-radius:10px;padding:14px 16px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                  <label style="font-size:13px;font-weight:500;color:#374151;">最慢速度</label>
                  <span style="font-size:12px;color:#6B7280;font-variant-numeric:tabular-nums;">{{ streamSpeed.minCps.value }} 字/秒</span>
                </div>
                <input type="range" :min="streamSpeedBounds.minCps.min" :max="streamSpeedBounds.minCps.max" :step="streamSpeedBounds.minCps.step" v-model.number="streamSpeed.minCps.value"
                  style="width:100%;accent-color:#3B6CF6;" />
              </div>

              <div style="background:#F9FAFB;border-radius:10px;padding:14px 16px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                  <label style="font-size:13px;font-weight:500;color:#374151;">最快速度</label>
                  <span style="font-size:12px;color:#6B7280;font-variant-numeric:tabular-nums;">{{ streamSpeed.maxCps.value }} 字/秒</span>
                </div>
                <input type="range" :min="streamSpeedBounds.maxCps.min" :max="streamSpeedBounds.maxCps.max" :step="streamSpeedBounds.maxCps.step" v-model.number="streamSpeed.maxCps.value"
                  style="width:100%;accent-color:#3B6CF6;" />
              </div>

              <div style="background:#F9FAFB;border-radius:10px;padding:14px 16px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                  <label style="font-size:13px;font-weight:500;color:#374151;">渲染帧间隔</label>
                  <span style="font-size:12px;color:#6B7280;font-variant-numeric:tabular-nums;">{{ streamSpeed.frameMs.value }}ms</span>
                </div>
                <input type="range" :min="streamSpeedBounds.frameMs.min" :max="streamSpeedBounds.frameMs.max" :step="streamSpeedBounds.frameMs.step" v-model.number="streamSpeed.frameMs.value"
                  style="width:100%;accent-color:#3B6CF6;" />
                <div style="display:flex;justify-content:space-between;margin-top:4px;">
                  <span style="font-size:11px;color:#9CA3AF;">更流畅</span>
                  <span style="font-size:11px;color:#9CA3AF;">省性能</span>
                </div>
              </div>

              <div style="display:flex;gap:8px;align-items:center;">
                <button @click="streamSpeed.reset()"
                  style="padding:7px 14px;border:1px solid #E5E7EB;background:#FFFFFF;color:#6B7280;font-size:13px;cursor:pointer;border-radius:6px;transition:all 0.15s;"
                  onmouseover="this.style.borderColor='#3B6CF6';this.style.color='#3B6CF6'" onmouseout="this.style.borderColor='#E5E7EB';this.style.color='#6B7280'">
                  恢复默认
                </button>
                <span style="font-size:12px;color:#9CA3AF;">默认：延迟 0.15s · 最慢 120 · 最快 4800 · 帧间隔 16ms</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onUnmounted, onErrorCaptured, defineAsyncComponent, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { LogOut } from 'lucide-vue-next'
import { useStreamSpeed, streamSpeedBounds } from '@/components/chat/composables/useStreamSpeed'

const authStore = useAuthStore()
const userDropdownOpen = ref(false)
const streamSpeed = useStreamSpeed()

const AgentManager = defineAsyncComponent(() => import('@/components/settings/AgentManager.vue'))
const CreatorProfile = defineAsyncComponent(() => import('@/components/settings/CreatorProfile.vue'))
const PlatformAccounts = defineAsyncComponent(() => import('@/components/settings/PlatformAccounts.vue'))
const ConfigPage = defineAsyncComponent(() => import('@/components/workbench/ConfigPage.vue'))
const PluginManagerInline = defineAsyncComponent(() => import('@/components/settings/PluginManagerInline.vue'))
const PluginDetailView = defineAsyncComponent(() => import('@/components/settings/PluginDetailView.vue'))
const SkillsManager = defineAsyncComponent(() => import('@/components/settings/SkillsManager.vue'))
import type { Plugin } from '@/api/plugins'

const emit = defineEmits<{ close: [] }>()

const childError = ref('')
const selectedPlugin = ref<Plugin | null>(null)

interface BotStatus {
  connected: boolean
  loading: boolean
  account: string
  statusLabel: string
}

const wechatStatus = reactive<BotStatus>({
  connected: false,
  loading: false,
  account: '',
  statusLabel: '',
})

const wechatQrCode = ref<string>('')

const feishuStatus = reactive<BotStatus>({
  connected: false,
  loading: false,
  account: '',
  statusLabel: '',
})

interface FeishuOAuthStatus {
  connected: boolean
  loading: boolean
  account: string
}

const feishuOAuthStatus = reactive<FeishuOAuthStatus>({
  connected: false,
  loading: false,
  account: '',
})

let wechatPollTimer: ReturnType<typeof setInterval> | null = null
let feishuPollTimer: ReturnType<typeof setInterval> | null = null

onErrorCaptured((err, instance, info) => {
  console.error('[SettingsView] ERROR CAPTURED:', err, info)
  childError.value = String(err)
  return false
})

async function apiFetch(path: string, opts?: RequestInit) {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${path}`, { headers, ...opts })
  return res.json()
}

async function loadFeishuOAuthStatus() {
  try {
    const r = await apiFetch('/api/feishu/oauth/status')
    if (r.success && r.data) {
      feishuOAuthStatus.connected = !!r.data.connected
      feishuOAuthStatus.account = r.data.account || ''
    }
  } catch {}
}

async function bindFeishuAccount() {
  feishuOAuthStatus.loading = true
  try {
    const r = await apiFetch('/api/feishu/oauth/authorize')
    if (!r.success || !r.authorize_url) {
      throw new Error(r.detail || r.error || '无法生成飞书授权链接')
    }
    window.location.href = r.authorize_url
  } catch (e: any) {
    feishuOAuthStatus.loading = false
    alert(e.message || '飞书授权启动失败')
  }
}

async function unbindFeishuAccount() {
  if (!confirm('解除授权后，智能体将不能访问你的飞书 Wiki 和 Doc，确定继续吗？')) return
  try {
    await apiFetch('/api/feishu/oauth/connection', { method: 'DELETE' })
    feishuOAuthStatus.connected = false
    feishuOAuthStatus.account = ''
  } catch (e: any) {
    alert(e.message || '解除授权失败')
  }
}

async function toggleBot(type: 'wechat' | 'feishu', enable: boolean) {
  const apiBase = type === 'wechat' ? '/api/wechat' : '/api/feishu'
  const statusObj = type === 'wechat' ? wechatStatus : feishuStatus

  if (enable) {
    statusObj.loading = true
    statusObj.statusLabel = type === 'wechat' ? '启动中' : '连接中'

    try {
      const r = await apiFetch(`${apiBase}/start`, { method: 'POST' })
      if (r.success) {
        if (type === 'wechat') {
          startWechatPolling()
        } else {
          startFeishuPolling()
        }
      } else {
        statusObj.loading = false
        alert(r.message || r.detail || `${type === 'wechat' ? '微信' : '飞书'}连接失败`)
      }
    } catch (e: any) {
      statusObj.loading = false
      alert(e.message || '网络错误')
    }
  } else {
    try {
      await apiFetch(`${apiBase}/stop`, { method: 'POST' })
    } catch {}
    stopBotTimers(type)
    statusObj.connected = false
    statusObj.loading = false
    statusObj.account = ''
    statusObj.statusLabel = ''
    if (type === 'wechat') wechatQrCode.value = ''
  }
}

async function fetchWechatQrCode() {
  try {
    const r = await apiFetch('/api/wechat/qrcode')
    if (r.success && r.data && r.data.qrcode) {
      wechatQrCode.value = r.data.qrcode
    }
  } catch {}
}

async function pollWechatStatus() {
  try {
    const r = await apiFetch('/api/wechat/status')
    if (!r.success || !r.data) return
    const d = r.data
    if (d.status === 'logged_in') {
      wechatStatus.connected = true
      wechatStatus.loading = false
      wechatStatus.account = d.wxid || d.nickname || '已登录'
      wechatStatus.statusLabel = ''
      wechatQrCode.value = ''
      enableAgentBridge('wechat')
    } else if (d.status === 'waiting_qr') {
      wechatStatus.loading = true
      wechatStatus.statusLabel = '等待扫码'
      if (d.qr_code_base64) {
        wechatQrCode.value = d.qr_code_base64
      } else if (!wechatQrCode.value) {
        fetchWechatQrCode()
      }
    } else if (d.status === 'error') {
      wechatStatus.loading = false
      wechatStatus.statusLabel = ''
      stopWechatPolling()
    } else {
      wechatStatus.statusLabel = d.status === 'starting' ? '启动中...' : d.status === 'scanned' ? '已扫码' : '连接中...'
    }
  } catch {}
}

async function pollFeishuStatus() {
  try {
    const r = await apiFetch('/api/feishu/status')
    if (!r.success || !r.data) return
    const d = r.data
    if (d.status === 'running' || d.is_running) {
      feishuStatus.connected = true
      feishuStatus.loading = false
      feishuStatus.account = d.bot_name || d.app_id || '已连接'
      feishuStatus.statusLabel = ''
      enableAgentBridge('feishu')
    } else if (d.status === 'error') {
      feishuStatus.loading = false
      feishuStatus.statusLabel = ''
      stopFeishuPolling()
    } else {
      feishuStatus.statusLabel = d.status === 'starting' ? '连接中...' : ''
    }
  } catch {}
}

async function enableAgentBridge(type: 'wechat' | 'feishu') {
  const apiBase = type === 'wechat' ? '/api/wechat' : '/api/feishu'
  try {
    await apiFetch(`${apiBase}/agent-bridge`, {
      method: 'POST',
      body: JSON.stringify({ enabled: true }),
    })
  } catch {}
}

function startWechatPolling() {
  stopWechatPolling()
  wechatPollTimer = setInterval(pollWechatStatus, 2000)
  pollWechatStatus()
}

function startFeishuPolling() {
  stopFeishuPolling()
  feishuPollTimer = setInterval(pollFeishuStatus, 3000)
  pollFeishuStatus()
}

function stopWechatPolling() {
  if (wechatPollTimer) { clearInterval(wechatPollTimer); wechatPollTimer = null }
}

function stopFeishuPolling() {
  if (feishuPollTimer) { clearInterval(feishuPollTimer); feishuPollTimer = null }
}

function stopBotTimers(type: 'wechat' | 'feishu') {
  if (type === 'wechat') stopWechatPolling()
  else stopFeishuPolling()
}

onMounted(async () => {
  document.addEventListener('click', handleGlobalClick)
  const oauthResult = new URLSearchParams(window.location.search).get('feishu_oauth')
  const oauthDetail = new URLSearchParams(window.location.search).get('detail')
  if (oauthResult === 'success') {
    activeSection.value = 'wechat'
    window.history.replaceState({}, document.title, window.location.pathname)
    alert('飞书账号已授权，智能体现在可以查找你的 Wiki 和 Doc 了')
  } else if (oauthResult === 'error') {
    activeSection.value = 'wechat'
    window.history.replaceState({}, document.title, window.location.pathname)
    alert(`飞书授权失败：${oauthDetail || '请重试'}`)
  }
  loadFeishuOAuthStatus()
  try {
    const [wRes, fRes] = await Promise.all([
      apiFetch('/api/wechat/status'),
      apiFetch('/api/feishu/status'),
    ])
    if (wRes.success && wRes.data) {
      const d = wRes.data
      if (d.is_running || d.status === 'logged_in') {
        wechatStatus.connected = true
        wechatStatus.account = d.wxid || d.nickname || '已登录'
        startWechatPolling()
      }
    }
    if (fRes.success && fRes.data) {
      const d = fRes.data
      if (d.is_running || d.status === 'running') {
        feishuStatus.connected = true
        feishuStatus.account = d.bot_name || d.app_id || '已连接'
        startFeishuPolling()
      }
    }
  } catch {}
})

onUnmounted(() => {
  stopWechatPolling()
  stopFeishuPolling()
  document.removeEventListener('click', handleGlobalClick)
})

function handleGlobalClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.settings-avatar-container')) {
    userDropdownOpen.value = false
  }
}

const sections = [
  { key: 'profile', label: '创作者画像', desc: '设置你的领域、调性和内容禁忌' },
  { key: 'agents', label: '智能体管理', desc: '创建、编辑和管理智能体' },
  { key: 'accounts', label: '平台账号', desc: '绑定各平台账号，同步作品数据' },
  { key: 'wechat', label: '自动化办公', desc: '连接通讯工具，智能办公助手' },
  { key: 'plugins', label: '插件管理', desc: '管理和配置您的插件' },
  { key: 'skills', label: 'Skills 技能', desc: '管理 Skill 技能配置' },
  { key: 'config', label: '模型配置', desc: '管理模型配置' },
  { key: 'display', label: '显示设置', desc: '流式输出速度与渲染参数' },
]

const activeSection = ref('profile')

const currentTitle = computed(() => sections.find(s => s.key === activeSection.value)?.label ?? '')
const currentDesc = computed(() => sections.find(s => s.key === activeSection.value)?.desc ?? '')

const loginMethodLabel = computed(() => {
  const method = authStore.user?.login_method || ''
  const map: Record<string, string> = {
    qrcode: '扫码登录',
    email: '邮箱登录',
    plugin: '插件登录',
    session_refresh: '会话刷新',
  }
  return map[method] || ''
})

async function handleLogout() {
  userDropdownOpen.value = false
  try {
    await authStore.logout()
    close()
  } catch (e) {
    console.error('[SettingsView] logout error:', e)
  }
}

function close() {
  document.removeEventListener('click', handleGlobalClick)
  stopWechatPolling()
  stopFeishuPolling()
  emit('close')
}
</script>

<style scoped>
@keyframes ao-spin { to { transform: rotate(360deg); } }
.ao-spin { animation: ao-spin 0.8s linear infinite; display: inline-block; }
.ao-spinner-lg { width:28px;height:28px;border:3px solid #E5E7EB;border-top-color:#9CA3AF;border-radius:50%;animation:ao-spin 0.8s linear infinite; }

.settings-section-banner {
  margin-bottom: 16px;
}
.settings-section-banner img {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 12px;
}

.settings-dropdown-enter-active,
.settings-dropdown-leave-active {
  transition: all 0.2s ease;
}
.settings-dropdown-enter-from,
.settings-dropdown-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-8px);
}
</style>