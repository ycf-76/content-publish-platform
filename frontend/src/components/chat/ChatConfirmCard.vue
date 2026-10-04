<template>
  <Transition name="ccc-fade">
    <div v-if="!isProcessed" class="ccc-card" :class="{ 'ccc-error': errorMsg }">
      <div class="ccc-header">
        <AlertTriangle :size="18" class="ccc-icon" />
        <span class="ccc-title">操作确认</span>
      </div>

      <div class="ccc-body">
        <div class="ccc-prompt">{{ prompt }}</div>
        <div v-if="skillName" class="ccc-skill-tag">
          <span class="ccc-skill-dot"></span>
          {{ skillName }}
        </div>
      </div>

      <div v-if="isExpired" class="ccc-expired-msg">
        <AlertTriangle :size="16" class="ccc-expired-icon" />
        <div class="ccc-expired-body">
          <p class="ccc-expired-title">操作确认已过期</p>
          <p class="ccc-expired-desc">该操作的等待时间已超时，请重新发起</p>
        </div>
      </div>

      <template v-else>
        <div v-if="errorMsg" class="ccc-error-msg">
          <span class="ccc-error-text">{{ errorMsg }}</span>
          <button class="ccc-error-retry" @click="clearError">重试</button>
        </div>

        <div class="ccc-actions">
          <button class="ccc-btn ccc-btn-approve" @click="submit('approve')" :disabled="submitting || !canSubmit">
            {{ submitting ? '提交中…' : '确认执行' }}
          </button>
          <button class="ccc-btn ccc-btn-reject" @click="submit('reject')" :disabled="submitting || !canSubmit">
            {{ submitting ? '提交中…' : '取消操作' }}
          </button>
        </div>
      </template>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { authFetch } from '@/api/client'
import { AlertTriangle } from 'lucide-vue-next'

const props = defineProps<{
  sessionId: string
  loopStatePath: string
  prompt: string
  skillName?: string
}>()

const emit = defineEmits<{
  confirmed: [action: 'approve' | 'reject', data?: any]
  expired: []
}>()

const submitting = ref(false)
const isProcessed = ref(false)
const isExpired = ref(false)
const lastAction = ref('')
const errorMsg = ref('')

const canSubmit = computed(() => !!props.sessionId && !!props.loopStatePath)

function clearError() {
  errorMsg.value = ''
}

function parseErrorMessage(status: number, body: string): string {
  try {
    const parsed = JSON.parse(body)
    if (parsed.detail) {
      if (typeof parsed.detail === 'string') return parsed.detail
      if (Array.isArray(parsed.detail)) {
        return parsed.detail.map((d: any) => d.msg || String(d)).join('; ')
      }
      return String(parsed.detail)
    }
    if (parsed.message) return parsed.message
  } catch {}
  if (status === 404) return '确认状态已过期，请重新发起操作'
  if (status === 422) return '请求参数无效'
  if (status === 401) return '登录已过期，请刷新页面后重试'
  if (status >= 500) return '服务器内部错误，请稍后重试'
  return `请求失败 (${status})`
}

async function submit(action: 'approve' | 'reject') {
  if (submitting.value) return

  if (!props.sessionId) {
    errorMsg.value = '会话 ID 缺失，请刷新页面后重试'
    return
  }
  if (!props.loopStatePath) {
    errorMsg.value = '确认状态路径缺失，请重新发起操作'
    return
  }

  errorMsg.value = ''
  submitting.value = true

  try {
    const res = await authFetch('/api/v1/chat/confirm', {
      method: 'POST',
      body: JSON.stringify({
        session_id: props.sessionId,
        loop_state_path: props.loopStatePath,
        action,
        feedback: '',
      }),
    })

    if (!res.ok) {
      const errBody = await res.text()
      console.error('[ChatConfirmCard] confirm failed:', res.status, errBody)
      errorMsg.value = parseErrorMessage(res.status, errBody)

      if (res.status === 404) {
        isExpired.value = true
        emit('expired')
      }
      return
    }

    const data = await res.json().catch(() => null)
    lastAction.value = action
    isProcessed.value = true
    emit('confirmed', action, data)
  } catch (e: any) {
    console.error('[ChatConfirmCard] confirm error:', e)
    errorMsg.value = e?.message?.includes('Failed to fetch')
      ? '网络连接失败，请检查网络后重试'
      : `操作出错：${e?.message || '未知错误'}`
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.ccc-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 12px;
  margin-top: 6px;
  transition: all 0.3s ease;
}

.ccc-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.ccc-icon {
  font-size: 14px;
  line-height: 1;
  color: #f97316;
}

.ccc-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.ccc-body {
  margin-bottom: 8px;
}

.ccc-prompt {
  font-size: 13px;
  color: #1e293b;
  line-height: 1.6;
  padding: 6px 8px;
  background: #f9fafb;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}

.ccc-skill-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 11px;
  color: #6b7280;
  background: #f9fafb;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
}

.ccc-skill-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #f97316;
}

.ccc-actions {
  display: flex;
  gap: 8px;
}

.ccc-btn {
  flex: 1;
  padding: 6px 12px;
  border-radius: 6px;
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.ccc-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ccc-btn-approve {
  background: #f97316;
  color: #fff;
}

.ccc-btn-approve:hover:not(:disabled) {
  background: #ea580c;
}

.ccc-btn-reject {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.ccc-btn-reject:hover:not(:disabled) {
  background: #e2e8f0;
  color: #475569;
}

.ccc-error {
  border-color: #fca5a5;
}

.ccc-error-msg {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  margin-bottom: 8px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
}

.ccc-error-text {
  font-size: 12px;
  color: #dc2626;
  line-height: 1.5;
  flex: 1;
}

.ccc-error-retry {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: #dc2626;
  background: #fff;
  border: 1px solid #fecaca;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.ccc-error-retry:hover {
  background: #fef2f2;
}

.ccc-expired-msg {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 6px;
}

.ccc-expired-icon {
  color: #f59e0b;
  flex-shrink: 0;
  margin-top: 1px;
}

.ccc-expired-body {
  flex: 1;
  min-width: 0;
}

.ccc-expired-title {
  font-size: 12.5px;
  font-weight: 600;
  color: #92400e;
  margin: 0 0 3px 0;
  line-height: 1.4;
}

.ccc-expired-desc {
  font-size: 11.5px;
  color: #a16207;
  margin: 0;
  line-height: 1.5;
}

.ccc-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.ccc-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>