<template>
  <Transition name="clfc-fade">
    <div v-if="!isProcessed" class="clfc-card" :class="{ 'clfc-error': errorMsg }">
      <div class="clfc-header">
        <Settings2 :size="18" class="clfc-icon" />
        <span class="clfc-title">{{ currentBatch?.title || '创作偏好确认' }}</span>
        <span v-if="currentBatch && currentBatch.total_batches > 1" class="clfc-batch-badge">
          {{ currentBatch.batch_index + 1 }}/{{ currentBatch.total_batches }}
        </span>
      </div>

      <div class="clfc-body">
        <p v-if="currentBatch?.description" class="clfc-desc">{{ currentBatch.description }}</p>
        <p v-if="currentBatch?.next_batch_hint" class="clfc-hint">下一批预告：{{ currentBatch.next_batch_hint }}</p>

        <div v-for="q in currentQuestions" :key="q.id" class="clfc-question">
          <label class="clfc-q-label">
            {{ q.question }}
            <span v-if="q.required" class="clfc-required">*</span>
          </label>

          <div v-if="q.type === 'single_choice' && q.options.length > 0" class="clfc-options">
            <button
              v-for="opt in q.options"
              :key="opt.value"
              class="clfc-opt-btn"
              :class="{ 'clfc-opt-selected': answers[q.id] === opt.value }"
              @click="selectOption(q.id, opt.value)"
            >
              <img v-if="opt.preview_url" :src="opt.preview_url" class="clfc-opt-preview" />
              <span class="clfc-opt-label">{{ opt.label }}</span>
              <span v-if="opt.description" class="clfc-opt-desc">{{ opt.description }}</span>
            </button>
            <div class="clfc-custom-row">
              <span class="clfc-custom-label">其他：</span>
              <input
                type="text"
                :value="answers[q.id] && !q.options.some(o => o.value === answers[q.id]) ? answers[q.id] : ''"
                @input="selectOption(q.id, ($event.target as HTMLInputElement).value)"
                placeholder="自定义…"
                class="clfc-custom-input"
              />
            </div>
          </div>

          <div v-else-if="q.type === 'multi_choice' && q.options.length > 0" class="clfc-options">
            <button
              v-for="opt in q.options"
              :key="opt.value"
              class="clfc-opt-btn"
              :class="{ 'clfc-opt-selected': (answers[q.id] || []).includes(opt.value) }"
              @click="toggleMultiOption(q.id, opt.value)"
            >
              <span class="clfc-opt-label">{{ opt.label }}</span>
            </button>
            <div class="clfc-custom-row">
              <span class="clfc-custom-label">其他：</span>
              <input
                type="text"
                :value="answers[q.id] && !q.options.some(o => (answers[q.id] || []).includes(o.value)) ? answers[q.id] : ''"
                @input="answers[q.id] = ($event.target as HTMLInputElement).value"
                placeholder="自定义…"
                class="clfc-custom-input"
              />
            </div>
          </div>

          <div v-else-if="q.type === 'slider'" class="clfc-slider-row">
            <input
              type="range"
              :min="q.min_value"
              :max="q.max_value"
              :value="answers[q.id] ?? q.default ?? q.min_value"
              @input="answers[q.id] = Number(($event.target as HTMLInputElement).value)"
              class="clfc-slider"
            />
            <span class="clfc-slider-val">{{ answers[q.id] ?? q.default ?? q.min_value }}</span>
          </div>

          <input
            v-else
            type="text"
            :value="answers[q.id] ?? q.default ?? ''"
            @input="answers[q.id] = ($event.target as HTMLInputElement).value"
            :placeholder="q.placeholder || '请输入…'"
            class="clfc-text-input"
          />
        </div>
      </div>

      <div v-if="errorMsg" class="clfc-error-msg">
        <span class="clfc-error-text">{{ errorMsg }}</span>
        <button class="clfc-error-retry" @click="clearError">重试</button>
      </div>

      <div class="clfc-actions">
        <button class="clfc-btn clfc-btn-submit" @click="submitAnswers" :disabled="submitting || !canSubmit">
          {{ submitting ? '提交中…' : submitLabel }}
        </button>
        <button class="clfc-btn clfc-btn-skip" @click="skipBatch" :disabled="submitting">
          跳过
        </button>
        <button class="clfc-btn clfc-btn-cancel" @click="cancelAll" :disabled="submitting">
          取消
        </button>
      </div>
      <p class="clfc-scope-hint">此次选择仅本次生效，不会修改您的默认设置</p>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { authFetch } from '@/api/client'
