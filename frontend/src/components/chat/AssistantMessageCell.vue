<template>
  <div class="dsh-assistant-row group">
    <div v-if="getPlanPreviewText(msg.agentMeta)" class="dsh-chat-plan-preview">
      <span class="dsh-chat-plan-text">{{ getPlanPreviewText(msg.agentMeta) }}</span>
    </div>

    <ToolCallCell
      v-if="msg.toolCalls && msg.toolCalls.length > 0 && msg === ctx.streamingMsg.value"
      :tool-calls="msg.toolCalls"
      :msg-idx="idx"
    />

    <!-- ═══ DecisionCell: 决策记录（对齐 Codex DecisionCell）═══ -->
    <div v-if="msg.decisions && msg.decisions.length > 0" class="dsh-cell dsh-cell-decisions">
      <div class="dsh-cell-header" @click="toggleExpand(msg, 'decisions')">
        <CheckCircle2 :size="14" class="dsh-cell-icon" />
        <span class="dsh-cell-label">决策记录 ({{ msg.decisions.length }})</span>
        <span class="dsh-cell-chevron" :style="{ transform: isExpanded(msg, 'decisions') ? 'rotate(90deg)' : 'rotate(0deg)' }">▸</span>
      </div>
      <Transition name="dsh-slide">
        <div v-show="isExpanded(msg, 'decisions')" class="dsh-cell-body">
          <div v-for="(d, di) in msg.decisions" :key="di" class="dsh-cell-decision-item">
            <span class="dsh-cell-decision-bullet">▸</span>
            <span class="dsh-cell-decision-text">{{ d }}</span>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ═══ ProgressCell: 轻量inline进度提示（Codex中progress在StatusIndicator，不在消息体）═══ -->
    <div v-if="msg.progress && msg.progress.length > 0 && msg === ctx.streamingMsg.value && ctx.isStreaming.value" class="dsh-cell-progress-inline">
      <span class="dsh-cell-progress-inline-text">{{ msg.progress[msg.progress.length - 1] }}</span>
    </div>

    <!-- ═══ ErrorCell: 独立渲染错误（对齐 Codex ErrorCell）═══ -->
    <div v-if="msg.errors && msg.errors.length > 0" class="dsh-cell dsh-cell-errors">
      <div class="dsh-cell-header" @click="toggleExpand(msg, 'errors')">
        <AlertTriangle :size="14" class="dsh-cell-icon" />
        <span class="dsh-cell-label">错误 ({{ msg.errors.length }})</span>
        <span class="dsh-cell-chevron" :style="{ transform: isExpanded(msg, 'errors') ? 'rotate(90deg)' : 'rotate(0deg)' }">▸</span>
      </div>
      <Transition name="dsh-slide">
        <div v-show="isExpanded(msg, 'errors')" class="dsh-cell-body">
          <div v-for="(e, ei) in msg.errors" :key="ei" class="dsh-cell-error-item">{{ e }}</div>
        </div>
      </Transition>
    </div>

    <!-- ═══ AgentMarkdownCell: 正式回复内容（对齐 Codex AgentMessageCell）═══ -->
    <!--
      三态渲染（对齐 Codex 渲染态/数据态解耦）：
      - preview (streaming): _streamHtml = stableHtml + renderMarkdown(tail)，粗糙但快，服务于感知进度
      - settling: 计算落地 HTML，同帧赋值，无闪烁
      - settled (completed): _streamHtml = settledHtml = renderMarkdown(fullContent)，完整、确定、值得信任
    -->
    <div
      v-if="msg.agentMeta?.workflowStatus !== 'awaiting_confirmation' && msg.agentMeta?.workflowStatus !== 'awaiting_clarification'"
      class="dsh-assistant-content"
      :class="{
        'dsh-streaming-light': msg === ctx.streamingMsg.value && ctx.isStreaming.value && msg.content
      }"
      v-html="getSafeStreamHtml(msg)"
      @click="onContentClick"
    ></div>

    <!-- ═══ ReasoningSummaryCell: 可折叠思考过程 ═══ -->
    <div v-if="msg.reasoning" class="dsh-cell dsh-cell-reasoning" :class="{ 'dsh-cell-reasoning-streaming': isCurrentlyStreamingThinking, 'dsh-cell-reasoning-expanded': isReasoningExpanded }">
      <div class="dsh-cell-header" @click="isReasoningExpanded = !isReasoningExpanded" style="cursor:pointer;">
        <Brain :size="14" class="dsh-cell-icon" />
        <span class="dsh-cell-label">{{ isCurrentlyStreamingThinking ? '正在思考' : '思考过程' }}</span>
        <span v-if="!isReasoningExpanded" class="dsh-cell-streaming-preview" :class="{ 'dsh-cell-streaming-preview--settled': !isCurrentlyStreamingThinking }">{{ getReasoningPreview(msg.reasoning) }}</span>
        <span class="dsh-cell-chevron" :style="{ transform: isReasoningExpanded ? 'rotate(90deg)' : 'rotate(0deg)', marginLeft: 'auto', fontSize: '11px', color: 'var(--dsh-text-3)' }">▸</span>
      </div>
      <Transition name="dsh-slide">
        <div v-show="isReasoningExpanded" class="dsh-cell-reasoning-body">
          <div class="dsh-cell-reasoning-content" :class="{ 'dsh-cell-reasoning-content--streaming': isCurrentlyStreamingThinking }">{{ msg.reasoning }}</div>
        </div>
      </Transition>
    </div>

    <template v-if="ctx.isCodexMode.value">
      <div v-if="msg.planSteps && msg.planSteps.length > 0" class="dsh-plan">
        <div class="dsh-plan-label">Updated Plan</div>
        <div v-if="msg.planExplanation" class="dsh-plan-explanation">{{ msg.planExplanation }}</div>
        <div class="dsh-plan-steps">
          <div
            v-for="(step, si) in msg.planSteps"
            :key="si"
            class="dsh-plan-step"
            :class="{
              'dsh-plan-step-completed': step.status === 'completed',
              'dsh-plan-step-active': step.status === 'in_progress',
              'dsh-plan-step-pending': step.status === 'pending',
            }"
          >
            <span class="dsh-plan-connector">{{ si === msg.planSteps.length - 1 ? '└' : '├' }}</span>
            <span class="dsh-plan-checkbox">
              <template v-if="step.status === 'completed'">✔</template>
              <template v-else-if="step.status === 'in_progress'">◉</template>
              <template v-else>□</template>
            </span>
            <span class="dsh-plan-step-text">{{ step.step }}</span>
          </div>
        </div>
      </div>

      <ToolCallCell
        v-if="msg.toolCalls && msg.toolCalls.length > 0"
        :tool-calls="msg.toolCalls"
        :msg-idx="idx"
      />

      <div v-if="msg.diffFile" class="dsh-diff">
        <div class="dsh-diff-line" @click="ctx.toggleDiff(idx)">
          <span class="dsh-diff-file">{{ msg.diffFile }}</span>
          <span class="dsh-diff-stats">
            <span class="dsh-diff-add">+{{ msg.diffAddCount || 0 }}</span>
            <span class="dsh-diff-del">-{{ msg.diffDelCount || 0 }}</span>
          </span>
          <span class="dsh-diff-toggle">{{ ctx.isDiffExpanded(idx) ? '收起' : '展开' }}</span>
        </div>
        <Transition name="dsh-slide">
          <div v-show="ctx.isDiffExpanded(idx) && msg.diffContent" class="dsh-diff-body">
            <pre class="dsh-diff-output" v-html="renderDiff(msg.diffContent || '')"></pre>
          </div>
        </Transition>
      </div>

      <div v-if="msg.agentMeta?.collab?.agents?.length" class="dsh-collab-panel">
        <div class="dsh-collab-header">
          <span class="dsh-collab-title">🤝 子智能体</span>
          <select
            class="dsh-collab-mode-select"
            :value="msg.agentMeta.collab.collabMode"
            @change="ctx.switchCollabMode(msg, ($event.target as HTMLSelectElement).value)"
          >
            <option value="explicit">explicit</option>
            <option value="proactive">proactive</option>
            <option value="disabled">disabled</option>
          </select>
          <span class="dsh-collab-pool">{{ msg.agentMeta.collab.poolActive }}/{{ msg.agentMeta.collab.maxConcurrent }} 并行</span>
        </div>
        <div class="dsh-collab-agents">
          <div
            v-for="agent in msg.agentMeta.collab.agents"
            :key="agent.agentId"
            class="dsh-collab-agent"
            :class="['dsh-collab-agent--' + agent.status, { 'dsh-collab-agent--expanded': ctx.expandedAgentId.value === agent.agentId }]"
            @click="ctx.toggleAgentExpand(agent.agentId)"
          >
            <div class="dsh-collab-agent-row">
              <span class="dsh-collab-agent-dot"></span>
              <span class="dsh-collab-agent-name">{{ agent.name }}</span>
              <span v-if="agent.role" class="dsh-collab-agent-role">{{ agent.role }}</span>
              <span class="dsh-collab-agent-status" :class="'dsh-collab-agent-status--' + agent.status">{{ agent.status === 'running' ? '执行中' : agent.status === 'completed' ? '已完成' : agent.status === 'error' ? '失败' : agent.status }}</span>
              <button
                v-if="agent.status === 'running' || agent.status === 'pending'"
                class="dsh-collab-agent-interrupt"
                @click.stop="ctx.interruptAgent(agent.agentId)"
                title="中断此Agent"
              >⏹</button>
            </div>
            <div v-if="agent.taskDescription" class="dsh-collab-agent-task">
              <span class="dsh-collab-task-label">任务：</span>
              <span class="dsh-collab-task-desc">{{ agent.taskDescription }}</span>
            </div>
            <div v-if="ctx.expandedAgentId.value === agent.agentId" class="dsh-collab-agent-detail">
              <div class="dsh-collab-agent-detail-row"><span class="dsh-collab-detail-label">ID</span><span class="dsh-collab-detail-value">{{ agent.agentId }}</span></div>
              <div class="dsh-collab-agent-detail-row"><span class="dsh-collab-detail-label">Role</span><span class="dsh-collab-detail-value">{{ agent.role || '-' }}</span></div>
              <div class="dsh-collab-agent-detail-row"><span class="dsh-collab-detail-label">Depth</span><span class="dsh-collab-detail-value">{{ agent.depth }}</span></div>
              <div class="dsh-collab-agent-detail-row"><span class="dsh-collab-detail-label">Parent</span><span class="dsh-collab-detail-value">{{ agent.parentId || 'root' }}</span></div>
              <div v-if="agent.forkMode" class="dsh-collab-agent-detail-row"><span class="dsh-collab-detail-label">上下文</span><span class="dsh-collab-detail-value">{{ agent.forkMode === 'fork' ? '继承父对话' : '全新开始' }}</span></div>
              <div v-if="agent.error" class="dsh-collab-agent-detail-row"><span class="dsh-collab-detail-label">Error</span><span class="dsh-collab-detail-value dsh-collab-detail-error">{{ agent.error }}</span></div>
            </div>
          </div>
        </div>
      </div>

      <RecoveryStatusCard
        v-if="msg.agentMeta?.recoveryStatus"
        :status="msg.agentMeta.recoveryStatus"
        :strategy="msg.agentMeta.recoveryStrategy"
        :attempt="msg.agentMeta.recoveryAttempt"
        :message="msg.agentMeta.recoveryMessage"
      />

      <RecoveryDecisionCard
        v-if="msg.agentMeta?.pendingDecision"
        :title="msg.agentMeta.pendingDecision.title"
        :description="msg.agentMeta.pendingDecision.description"
        @decide="ctx.onRecoveryDecide(idx, $event)"
      />

      <div v-if="msg.isError" class="dsh-error-row">
        <button class="dsh-retry-btn" @click="ctx.retryLastMessage">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
          重试
        </button>
      </div>
    </template>

    <AgentProgressCard
      v-if="msg.agentMeta?.workflowId"
      :steps="msg.agentMeta.steps || []"
      :workflow-status="msg.agentMeta.workflowStatus"
      :total-percent="msg.agentMeta.totalPercent || 0"
      :workflow-id="msg.agentMeta.workflowId || ''"
      @retry="ctx.retryWorkflow"
    />

    <ChatReviewCard
      v-if="msg.agentMeta?.workflowId && msg.agentMeta?.workflowStatus === 'awaiting_review'"
      :workflow-id="msg.agentMeta.workflowId"
      :review-type="getReviewType(msg)"
      :images="msg.agentMeta.reviewImages"
      :content="msg.agentMeta.reviewContent"
      @reviewed="(action: string) => ctx.onChatReviewed(msg, action)"
    />

    <ChatConfirmCard
      v-if="msg.agentMeta?.workflowStatus === 'awaiting_confirmation' && msg.agentMeta?.loopStatePath"
      :session-id="sseSessionId"
      :loop-state-path="msg.agentMeta.loopStatePath"
      :prompt="msg.agentMeta.confirmationPrompt || msg.content"
      :skill-name="msg.agentMeta.confirmationSkill"
      @confirmed="(action: 'approve' | 'reject', data?: any) => ctx.onChatConfirmed(msg, action, data)"
      @expired="() => ctx.onConfirmationExpired(msg)"
    />
    <div
      v-else-if="msg.agentMeta?.workflowStatus === 'awaiting_confirmation' || msg.agentMeta?.workflowStatus === 'confirmation_expired'"
      class="dsh-confirm-lost"
    >
      <AlertTriangle :size="16" class="dsh-confirm-lost-icon" />
      <div class="dsh-confirm-lost-body">
        <p class="dsh-confirm-lost-title">有一个操作等待确认，但确认状态已失效</p>
        <p class="dsh-confirm-lost-msg">{{ msg.agentMeta.confirmationPrompt || msg.content || '请重新发起该操作' }}</p>
        <button class="dsh-confirm-lost-btn" @click="ctx.sendMessage">重新发起</button>
      </div>
    </div>

    <ChatClarificationCard
      v-if="msg.agentMeta?.workflowStatus === 'awaiting_clarification' && msg.agentMeta?.loopStatePath"
      :session-id="sseSessionId"
      :loop-state-path="msg.agentMeta.loopStatePath"
      :batches="msg.agentMeta.clarificationBatches || []"
      :prompt="msg.agentMeta.clarificationPrompt || msg.content"
      :skill-name="msg.agentMeta.clarificationSkill"
      @clarified="(answers: Record<string, any>, data?: any) => ctx.onChatClarified?.(msg, answers, data)"
      @skipped="() => ctx.onChatClarified?.(msg, {}, undefined)"
      @cancelled="() => ctx.onChatClarified?.(msg, {}, undefined)"
    />
    <div
      v-else-if="msg.agentMeta?.workflowStatus === 'awaiting_clarification'"
      class="dsh-confirm-lost"
    >
      <AlertTriangle :size="16" class="dsh-confirm-lost-icon" />
      <div class="dsh-confirm-lost-body">
        <p class="dsh-confirm-lost-title">有创作偏好等待确认，但确认状态已失效</p>
        <p class="dsh-confirm-lost-msg">{{ msg.agentMeta.clarificationPrompt || msg.content || '请重新发起该操作' }}</p>
        <button class="dsh-confirm-lost-btn" @click="ctx.sendMessage">重新发起</button>
      </div>
    </div>

    <div v-if="msg.agentMeta?.videoResult?.media_url" class="dsh-video-result">
      <video class="dsh-video-result-player" :src="msg.agentMeta.videoResult.media_url" controls preload="metadata"></video>
      <div class="dsh-video-result-meta">
        <span class="dsh-video-result-status" :class="'dsh-video-status-' + (msg.agentMeta.videoResult.publish_status || 'unknown')">
          {{ videoStatusLabel(msg.agentMeta.videoResult.publish_status) }}
        </span>
        <a v-if="msg.agentMeta.videoResult.post_id" class="dsh-video-result-link" :href="'https://www.xiaohongshu.com/explore/' + msg.agentMeta.videoResult.post_id" target="_blank" rel="noopener">查看笔记</a>
        <span v-if="msg.agentMeta.videoResult.message" class="dsh-video-result-message">{{ msg.agentMeta.videoResult.message }}</span>
      </div>
    </div>

    <ChatCardDraft
      v-if="msg.agentMeta?.cardDraft && (msg.agentMeta.cardDraft.pages?.length > 0 || msg.agentMeta.cardDraft.pngUrls?.length > 0)"
      :card-draft="msg.agentMeta.cardDraft"
      @open-studio="onOpenStudio"
    />

    <div v-if="ctx.isChatMode.value && msg.isError" class="dsh-chat-error">
      <AlertTriangle :size="14" /> <span>处理出现问题，可以重试或换个说法</span>
    </div>

    <div
      v-if="msg.content && msg !== ctx.streamingMsg.value"
      class="dsh-msg-actions"
    >
      <button class="dsh-msg-btn" :class="{ 'dsh-msg-btn--liked': feedbackState === 'like' }" @click="toggleFeedback('like')" title="有帮助">
        <ThumbsUp :size="16" :stroke-width="1.5" />
        <span v-if="likeCount > 0" class="dsh-like-count">{{ likeCount }}</span>
      </button>
      <button class="dsh-msg-btn" :class="{ 'dsh-msg-btn--disliked': feedbackState === 'dislike' }" @click="toggleFeedback('dislike')" title="无帮助">
        <ThumbsDown :size="16" :stroke-width="1.5" />
      </button>
      <button class="dsh-msg-btn" @click="onCopyMessage" title="复制">
        <ClipboardCopy :size="16" :stroke-width="1.5" />
      </button>
      <button class="dsh-msg-btn" @click="ctx.retryLastMessage" title="重新运行">
        <RotateCcw :size="16" :stroke-width="1.5" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import { useChatRenderContext } from './chat-context'
