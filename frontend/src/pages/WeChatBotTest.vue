<template>
  <div class="wechat-bot-test">
    <div class="header">
      <h1>🤖 微信机器人控制台</h1>
      <p class="subtitle">基于 iLink 协议 - Phase 2 测试页面</p>
    </div>

    <!-- 状态卡片 -->
    <div class="card status-card">
      <h2>📊 当前状态</h2>
      <div class="status-info">
        <div class="status-item">
          <span class="label">运行状态:</span>
          <span :class="['status-badge', state.data?.status]">
            {{ getStatusText(state.data?.status) }}
          </span>
        </div>
        <div v-if="state.data?.wxid" class="status-item">
          <span class="label">微信ID:</span>
          <span>{{ state.data.wxid.substring(0, 20) }}...</span>
        </div>
        <div v-if="state.data?.uptime" class="status-item">
          <span class="label">运行时长:</span>
          <span>{{ state.data.uptime }}</span>
        </div>
        <div v-if="state.error" class="error-msg">
          ❌ {{ state.error }}
        </div>
      </div>
      
      <!-- 控制按钮 -->
      <div class="controls">
        <button 
          @click="handleStart"
          :disabled="isLoading || state.data?.is_running"
          class="btn btn-primary"
        >
          {{ isLoading ? '⏳ 启动中...' : '▶️ 启动服务' }}
        </button>
        
        <button 
          @click="handleStop"
          :disabled="isLoading || !state.data?.is_running"
          class="btn btn-danger"
        >
          ⏹️ 停止服务
        </button>
        
        <button 
          @click="fetchStatus"
          :disabled="isLoading"
          class="btn btn-secondary"
        >
          🔄 刷新状态
        </button>
      </div>
    </div>

    <!-- 二维码显示 -->
    <div v-if="showQRCode && qrCodeData.qrcode" class="card qrcode-card">
      <h2>📱 扫码登录</h2>
      <div class="qrcode-container">
        <img 
          :src="qrCodeData.qrcode" 
          alt="微信登录二维码" 
          class="qrcode-image"
        />
        <p class="qrcode-hint">
          ⏳ 请在 {{ qrCountdown }} 秒内用微信扫码
        </p>
        <p class="qrcode-steps">
          1. 打开微信 → 扫一扫<br/>
          2. 对准屏幕上的二维码<br/>
          3. 在手机上确认登录
        </p>
      </div>
    </div>

    <!-- 发送消息 -->
    <div v-if="state.data?.status === 'logged_in'" class="card message-card">
      <h2>💬 发送消息（手动模式）</h2>
      <div class="message-form">
        <div class="form-group">
          <label>目标ID:</label>
          <input 
            v-model="messageForm.to_wxid" 
            type="text" 
            placeholder="filehelper 或 微信ID"
            class="input"
          />
        </div>
        <div class="form-group">
          <label>消息内容:</label>
          <textarea 
            v-model="messageForm.content" 
            placeholder="输入要发送的消息..."
            rows="4"
            class="textarea"
          ></textarea>
        </div>
        <button 
          @click="handleSendMessage"
          :disabled="isSending || !messageForm.to_wxid || !messageForm.content"
          class="btn btn-success"
        >
          {{ isSending ? '发送中...' : '📤 发送消息' }}
        </button>
      </div>
      
      <!-- 发送结果 -->
      <div v-if="sendResult" :class="['result', sendResult.success ? 'success' : 'error']">
        {{ sendResult.success ? '✅' : '❌' }} {{ sendResult.message }}
      </div>
    </div>

    <!-- API 日志 -->
    <div class="card log-card">
      <h2>📋 操作日志</h2>
      <div class="log-container">
        <div 
          v-for="(log, index) in logs" 
          :key="index" 
          :class="['log-entry', log.type]"
        >
          <span class="log-time">{{ log.time }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
        <div v-if="logs.length === 0" class="empty-log">
          暂无日志
        </div>
      </div>
    </div>

    <!-- 快速操作 -->
    <div class="card quick-actions">
      <h2>⚡ 快速测试</h2>
      <div class="action-buttons">
        <button @click="testHealthCheck" class="btn btn-small btn-secondary">
          🩺 健康检查
        </button>
        <button @click="clearLogs" class="btn btn-small btn-warning">
          🗑️ 清空日志
        </button>
        <button @click="openDocs" class="btn btn-small btn-info">
          📖 查看文档
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'

const API_BASE = '/api/wechat'

// 状态
const state = reactive({
  data: null,
  error: null
})

const qrCodeData = reactive({
  qrcode: '',
  expires_in: 120
})

const messageForm = reactive({
  to_wxid: 'filehelper',
  content: ''
})

const sendResult = ref(null)
const logs = reactive([])
const isLoading = ref(false)
const isSending = ref(false)
const showQRCode = computed(() => state.data?.status === 'waiting_qr')

// 倒计时
let countdownTimer = null
const qrCountdown = ref(120)

// 生命周期
onMounted(() => {
  fetchStatus()
})

onUnmounted(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})