import { Settings2 } from 'lucide-vue-next'

interface ClarifyOption {
  label: string
  value: string
  description?: string
  preview_url?: string
}

interface ClarifyQuestion {
  id: string
  source_skill: string
  question: string
  type: string
  options: ClarifyOption[]
  default: string
  required: boolean
  placeholder: string
  min_value: number
  max_value: number
}

interface ClarificationBatch {
  batch_id: string
  batch_index: number
  total_batches: number
  title: string
  description: string
  questions: ClarifyQuestion[]
  next_batch_hint: string
  requires_confirmation: boolean
}

const props = defineProps<{
  sessionId: string
  loopStatePath: string
  batches: ClarificationBatch[]
  prompt?: string
  skillName?: string
}>()

const emit = defineEmits<{
  clarified: [answers: Record<string, any>, data?: any]
  skipped: []
  cancelled: []
}>()

const submitting = ref(false)
const isProcessed = ref(false)
const errorMsg = ref('')
const answers = ref<Record<string, any>>({})
const currentBatchIndex = ref(0)

const currentBatch = computed(() => {
  if (!props.batches || props.batches.length === 0) return null
  return props.batches[Math.min(currentBatchIndex.value, props.batches.length - 1)]
})

const currentQuestions = computed(() => currentBatch.value?.questions || [])

const submitLabel = computed(() => {
  if (!currentBatch.value) return '确认'
  if (currentBatch.value.requires_confirmation) return '确认并提交'
  if (currentBatchIndex.value < props.batches.length - 1) return '下一步'
  return '确认并继续'
})

const canSubmit = computed(() => {
  if (!props.sessionId || !props.loopStatePath) return false
  if (!currentBatch.value) return false
  for (const q of currentBatch.value.questions) {
    if (q.required) {
      const val = answers.value[q.id]
      if (val === undefined || val === null || val === '' || (Array.isArray(val) && val.length === 0)) {
        return false
      }
    }
  }
  return true
})

function clearError() {
  errorMsg.value = ''
}

function selectOption(qId: string, value: string) {
  answers.value[qId] = value
}

function toggleMultiOption(qId: string, value: string) {
  const current = (answers.value[qId] || []) as string[]
  const idx = current.indexOf(value)
  if (idx >= 0) {
    answers.value[qId] = current.filter((v: string) => v !== value)
  } else {
    answers.value[qId] = [...current, value]
  }
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
  if (status === 404) return '澄清状态已过期，请重新发起操作'
  if (status === 422) return '请求参数无效'
  if (status === 401) return '登录已过期，请刷新页面后重试'
  if (status >= 500) return '服务器内部错误，请稍后重试'
  return `请求失败 (${status})`
}

async function submitAnswers() {
  if (submitting.value) return
  if (!props.sessionId || !props.loopStatePath) {
    errorMsg.value = '会话信息缺失，请刷新页面后重试'
    return
  }

  submitting.value = true
  errorMsg.value = ''

  try {
    const fieldAnswers: Record<string, any> = {}
    for (const [qId, val] of Object.entries(answers.value)) {
      let fieldName = qId
      if (fieldName.includes('__')) {
        fieldName = fieldName.split('__').pop() || fieldName
      }
      fieldName = fieldName.replace(/^clarify_/, '')
      fieldAnswers[fieldName] = val
    }

    const res = await authFetch('/api/v1/chat/clarify', {
      method: 'POST',
      body: JSON.stringify({
        session_id: props.sessionId,
        loop_state_path: props.loopStatePath,
        answers: fieldAnswers,
        batch_id: currentBatch.value?.batch_id || '',
        action: 'answer',
      }),
    })

    if (!res.ok) {
      const errBody = await res.text()
      console.error('[ChatClarificationCard] clarify failed:', res.status, errBody)
      errorMsg.value = parseErrorMessage(res.status, errBody)
      return
    }

    const data = await res.json().catch(() => null)
    isProcessed.value = true
    emit('clarified', fieldAnswers, data)
  } catch (e: any) {
    console.error('[ChatClarificationCard] clarify error:', e)
    errorMsg.value = e?.message?.includes('Failed to fetch')
      ? '网络连接失败，请检查网络后重试'
      : `操作出错：${e?.message || '未知错误'}`
  } finally {
    submitting.value = false
  }
}