import type { ChatMessage } from './cell-types'
import { getChatStatusText, getPlanPreviewText, getToolDisplayLabel } from './cell-types'
import { renderAssistantHtml, wrapStreamHtml } from './chat-content-renderer'
import { Sparkles, BarChart3, AlertTriangle, Brain, CheckCircle2, ThumbsUp, ThumbsDown, ClipboardCopy, RotateCcw } from 'lucide-vue-next'
import ToolCallCell from './ToolCallCell.vue'
import ChatConfirmCard from './ChatConfirmCard.vue'
import ChatClarificationCard from './ChatClarificationCard.vue'

const RecoveryStatusCard = defineAsyncComponent(() => import('./RecoveryStatusCard.vue'))
const RecoveryDecisionCard = defineAsyncComponent(() => import('./RecoveryDecisionCard.vue'))
const AgentProgressCard = defineAsyncComponent(() => import('./AgentProgressCard.vue'))
const ChatReviewCard = defineAsyncComponent(() => import('./ChatReviewCard.vue'))
const ChatCardDraft = defineAsyncComponent(() => import('./ChatCardDraft.vue'))

const props = defineProps<{
  msg: ChatMessage
  idx: number
  sseSessionId: string
}>()

const ctx = useChatRenderContext()

const feedbackState = ref<'like' | 'dislike' | null>(null)
const likeCount = ref(0)
const isReasoningExpanded = ref(false)