// API 方法
async function fetchStatus() {
  try {
    const response = await fetch(`${API_BASE}/status`)
    const result = await response.json()
    
    if (result.success) {
      state.data = result.data
      state.error = null
      
      // 如果是等待扫码状态，获取二维码
      if (result.data.status === 'waiting_qr') {
        await fetchQRCode()
        startCountdown()
      } else {
        stopCountdown()
      }
      
      addLog('info', `状态更新: ${result.data.status}`)
    } else {
      throw new Error(result.detail || '查询失败')
    }
  } catch (error) {
    console.error('查询状态失败:', error)
    state.error = error.message
    addLog('error', `查询失败: ${error.message}`)
  }
}

async function handleStart() {
  isLoading.value = true
  sendResult.value = null
  
  try {
    const response = await fetch(`${API_BASE}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    })
    
    const result = await response.json()
    
    if (result.success) {
      state.data = result.data
      addLog('success', '✅ 服务启动成功')
      
      // 自动获取二维码
      if (result.data.status === 'waiting_qr') {
        await fetchQRCode()
        startCountdown()
      }
    } else {
      throw new Error(result.detail || '启动失败')
    }
  } catch (error) {
    console.error('启动失败:', error)
    state.error = error.message
    addLog('error', `❌ 启动失败: ${error.message}`)
  } finally {
    isLoading.value = false
  }
}

async function handleStop() {
  isLoading.value = true
  
  try {
    const response = await fetch(`${API_BASE}/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    })
    
    const result = await response.json()
    
    if (result.success) {
      state.data = result.data
      stopCountdown()
      addLog('success', '✅ 服务已停止')
    } else {
      throw new Error(result.detail || '停止失败')
    }
  } catch (error) {
    console.error('停止失败:', error)
    state.error = error.message
    addLog('error', `❌ 停止失败: ${error.message}`)
  } finally {
    isLoading.value = false
  }
}

async function fetchQRCode() {
  try {
    const response = await fetch(`${API_BASE}/qrcode`)
    const result = await response.json()
    
    if (result.success && result.data?.qrcode) {
      qrCodeData.qrcode = result.data.qrcode
      qrCodeData.expires_in = result.data.expires_in || 120
      qrCountdown.value = qrCodeData.expires_in
      addLog('success', '二维码获取成功')
    } else {
      addLog('warning', '暂无二维码或获取失败')
    }
  } catch (error) {
    console.error('获取二维码失败:', error)
    addLog('error', `获取二维码失败: ${error.message}`)
  }
}

