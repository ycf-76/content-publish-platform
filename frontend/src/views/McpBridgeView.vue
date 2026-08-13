<template>
  <main class="bridge-page">
    <header class="bridge-header">
      <h1>MCP 桥接页面</h1>
      <div class="bridge-status" :class="statusClass">
        <span class="dot"></span>
        <span>{{ statusText }}</span>
      </div>
    </header>

    <section class="bridge-config card">
      <div class="config-row">
        <label>后端地址</label>
        <input v-model="backendUrl" type="text" placeholder="http://127.0.0.1:8000" :disabled="connected" />
      </div>
      <div class="config-row">
        <label>扩展 ID</label>
        <input v-model="extensionId" type="text" placeholder="在 chrome://extensions 找到扩展ID" :disabled="connected" />
        <button class="hint-btn" @click="showHint = !showHint" type="button">？</button>
      </div>
      <div class="config-hint" v-if="showHint">
        获取扩展ID：打开 chrome://extensions → 开启"开发者模式" → 找到"多智能体小红书发布平台 MCP 插件" → 复制 ID 栏的字符串
      </div>
      <div class="config-actions">
        <button class="btn-primary" @click="toggleConnect" type="button" :disabled="!canConnect">
          {{ connected ? '断开' : '连接' }}
        </button>
        <button class="btn-secondary" @click="testExtension" type="button" :disabled="!extensionId || testing">
          {{ testing ? '测试中...' : '测试扩展通信' }}
        </button>
      </div>
      <div class="config-test-result" v-if="testResult" :class="{ 'test-ok': testOk, 'test-fail': !testOk }">
        {{ testResult }}
      </div>
    </section>

    <section class="bridge-guide card" v-if="!connected">
      <h2>使用说明</h2>
      <ol>
        <li>安装浏览器扩展（browser_extension 目录加载到 Chrome）</li>
        <li>在浏览器里登录小红书（打开 xiaohongshu.com 并登录）</li>
        <li>在上方输入扩展 ID</li>
        <li>点"连接"启动桥接</li>
        <li>保持本页面打开，去选题池点"抓取"</li>
      </ol>
      <p class="guide-tip">也可以点击扩展图标 → "打开桥接页面（抓取必需）" 使用扩展自带的桥接页面。</p>
    </section>

    <section class="bridge-log card" v-if="connected">
      <div class="log-header">
        <h2>桥接日志</h2>
        <button class="btn-secondary btn-sm" @click="logs = []" type="button">清空</button>
      </div>
      <div class="log-body" ref="logBody">
        <div v-for="(line, i) in logs" :key="i" :class="'log-' + line.level">
          <span class="log-time">{{ line.time }}</span>
          <span class="log-msg">{{ line.msg }}</span>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onUnmounted } from 'vue'

const backendUrl = ref(localStorage.getItem('bridge_backend') || 'http://127.0.0.1:8000')
const extensionId = ref(localStorage.getItem('bridge_ext_id') || '')
const connected = ref(false)
const showHint = ref(false)
const testing = ref(false)
const testResult = ref('')
const testOk = ref(false)
const logs = ref<{ time: string; msg: string; level: string }[]>([])
const logBody = ref<HTMLElement | null>(null)

let eventSource: EventSource | null = null
let heartbeatTimer: number | null = null

const canConnect = computed(() => backendUrl.value.trim() && extensionId.value.trim())
const statusClass = computed(() => connected.value ? 'online' : 'offline')
const statusText = computed(() => connected.value ? '桥接在线' : '未连接')

function log(msg: string, level = 'info') {
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  logs.value.push({ time, msg, level })
  nextTick(() => {
    if (logBody.value) logBody.value.scrollTop = logBody.value.scrollHeight
  })
  while (logs.value.length > 200) logs.value.shift()
}

async function registerBridge() {
  try {
    await fetch(backendUrl.value.replace(/\/+$/, '') + '/api/mcp/bridge/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: 'frontend-bridge' }),
    })
  } catch (e) {
    log(`注册失败: ${(e as Error).message}`, 'error')
  }
}

