<template>
  <div class="mint-wf-card wf-node-card wf-node-copywrite" id="card-copywrite" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">03</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="pen-tool" class="wf-node-icon"></i>
            文案撰写
            <code class="wf-node-key">copywrite</code>
          </div>
          <div class="wf-node-subtitle">生成并精修文案</div>
        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>

    <div class="wf-node-summary" v-if="nodeStatus === 'completed' && result">
      {{ editTitle || '文案已确认' }}
    </div>

    <div class="wf-node-body">
      <!-- idle：显示提示但不强调"等待" -->
      <div v-if="nodeStatus === 'idle'" class="cw-empty">
        <i data-lucide="pen-tool" style="width:14px;height:14px;color:#FF2442;"></i>
        <span>文案撰写节点就绪</span>
        <div v-if="targetLength" class="cw-config-hint">
          目标字数：{{ targetLength }} 字
        </div>
      </div>

      <!-- running：流式逐字打印（Codex 风格） -->
      <div v-else-if="nodeStatus === 'running'" class="cw-body">
        <div v-if="!streamingText" class="cw-loading">
          <div class="cw-loader-codex">
            <div class="cw-loader-dot"></div>
            <div class="cw-loader-dot"></div>
            <div class="cw-loader-dot"></div>
          </div>
          <span>正在生成文案...</span>
          <div v-if="targetLength" class="cw-config-hint">目标 {{ targetLength }} 字</div>
        </div>
        <template v-else>
          <div class="cw-streaming-codex">
            <div class="cw-stream-text">{{ typedText }}</div>
            <span class="cw-cursor-codex">▌</span>
          </div>
          <div class="cw-meta-row">
            <span class="cw-counter">{{ typedText.length }} 字<span v-if="targetLength"> / {{ targetLength }} 字目标</span></span>
            <span class="cw-status-dot"></span>
          </div>
        </template>
      </div>

      <!-- error -->
      <div v-else-if="nodeStatus === 'error'" class="cw-error">
        <i data-lucide="alert-circle" style="width:16px;height:16px;"></i>
        <span>{{ errorMessage || '文案生成失败' }}</span>
      </div>

      <!-- awaiting_review：人工审核状态（主要状态） -->
      <div v-else-if="nodeStatus === 'awaiting_review' && result" class="cw-body">
        <div class="cw-review-badge">
          <i data-lucide="eye" style="width:16px;height:16px;"></i>
          <span>请审核文案</span>
        </div>

        <div class="cw-editor">
          <input
            v-model="editTitle"
            class="cw-title"
            placeholder="填写标题会有更多赞哦～"
            :maxlength="20"
          />
          <div class="cw-title-count">{{ editTitle.length }}/20</div>
          <div class="cw-hr"></div>
          <textarea
            ref="textareaRef"
            v-model="editContent"
            class="cw-textarea"
            placeholder="添加正文"
            @input="autoResize"
          ></textarea>
          <div class="cw-counter">
            {{ editContent.length }} 字
            <span v-if="targetLength && Math.abs(editContent.length - targetLength) > 50" class="cw-length-warning">
              （目标 {{ targetLength }} 字）
            </span>
          </div>
          <div v-if="suggestedTopics.length" class="cw-topics">
            <span class="cw-topics-label">话题标签</span>
            <button
              v-for="(t, i) in suggestedTopics"
              :key="i"
              class="cw-topic-chip"
              :class="{ 'cw-topic-used': isTopicUsed(t) }"
              @click="insertTopic(t)"
            >{{ t }}</button>
          </div>
        </div>

        <div v-if="displayData.review_feedback" class="cw-msg cw-msg-warn">
          <i data-lucide="message-square-warning" style="width:12px;height:12px;"></i>
          <span>上游反馈：{{ result.review_feedback }}</span>
        </div>
        <div v-if="saveError" class="cw-msg cw-msg-err">
          <i data-lucide="alert-circle" style="width:12px;height:12px;"></i>
          <span>{{ saveError }}</span>
        </div>
        <div v-if="regenerateError" class="cw-msg cw-msg-err">
          <i data-lucide="alert-circle" style="width:12px;height:12px;"></i>
          <span>{{ regenerateError }}</span>
        </div>
      </div>

      <!-- completed：已确认状态 -->
      <div v-else-if="nodeStatus === 'completed' && result" class="cw-body">
        <div class="cw-completed-badge">
          <i data-lucide="check-circle" style="width:16px;height:16px;"></i>
          <span>文案已确认</span>
        </div>

        <div class="cw-editor cw-editor-readonly">
          <div class="cw-title cw-title-readonly">{{ editTitle || '（无标题）' }}</div>
          <div class="cw-hr"></div>
          <pre class="cw-textarea cw-textarea-readonly">{{ editContent || '（无内容）' }}</pre>
          <div class="cw-counter">{{ editContent.length }} 字</div>
        </div>
      </div>

      <!-- 无数据显示 -->
      <div v-else class="cw-empty">
        <i data-lucide="check-circle" style="width:14px;height:14px;color:#60A5FA;"></i>
        文案已处理（详细数据不可用）
      </div>
    </div>

    <div class="mint-wf-footer" v-if="showFooter">
      <div class="wf-node-meta" v-if="nodeMeta">
        <span class="wf-meta-item"><i data-lucide="clock" style="width:12px;height:12px;"></i>{{ nodeMeta.duration }}</span>
        <span class="wf-meta-item"><i data-lucide="cpu" style="width:12px;height:12px;"></i>{{ nodeMeta.model }}</span>
        <span class="wf-meta-item"><i data-lucide="zap" style="width:12px;height:12px;"></i>{{ nodeMeta.tokens }} tokens</span>
      </div>
      <div class="cw-actions">
        <!-- awaiting_review 状态的操作按钮 -->
        <template v-if="nodeStatus === 'awaiting_review'">
          <button class="cw-btn cw-btn-ghost" @click="regenerateCopy" :disabled="regenerating">
            <i data-lucide="refresh-cw" style="width:14px;height:14px;"></i>
            {{ regenerating ? '生成中...' : '重新生成' }}
          </button>
          <button class="cw-btn cw-btn-outline" @click="approveAndContinue">
            <i data-lucide="check" style="width:14px;height:14px;"></i>
            确认并继续
          </button>
        </template>

        <!-- completed 状态的编辑按钮 -->
        <template v-else-if="nodeStatus === 'completed'">
          <button class="cw-btn cw-btn-ghost" @click="regenerateCopy" :disabled="regenerating">
            <i data-lucide="refresh-cw" style="width:14px;height:14px;"></i>
            {{ regenerating ? '生成中...' : '重新生成' }}
          </button>
          <button class="cw-btn cw-btn-outline" @click="reEdit">
            <i data-lucide="edit-3" style="width:14px;height:14px;"></i>
            重新编辑
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'
import { workflowApi } from '@/api/workflow'
import { useWorkflowStore } from '@/stores/workflow'
import { useTypewriter } from '@/composables/useTypewriter'