async function onOpenStudio(workId?: string) {
  const { useWorkStore } = await import('@/stores/work')
  const workStore = useWorkStore()
  workStore.showWorkDetail = true
}

function toggleFeedback(type: 'like' | 'dislike') {
  if (type === 'like') {
    if (feedbackState.value === 'like') {
      feedbackState.value = null
      likeCount.value--
    } else {
      if (feedbackState.value === 'dislike') feedbackState.value = null
      feedbackState.value = 'like'
      likeCount.value++
    }
  } else {
    feedbackState.value = feedbackState.value === type ? null : type
  }
}

async function onCopyMessage() {
  try {
    await navigator.clipboard.writeText(props.msg.content || '')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = props.msg.content || ''
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
  showToast('已复制')
}

async function copyToClipboard(text: string, triggerEl: HTMLElement) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
  showCopyFeedback(triggerEl)
}

function showCopyFeedback(el: HTMLElement) {
  el.classList.add('dsh-copy-success')
  setTimeout(() => el.classList.remove('dsh-copy-success'), 1500)
  showToast('已复制')
}

let toastTimer: number | null = null

function showToast(message: string) {
  const existing = document.querySelector('.dsh-copy-toast')
  if (existing) existing.remove()
  if (toastTimer !== null) window.clearTimeout(toastTimer)

  const el = document.createElement('div')
  el.className = 'dsh-copy-toast'
  el.textContent = message
  document.body.appendChild(el)

  toastTimer = window.setTimeout(() => {
    el.remove()
    toastTimer = null
  }, 1600)
}