async function postResult(callId: string, result: object) {
  try {
    await fetch(backendUrl.value.replace(/\/+$/, '') + `/api/mcp/bridge/result/${callId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(result),
    })
  } catch (e) {
    log(`回传结果失败: ${(e as Error).message}`, 'error')
  }
}

async function handleRequest(req: { call_id: string; action: string; payload: any }) {
  const { call_id, action, payload } = req
  log(`收到请求: action=${action} call_id=${call_id}`)

  try {
    const result = await chrome.runtime.sendMessage(extensionId.value, { action, payload })
    if (result && result.success) {
      log(`请求成功: action=${action}`, 'success')
      await postResult(call_id, { success: true, data: result.data })
    } else {
      const msg = result?.message || '扩展返回失败'
      log(`请求失败: action=${action} → ${msg}`, 'warn')
      // 透传完整 result，保留 _diag 等诊断字段
      await postResult(call_id, { success: false, ...result })
    }
  } catch (e) {
    log(`转发异常: action=${action} → ${(e as Error).message}`, 'error')
    await postResult(call_id, { success: false, message: (e as Error).message })
  }
}

function connectSSE() {
  const url = backendUrl.value.replace(/\/+$/, '') + '/api/mcp/bridge/stream'
  log(`正在连接后端 SSE: ${url}`)
  eventSource = new EventSource(url)

  eventSource.onopen = async () => {
    log('SSE 连接已建立', 'success')
    await registerBridge()
    connected.value = true
    localStorage.setItem('bridge_backend', backendUrl.value)
    localStorage.setItem('bridge_ext_id', extensionId.value)
    heartbeatTimer = window.setInterval(registerBridge, 30000)
  }

  eventSource.onmessage = async (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'hello') {
        log(`收到 hello: ${msg.message}`)
        return
      }
      if (msg.type === 'request' && msg.call_id) {
        await handleRequest(msg)
        return
      }
      log(`收到消息: ${JSON.stringify(msg).slice(0, 200)}`)
    } catch (e) {
      log(`消息解析失败: ${(e as Error).message}`, 'error')
    }
  }

  eventSource.onerror = () => {
    log('SSE 连接断开，5 秒后重连...', 'error')
    eventSource?.close()
    eventSource = null
    connected.value = false
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
    setTimeout(() => { if (canConnect.value) connectSSE() }, 5000)
  }
}

function toggleConnect() {
  if (connected.value) {
    eventSource?.close()
    eventSource = null
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
    connected.value = false
    log('已断开连接')
  } else {
    connectSSE()
  }
}

async function testExtension() {
  testing.value = true
  testResult.value = ''
  try {
    const result = await chrome.runtime.sendMessage(extensionId.value, { action: 'health' })
    if (result && result.success) {
      testOk.value = true
      testResult.value = `扩展在线，小红书${result.data.logged_in ? '已登录' : '未登录'}，${result.data.cookies_count} 个 cookie`
    } else {
      testOk.value = false
      testResult.value = result?.message || '扩展返回失败'
    }
  } catch (e) {
    testOk.value = false
    testResult.value = `通信失败：${(e as Error).message}（请确认扩展ID正确且扩展已启用）`
  } finally {
    testing.value = false
  }
}

onUnmounted(() => {
  eventSource?.close()
  if (heartbeatTimer) clearInterval(heartbeatTimer)
})
</script>

<style scoped>
.bridge-page {
  /* 小红书风格覆盖：将 ma-blue-* 主色映射为小红书红系 */
  --ma-blue-50: #FFF1F3;
  --ma-blue-100: #FFE4E8;
  --ma-blue-200: #FFCDD5;
  --ma-blue-300: #FF9AA7;
  --ma-blue-400: #FF2442;
  --ma-blue-500: #FF2442;
  --ma-blue-600: #FF2442;
  --ma-blue-700: #FF2442;
  --ma-blue-800: #FF2442;
  --ma-blue-900: #FF2442;
  min-width: 1024px;
  max-width: 900px;
  margin: 0 auto;
  padding: 32px;
  min-height: 100vh;
  background: var(--ma-bg-subtle);
  font-family: var(--ma-font-sans);
  color: var(--ma-text-primary);
}
.bridge-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.bridge-header h1 {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
}
.bridge-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  padding: 6px 14px;
  border-radius: 20px;
}
.bridge-status .dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.bridge-status.online { background: #dcfce7; color: #166534; }
.bridge-status.online .dot { background: #10b981; }
.bridge-status.offline { background: #fee2e2; color: #991b1b; }
.bridge-status.offline .dot { background: #ef4444; }

.card {
  background: var(--ma-bg-base);
  border: 1px solid var(--ma-border-default);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
}
.config-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.config-row label {
  width: 80px;
  font-size: 14px;
  color: var(--ma-text-secondary);
  flex-shrink: 0;
}
.config-row input {
  flex: 1;
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--ma-border-default);
  border-radius: 6px;
  font-size: 14px;
  font-family: inherit;
  color: var(--ma-text-primary);
  background: var(--ma-bg-base);
  outline: none;
  box-sizing: border-box;
}
.config-row input:focus {
  border-color: var(--ma-blue-500);
  box-shadow: 0 0 0 3px rgba(255, 36, 66, 0.1);
}
.hint-btn {
  width: 28px;
  height: 28px;
  border: 1px solid var(--ma-border-default);
  border-radius: 50%;
  background: var(--ma-bg-base);
  cursor: pointer;
  font-size: 13px;
  color: var(--ma-text-tertiary);
  flex-shrink: 0;
}
.config-hint {
  font-size: 13px;
  color: var(--ma-text-tertiary);
  background: var(--ma-blue-50);
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 12px;
  line-height: 1.6;
}
.config-actions {
  display: flex;
  gap: 10px;
}
.btn-primary {
  padding: 9px 20px;
  border: none;
  border-radius: 6px;
  background: var(--ma-blue-500);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
}
.btn-primary:hover:not(:disabled) { background: var(--ma-blue-600); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary {
  padding: 9px 16px;
  border: 1px solid var(--ma-border-default);
  border-radius: 6px;
  background: var(--ma-bg-base);
  color: var(--ma-text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
}
.btn-secondary:hover:not(:disabled) { background: var(--ma-bg-subtle); }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.config-test-result {
  margin-top: 10px;
  padding: 8px 12px;
  font-size: 13px;
  border-radius: 6px;
}
.config-test-result.test-ok { background: #dcfce7; color: #166534; }
.config-test-result.test-fail { background: #fee2e2; color: #991b1b; }

.bridge-guide h2 { font-size: 16px; margin: 0 0 12px; }
.bridge-guide ol { padding-left: 20px; line-height: 2; font-size: 14px; color: var(--ma-text-secondary); }
.guide-tip { font-size: 13px; color: var(--ma-text-tertiary); margin-top: 12px; padding: 10px 14px; background: var(--ma-bg-subtle); border-radius: 6px; }

.log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.log-header h2 { font-size: 16px; margin: 0; }
.log-body {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.8;
  max-height: 400px;
  overflow-y: auto;
  background: #0f172a;
  color: #e2e8f0;
  padding: 14px;
  border-radius: 12px;
}
.log-time { color: #64748b; margin-right: 8px; }
.log-info .log-msg { color: #93c5fd; }
.log-success .log-msg { color: #6ee7b7; }
.log-error .log-msg { color: #fca5a5; }
.log-warn .log-msg { color: #fcd34d; }
</style>