const workflowStore = useWorkflowStore()

const props = defineProps<{
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
  result: any
  errorMessage?: string
  workflowId?: string
  streamingText?: string
  nodeConfig?: { content_length?: number; require_review?: boolean; [key: string]: any }
}>()

const emit = defineEmits<{
  'approve-and-continue': []
  're-edit': []
}>()

watch(() => props.nodeStatus, () => nextTick(() => createIcons({ icons })))
watch(() => props.result, () => nextTick(() => createIcons({ icons })), { deep: true, immediate: true })

// 从配置获取目标文案长度
const targetLength = computed(() => props.nodeConfig?.content_length || 300)

// 打字机效果：流式文本逐字打印
const streamTarget = computed(() => props.streamingText || '')
const { displayed: typedText } = useTypewriter(streamTarget, { intervalMs: 20, charsPerTick: 2 })

const displayData = ref<Record<string, any>>({})

watch(() => props.result, (r) => {
  if (r) {
    displayData.value = { ...r }
    editTitle.value = r.title || ''
    editContent.value = r.content || ''
    selectedTopics.value = new Set(r.tags || [])
    nextTick(() => autoResize())
  }
}, { deep: true, immediate: true })

const saving = ref(false)
const saveError = ref('')
const regenerating = ref(false)
const regenerateError = ref('')
const editTitle = ref('')
const editContent = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const showFooter = computed(() =>
  ['awaiting_review', 'completed'].includes(props.nodeStatus)
)