function onContentClick(e: MouseEvent) {
  const target = e.target as HTMLElement

  const linkEl = target.closest('a.dsh-link-text') as HTMLAnchorElement | null
  if (linkEl && linkEl.href) {
    const href = linkEl.href
    if (href.startsWith('http://') || href.startsWith('https://')) {
      e.preventDefault()
      e.stopPropagation()
      ctx.openInBrowser(href)
      return
    }
  }

  const codeCopyBtn = target.closest('.dsh-code-copy-btn') as HTMLElement | null
  if (codeCopyBtn) {
    const pre = codeCopyBtn.closest('.dsh-code-block')
    const code = pre?.querySelector('code')
    if (code) {
      copyToClipboard(code.textContent || '', codeCopyBtn)
    }
    e.preventDefault()
    e.stopPropagation()
    return
  }

  const inlineCode = target.closest('.dsh-inline-code') as HTMLElement | null
  if (inlineCode) {
    copyToClipboard(inlineCode.textContent || '', inlineCode)
    e.preventDefault()
    e.stopPropagation()
    return
  }
}

function extractFirstBold(text: string): string {
  if (!text) return ''
  const match = text.match(/\*\*(.+?)\*\*/)
  if (match) return match[1]
  return ''
}

const _expandedState = new WeakMap<any, Record<string, boolean>>()