async function skipBatch() {
  if (submitting.value) return
  submitting.value = true
  errorMsg.value = ''
  try {
    const res = await authFetch('/api/v1/chat/clarify', {
      method: 'POST',
      body: JSON.stringify({
        session_id: props.sessionId,
        loop_state_path: props.loopStatePath,
        answers: {},
        batch_id: currentBatch.value?.batch_id || '',
        action: 'skip',
      }),
    })
    if (!res.ok) {
      const errBody = await res.text()
      errorMsg.value = parseErrorMessage(res.status, errBody)
      return
    }
    const data = await res.json().catch(() => null)
    if (data?.status === 'awaiting_clarification' && data?.clarification_batches?.length) {
      // 后端返回下一批问题，更新批次
      currentBatchIndex.value++
    } else {
      // 澄清完成或最后一批被跳过
      isProcessed.value = true
      emit('skipped')
    }
  } catch (e: any) {
    errorMsg.value = `跳过出错：${e?.message || '未知错误'}`
  } finally {
    submitting.value = false
  }
}

async function cancelAll() {
  if (submitting.value) return
  submitting.value = true
  try {
    const res = await authFetch('/api/v1/chat/clarify', {
      method: 'POST',
      body: JSON.stringify({
        session_id: props.sessionId,
        loop_state_path: props.loopStatePath,
        answers: {},
        action: 'cancel',
      }),
    })
    if (res.ok) {
      isProcessed.value = true
      emit('cancelled')
    } else {
      const errBody = await res.text()
      errorMsg.value = parseErrorMessage(res.status, errBody)
    }
  } catch (e: any) {
    errorMsg.value = `取消出错：${e?.message || '未知错误'}`
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.clfc-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px 14px;
  margin-top: 6px;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  min-height: 200px;
}

.clfc-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.clfc-icon {
  color: #8b5cf6;
}

.clfc-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.clfc-batch-badge {
  font-size: 11px;
  color: #8b5cf6;
  background: #f5f3ff;
  padding: 1px 6px;
  border-radius: 4px;
  margin-left: auto;
}

.clfc-body {
  margin-bottom: 10px;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.clfc-desc {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 8px;
}

.clfc-hint {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 6px;
  font-style: italic;
}

.clfc-question {
  margin-bottom: 10px;
}

.clfc-q-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #1e293b;
  margin-bottom: 4px;
}

.clfc-required {
  color: #ef4444;
  margin-left: 2px;
}

.clfc-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.clfc-opt-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
  cursor: pointer;
  transition: all 0.15s;
  min-width: 60px;
}

.clfc-opt-btn:hover {
  border-color: #8b5cf6;
  background: #f5f3ff;
}

.clfc-opt-selected {
  border-color: #8b5cf6;
  background: #ede9fe;
}

.clfc-opt-preview {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
}

.clfc-opt-label {
  font-size: 12px;
  color: #374151;
}

.clfc-opt-desc {
  font-size: 10px;
  color: #9ca3af;
}

.clfc-slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.clfc-slider {
  flex: 1;
}

.clfc-slider-val {
  font-size: 12px;
  color: #6b7280;
  min-width: 30px;
  text-align: right;
}

.clfc-text-input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
}

.clfc-text-input:focus {
  border-color: #8b5cf6;
}

.clfc-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}

.clfc-btn {
  flex: 1;
  padding: 6px 12px;
  border-radius: 6px;
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.clfc-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.clfc-btn-submit {
  background: #8b5cf6;
  color: #fff;
}

.clfc-btn-submit:hover:not(:disabled) {
  background: #7c3aed;
}

.clfc-btn-skip {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.clfc-btn-skip:hover:not(:disabled) {
  background: #e2e8f0;
}

.clfc-btn-cancel {
  background: #f1f5f9;
  color: #94a3b8;
  border: 1px solid #e2e8f0;
  flex: 0.6;
}

.clfc-scope-hint {
  text-align: center;
  font-size: 11px;
  color: #94a3b8;
  margin: 4px 0 0;
}

.clfc-custom-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.clfc-custom-label {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}

.clfc-custom-input {
  flex: 1;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 12px;
  outline: none;
}

.clfc-custom-input:focus {
  border-color: #6366f1;
}

.clfc-error {
  border-color: #fca5a5;
}

.clfc-error-msg {
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

.clfc-error-text {
  font-size: 12px;
  color: #dc2626;
  line-height: 1.5;
  flex: 1;
}

.clfc-error-retry {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: #dc2626;
  background: #fff;
  border: 1px solid #fecaca;
  border-radius: 4px;
  cursor: pointer;
}

.clfc-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.clfc-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>