const suggestedTopics = computed(() => {
  return (displayData.value?.tags || []).filter((t: string) => t?.trim().length > 0)
})

const selectedTopics = ref<Set<string>>(new Set())

function isTopicUsed(topic: string) {
  return selectedTopics.value.has(topic)
}

function insertTopic(topic: string) {
  if (selectedTopics.value.has(topic)) {
    selectedTopics.value.delete(topic)
  } else {
    selectedTopics.value.add(topic)
  }
}

function autoResize() {
  const ta = textareaRef.value
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = ta.scrollHeight + 'px'
}

async function regenerateCopy() {
  if (!props.workflowId) { regenerateError.value = '缺少工作流 ID'; return }
  regenerating.value = true
  regenerateError.value = ''
  saveError.value = ''
  try {
    await workflowApi.rollback(props.workflowId, 'copywrite')
    await workflowStore.resumeWorkflow()
  } catch (e: any) {
    regenerateError.value = '重新生成失败：' + (e?.response?.data?.detail || e?.message || String(e))
  } finally {
    regenerating.value = false
  }
}

async function approveAndContinue() {
  if (!props.workflowId) { saveError.value = '缺少工作流 ID'; return }
  saving.value = true
  saveError.value = ''

  const output = {
    title: editTitle.value.trim(),
    content: editContent.value.trim(),
    tags: Array.from(selectedTopics.value).length > 0 ? Array.from(selectedTopics.value) : (displayData.value?.tags || []),
    locations: displayData.value?.locations || [],
    key_points: displayData.value?.key_points,
    structured_items: displayData.value?.structured_items,
    review_feedback: displayData.value?.review_feedback,
    prompt_source: displayData.value?.prompt_source,
    approved: true,
    approved_at: new Date().toISOString(),
  }

  try {
    await workflowApi.updateNodeOutput(props.workflowId, 'copywrite', output)
    emit('approve-and-continue')
  } catch (e: any) {
    saveError.value = '确认失败：' + (e?.response?.data?.detail || e?.message || String(e))
  } finally {
    saving.value = false
  }
}

function reEdit() {
  emit('re-edit')
}

const statusColor = computed(() => ({
  idle: '#9CA3AF',
  running: '#FF2442',
  completed: '#10B981',
  awaiting_review: '#F59E0B',
  error: '#EF4444',
}[props.nodeStatus] || '#9CA3AF'))

const statusLabel = computed(() => ({
  idle: '待执行',
  running: '执行中',
  completed: '已完成',
  awaiting_review: '待审核',
  error: '失败',
}[props.nodeStatus] || '待执行'))

const statusBadgeStyle = computed(() => {
  if (props.nodeStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'completed') return { background: '#D1FAE5', color: '#059669' }
  if (props.nodeStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'awaiting_review') return { background: '#FEF3C7', color: '#D97706' }
  return { background: '#F1F5F9', color: '#64748B' }
})
</script>

<style scoped>
.cw-empty {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 20px;
  color: #9CA3AF;
  font-size: 15px;
  justify-content: center;
  flex-direction: column;
}

.cw-config-hint {
  margin-top: 8px;
  padding: 4px 10px;
  background: #F3F4F6;
  border-radius: 12px;
  font-size: 13px;
  color: #6B7280;
}

.cw-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.cw-loading {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 32px 0;
  color: #6B7280;
  font-size: 14px;
  justify-content: center;
  flex-direction: column;
}

/* Codex 风格加载动画：三脉冲点 */
.cw-loader-codex {
  display: flex;
  align-items: center;
  gap: 4px;
}
.cw-loader-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #FF2442;
  animation: cwPulse 1.4s ease-in-out infinite;
}
.cw-loader-dot:nth-child(2) { animation-delay: 0.16s; }
.cw-loader-dot:nth-child(3) { animation-delay: 0.32s; }