async function handleSendMessage() {
  isSending.value = true
  sendResult.value = null
  
  try {
    const response = await fetch(`${API_BASE}/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(messageForm)
    })
    
    const result = await response.json()
    
    sendResult.value = result
    
    if (result.success) {
      addLog('success', `✅ 消息已发送至 ${messageForm.to_wxid}`)
      messageForm.content = ''  // 清空输入框
    } else {
      addLog('error', `❌ 发送失败: ${result.message}`)
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    sendResult.value = { success: false, message: error.message }
    addLog('error', `❌ 发送异常: ${error.message}`)
  } finally {
    isSending.value = false
  }
}

// 辅助方法
function getStatusText(status) {
  const statusMap = {
    'stopped': '已停止',
    'starting': '启动中',
    'waiting_qr': '等待扫码',
    'scanned': '已扫描',
    'confirming': '确认中',
    'logged_in': '✅ 已登录',
    'error': '❌ 错误'
  }
  return statusMap[status] || status || '未知'
}

function addLog(type, message) {
  const time = new Date().toLocaleTimeString()
  logs.unshift({ time, message, type })
  
  // 只保留最近50条
  if (logs.length > 50) {
    logs.pop()
  }
}

function startCountdown() {
  stopCountdown()
  qrCountdown.value = qrCodeData.expires_in
  
  countdownTimer = setInterval(() => {
    if (qrCountdown.value > 0) {
      qrCountdown.value--
    } else {
      stopCountdown()
      addLog('warning', '⏰ 二维码已过期，请重新启动')
    }
  }, 1000)
}

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

// 快速操作
async function testHealthCheck() {
  try {
    const response = await fetch(`${API_BASE}/health`)
    const data = await response.json()
    addLog('info', `健康检查: ${JSON.stringify(data)}`)
    alert(`健康检查结果:\n${JSON.stringify(data, null, 2)}`)
  } catch (error) {
    addLog('error', `健康检查失败: ${error.message}`)
  }
}

function clearLogs() {
  logs.splice(0, logs.length)
  addLog('info', '日志已清空')
}

function openDocs() {
  window.open('/docs/WECHAT_ILINK_BOT_IMPLEMENTATION.md', '_blank')
}
</script>

<style scoped>
.wechat-bot-test {
  max-width: 900px;
  margin: 20px auto;
  padding: 20px;
}

.header {
  text-align: center;
  margin-bottom: 30px;
}

.header h1 {
  font-size: 28px;
  margin-bottom: 8px;
  color: #333;
}

.subtitle {
  color: #666;
  font-size: 14px;
}

.card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.card h2 {
  font-size: 18px;
  margin-bottom: 16px;
  color: #333;
  border-bottom: 2px solid #f0f0f0;
  padding-bottom: 10px;
}

/* 状态卡片 */
.status-card .status-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-item .label {
  font-weight: 600;
  min-width: 80px;
  color: #666;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 13px;
}

.status-badge.stopped { background: #f5f5f5; color: #999; }
.status-badge.starting { background: #fff4e5; color: #fa8c16; }
.status-badge.waiting_qr { background: #e6f7ff; color: #1890ff; }
.status-badge.scanned { background: #f6ffed; color: #52c41a; }
.status-badge.confirming { background: #e6f7ff; color: #1890ff; }
.status-badge.logged_in { background: #f6ffed; color: #52c41a; }
.status-badge.error { background: #fff2f0; color: #ff4d4f; }

.error-msg {
  color: #ff4d4f;
  padding: 10px;
  background: #fff2f0;
  border-radius: 6px;
  border-left: 3px solid #ff4d4f;
}

.controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary { background: #1890ff; color: white; }
.btn-primary:hover:not(:disabled) { background: #40a9ff; }

.btn-danger { background: #ff4d4f; color: white; }
.btn-danger:hover:not(:disabled) { background: #ff7875; }

.btn-success { background: #52c41a; color: white; }
.btn-success:hover:not(:disabled) { background: #73d13d; }

.btn-secondary { background: #f0f0f0; color: #666; }
.btn-secondary:hover:not(:disabled) { background: #d9d9d9; }

.btn-small {
  padding: 6px 14px;
  font-size: 13px;
}

.btn-warning { background: #faad14; color: white; }
.btn-info { background: #13c2c2; color: white; }

/* 二维码卡片 */
.qrcode-card {
  text-align: center;
}

.qrcode-container {
  max-width: 300px;
  margin: 0 auto;
}

.qrcode-image {
  width: 100%;
  height: auto;
  border: 2px solid #1890ff;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.15);
}

.qrcode-hint {
  font-size: 18px;
  font-weight: 600;
  color: #1890ff;
  margin: 16px 0;
}

.qrcode-steps {
  color: #666;
  line-height: 1.8;
  text-align: left;
  background: #fafafa;
  padding: 12px;
  border-radius: 6px;
}

/* 消息卡片 */
.message-form {
  max-width: 500px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-weight: 600;
  margin-bottom: 6px;
  color: #333;
}

.input, .textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.input:focus, .textarea:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.1);
}

.textarea {
  resize: vertical;
  min-height: 80px;
}

.result {
  margin-top: 16px;
  padding: 12px;
  border-radius: 6px;
  font-weight: 600;
}

.result.success {
  background: #f6ffed;
  color: #52c41a;
  border-left: 3px solid #52c41a;
}

.result.error {
  background: #fff2f0;
  color: #ff4d4f;
  border-left: 3px solid #ff4d4f;
}

/* 日志卡片 */
.log-card {
  max-height: 400px;
  overflow-y: auto;
}

.log-container {
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

.log-entry {
  padding: 8px 10px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  gap: 12px;
}

.log-time {
  color: #999;
  min-width: 70px;
}

.log-message {
  flex: 1;
}

.log-entry.info { background: #fafafa; }
.log-entry.success { background: #f6ffed; color: #389e0d; }
.log-entry.warning { background: #fffbe6; color: #d48806; }
.log-entry.error { background: #fff2f0; color: #cf1322; }

.empty-log {
  text-align: center;
  color: #999;
  padding: 40px;
}

/* 快速操作 */
.quick-actions .action-buttons {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .wechat-bot-test {
    padding: 10px;
  }
  
  .controls {
    flex-direction: column;
  }
  
  .controls .btn {
    width: 100%;
    justify-content: center;
  }
}
</style>