function isExpanded(msg: any, key: string): boolean {
  const state = _expandedState.get(msg)
  if (state && key in state) return state[key]
  return false
}

function toggleExpand(msg: any, key: string) {
  let state = _expandedState.get(msg)
  if (!state) {
    state = {}
    _expandedState.set(msg, state)
  }
  state[key] = !state[key]
}

const isCurrentlyStreamingThinking = computed(() => {
  return props.msg === ctx.streamingMsg.value && ctx.isStreaming.value && ctx.streamingThinking.value
})

const reasoningOneLine = computed(() => {
  const raw = props.msg.reasoning || ''
  if (!raw) return ''
  const cleaned = raw
    .replace(/\*\*/g, '')
    .replace(/\*/g, '')
    .replace(/#{1,4}\s/g, '')
    .replace(/\n+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
  return cleaned
})

function getReasoningPreview(text: string): string {
  if (!text) return ''
  const cleaned = text
    .replace(/\*\*/g, '')
    .replace(/\*/g, '')
    .replace(/#{1,4}\s/g, '')
    .replace(/\n+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
  const MAX = 80
  if (cleaned.length <= MAX) return cleaned
  return '…' + cleaned.slice(cleaned.length - MAX)
}

function getSafeStreamHtml(msg: ChatMessage): string {
  if (msg._streamHtml) {
    return wrapStreamHtml(msg._streamHtml)
  }
  return renderAssistantHtml(msg.content || '')
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function videoStatusLabel(status?: string): string {
  const labels: Record<string, string> = {
    success: '已发布',
    published: '已发布',
    awaiting_manual: '待手动发布',
    failed: '发布失败',
    unknown: '发布状态未知',
  }
  return labels[status || 'unknown'] || status || '发布状态未知'
}

function getReviewType(msg: ChatMessage): 'image' | 'final' {
  const currentStep = msg.agentMeta?.currentStep || ''
  const steps = msg.agentMeta?.steps || []
  const reviewStep = steps.find(s => s.status === 'awaiting_review')
  if (reviewStep) {
    const key = reviewStep.nodeKey
    if (key === 'image_review') return 'image'
    if (key === 'final_review') return 'final'
  }
  if (currentStep.includes('图片')) return 'image'
  return 'final'
}

function renderDiff(content: string): string {
  if (!content) return ''
  return content.split('\n').map(line => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return `<span class="dsh-diff-line-add">${escapeHtml(line)}</span>`
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      return `<span class="dsh-diff-line-del">${escapeHtml(line)}</span>`
    } else if (line.startsWith('@@')) {
      return `<span class="dsh-diff-line-hunk">${escapeHtml(line)}</span>`
    }
    return escapeHtml(line)
  }).join('\n')
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
</script>