@keyframes cwPulse {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* Codex 风格流式输出 */
.cw-streaming-codex {
  position: relative;
  padding: 20px 24px;
  background: linear-gradient(135deg, #F5F5F7 0%, #EEEEEF 100%);
  border-radius: 10px;
  border: 1px solid #E8E8E8;
  min-height: 100px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.cw-stream-text {
  font-size: 15px;
  color: #1a1a1a;
  line-height: 1.85;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Codex 风格光标：呼吸脉动 */
.cw-cursor-codex {
  display: inline-block;
  color: #FF2442;
  font-weight: 300;
  margin-left: 1px;
  animation: cwCursorPulse 1s ease-in-out infinite;
}

@keyframes cwCursorPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.2; }
}

/* 底部元信息行 */
.cw-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding: 0 4px;
}

.cw-counter {
  font-size: 12px;
  color: #9CA3AF;
  font-variant-numeric: tabular-nums;
}

.cw-length-warning {
  color: #F59E0B;
  margin-left: 4px;
}

/* 状态指示点：脉动绿点 */
.cw-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10B981;
  animation: cwStatusPulse 2s ease-in-out infinite;
}

@keyframes cwStatusPulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(16,185,129,0.4); }
  50% { opacity: 0.7; box-shadow: 0 0 0 4px rgba(16,185,129,0); }
}

/* 审核状态徽章 */
.cw-review-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%);
  border: 1px solid #F59E0B;
  border-radius: 16px;
  color: #92400E;
  font-size: 13px;
  font-weight: 600;
  width: fit-content;
}

/* 已确认徽章 */
.cw-completed-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: linear-gradient(135deg, #D1FAE5 0%, #A7F3D0 100%);
  border: 1px solid #10B981;
  border-radius: 16px;
  color: #065F46;
  font-size: 13px;
  font-weight: 600;
  width: fit-content;
}

.cw-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  color: #EF4444;
  font-size: 15px;
}

.cw-editor {
  display: flex;
  flex-direction: column;
}

.cw-editor-readonly {
  opacity: 0.85;
}

.cw-title {
  width: 100%;
  border: none;
  outline: none;
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  background: transparent;
  padding: 0;
  line-height: 1.5;
  font-family: inherit;
  box-sizing: border-box;
}
.cw-title::placeholder { color: #C4C4C4; font-weight: 400; }

.cw-title-readonly {
  cursor: default;
  color: #374151;
}

.cw-title-count {
  font-size: 12px;
  color: #C4C4C4;
  text-align: right;
  padding: 2px 0 0 0;
}

.cw-hr {
  height: 1px;
  background: #F0F0F0;
  margin: 10px 0;
}

.cw-textarea {
  width: 100%;
  border: none;
  outline: none;
  font-size: 15px;
  color: #333;
  background: transparent;
  padding: 0;
  line-height: 1.8;
  resize: none;
  font-family: inherit;
  box-sizing: border-box;
  white-space: pre-wrap;
  word-break: break-word;
  min-height: 80px;
}
.cw-textarea::placeholder { color: #C4C4C4; }

.cw-textarea-readonly {
  cursor: default;
  color: #374151;
  font-family: inherit;
  white-space: pre-wrap;
  word-break: break-word;
}

.cw-topics {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #F0F0F0;
}

.cw-topics-label {
  font-size: 13px;
  color: #999;
  font-weight: 500;
  margin-right: 2px;
}

.cw-topic-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border: 1px solid #E8E8E8;
  border-radius: 14px;
  background: #F5F5F7;
  color: #13386C;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  line-height: 1.4;
}
.cw-topic-chip:hover { background: #EDF2FC; border-color: #B8CCE8; }
.cw-topic-used { background: #EDF2FC; border-color: #93B4E0; color: #2563EB; }

.cw-msg {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 14px;
}
.cw-msg-warn { background: #FFFBEB; border: 1px solid #FDE68A; color: #92400E; }
.cw-msg-err  { background: #FEF2F2; border: 1px solid #FCA5A5; color: #DC2626; }

.cw-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cw-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.cw-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.cw-btn-ghost {
  background: #F3F4F6;
  border: 1px solid #E5E7EB;
  color: #6B7280;
}
.cw-btn-ghost:hover:not(:disabled) { background: #E5E7EB; color: #6B7280; }

.cw-btn-outline {
  background: transparent;
  border: 1px solid #FF2442;
  color: #FF2442;
}
.cw-btn-outline:hover:not(:disabled) { background: rgba(255,36,66,0.06); }

.wf-node-copywrite .mint-wf-footer {
  justify-content: space-between;
  align-items: center;
}
</style>
