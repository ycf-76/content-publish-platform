<template>
  <div class="dsh-chat" :class="{ 'is-dark': darkTheme, 'is-hero': heroMode }">
    <!-- SVG 滤镜：马克笔背景层手绘笔触效果（仅作用于伪元素背景，不伤文字） -->
    <svg style="position:absolute;width:0;height:0" aria-hidden="true">
      <defs>
        <filter id="dsh-marker-filter">
          <feTurbulence type="turbulence" baseFrequency="0.04" numOctaves="4" result="noise" seed="3" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="2" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
    <!-- 顶部轻量 header（简化版，去掉思考按钮） -->
    <header class="dsh-header dsh-header-minimal" v-show="!heroMode">
      <div class="dsh-header-cluster">
        <button
          class="dsh-mode-toggle"
          :class="{ 'dsh-mode-active': isAgentMode }"
          @click="isAgentMode = !isAgentMode"
          :title="isAgentMode ? '切换到 Chat 模式' : '切换到 Agent 模式'"
        >
          {{ isAgentMode ? 'Agent' : 'Chat' }}
        </button>
      </div>
    </header>

    <!-- 滚动主体 -->
    <div
      class="dsh-scroll-body"
      :class="{ 'dsh-scroll-hidden': heroMode }"
      ref="scrollBodyRef"
      @scroll="onScroll"
    >
      <div v-if="!heroMode" class="dsh-column">
        <!-- 状态指示行：等待/推理中/工具执行中 -->
        <div v-if="isStreaming" class="dsh-turn-status">
          <span class="dsh-turn-status-dot"></span>
          <span class="dsh-turn-status-text">
            <template v-if="!streamingThinking && !streamingHasContent">Thinking…</template>
            <template v-else-if="streamingThinking">Reasoning…</template>
            <template v-else>Writing…</template>
          </span>
          <span class="dsh-turn-status-clock" v-if="streamingClock">{{ streamingClock }}s</span>
          <span class="dsh-turn-status-hint">esc to interrupt</span>
        </div>

        <div
          v-for="(msg, idx) in currentMessages"
          :key="idx"
          class="dsh-flow-item"
        >
          <!-- ═══ UserCell ═══ -->
          <div v-if="msg.role === 'user'" class="dsh-user-row">
            <div class="dsh-user-stack">
              <div class="dsh-bubble" v-html="renderMarkdown(msg.content)"></div>
            </div>
          </div>

          <!-- ═══ AssistantCell ═══ -->
          <div v-else-if="msg.role === 'assistant'" class="dsh-assistant-row">
            <!-- Markdown 回复主体（主内容在上） -->
            <div
              class="dsh-assistant-content"
              v-html="renderMarkdown(getTypewriterContent(msg, idx))"
            ></div>

            <!-- PlanCell: 计划步骤 — 极简终端树形 -->
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

            <!-- ExecCell: Shell 命令 — 默认折叠，点击展开 -->
            <div v-if="msg.toolCalls && msg.toolCalls.length > 0" class="dsh-exec-group">
              <div v-for="(tc, ti) in msg.toolCalls" :key="ti" class="dsh-exec-cell">
                <div class="dsh-exec-line" @click="toggleExec(idx, ti)">
                  <span class="dsh-exec-prompt">$</span>
                  <span class="dsh-exec-cmd">{{ tc.name }}</span>
                  <template v-if="tc.result">
                    <template v-if="!isExecExpanded(idx, ti)">
                      <span v-if="getResultLineCount(tc.result) > 2" class="dsh-exec-fold">… +{{ getResultLineCount(tc.result) - 2 }} lines</span>
                    </template>
                  </template>
                  <span v-if="tc.durationMs" class="dsh-exec-duration">{{ (tc.durationMs / 1000).toFixed(1) }}s</span>
                  <span class="dsh-exec-toggle">{{ isExecExpanded(idx, ti) ? '收起' : '展开' }}</span>
                </div>
                <Transition name="dsh-slide">
                  <div v-show="isExecExpanded(idx, ti) && tc.result" class="dsh-exec-body">
                    <pre class="dsh-exec-output"><code>{{ tc.result }}</code></pre>
                  </div>
                </Transition>
              </div>
            </div>

            <!-- DiffCell: 代码变更 — 文件路径 + 增删行数，默认折叠 -->
            <div v-if="msg.diffFile" class="dsh-diff">
              <div class="dsh-diff-line" @click="toggleDiff(idx)">
                <span class="dsh-diff-file">{{ msg.diffFile }}</span>
                <span class="dsh-diff-stats">
                  <span class="dsh-diff-add">+{{ msg.diffAddCount || 0 }}</span>
                  <span class="dsh-diff-del">-{{ msg.diffDelCount || 0 }}</span>
                </span>
                <span class="dsh-diff-toggle">{{ isDiffExpanded(idx) ? '收起' : '展开' }}</span>
              </div>
              <Transition name="dsh-slide">
                <div v-show="isDiffExpanded(idx) && msg.diffContent" class="dsh-diff-body">
                  <pre class="dsh-diff-output" v-html="renderDiff(msg.diffContent)"></pre>
                </div>
              </Transition>
            </div>

            <!-- AgentProgressCard: 工作流进度 -->
            <AgentProgressCard
              v-if="msg.agentMeta?.workflowId"
              :steps="msg.agentMeta.steps || []"
              :workflow-status="msg.agentMeta.workflowStatus"
              :total-percent="msg.agentMeta.totalPercent || 0"
            />

            <!-- RecoveryStatusCard: 恢复状态 -->
            <RecoveryStatusCard
              v-if="msg.agentMeta?.recoveryStatus"
              :status="msg.agentMeta.recoveryStatus"
              :strategy="msg.agentMeta.recoveryStrategy"
              :attempt="msg.agentMeta.recoveryAttempt"
              :message="msg.agentMeta.recoveryMessage"
            />

            <!-- RecoveryDecisionCard: 结构性恢复决策 -->
            <RecoveryDecisionCard
              v-if="msg.agentMeta?.pendingDecision"
              :title="msg.agentMeta.pendingDecision.title"
              :description="msg.agentMeta.pendingDecision.description"
              @decide="onRecoveryDecide(idx, $event)"
            />

            <!-- ThinkingCell: 回复主体之下，视觉上从属于正式回复 -->
            <div v-if="msg.thinking" class="dsh-thinking" :class="{ 'dsh-thinking-glow': isLastAssistant(idx) && isStreaming && streamingThinking }">
              <!-- 流式阶段 -->
              <div v-if="isLastAssistant(idx) && isStreaming && streamingThinking" class="dsh-thinking-streaming">
                <span class="dsh-thinking-spinner"></span>
                <span class="dsh-thinking-preview" v-html="renderThinkingText(getThinkingPreview(msg.thinking))"></span>
              </div>
              <!-- 完成后：一行 dim 指示器，可点击展开 -->
              <div v-else class="dsh-thinking-line" @click="toggleThinking(idx)">
                <span class="dsh-thinking-dot"></span>
                <span class="dsh-thinking-label">{{ getThinkingSummary(msg.thinking) }}</span>
                <span class="dsh-thinking-toggle-inline">{{ isThinkingExpanded(idx) ? '收起' : '展开' }}</span>
              </div>
              <Transition name="dsh-slide">
                <div v-show="isThinkingExpanded(idx)" class="dsh-thinking-body">
                  <div class="dsh-thinking-raw" v-html="renderThinkingText(msg.thinking)"></div>
                </div>
              </Transition>
            </div>

            <!-- 操作栏 -->
            <div class="dsh-msg-actions">
              <button class="dsh-msg-action" @click="copyMessage(msg.content)" title="复制">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
            </div>

            <!-- 错误重试 -->
            <div v-if="msg.isError" class="dsh-error-row">
              <button class="dsh-retry-btn" @click="retryLastMessage">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                重试
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 回到底部浮动钮 -->
      <div v-if="showToBottom && !heroMode" class="dsh-to-bottom-slot">
        <button class="dsh-to-bottom" @click="scrollToBottom(true)" title="回到底部">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
      </div>
    </div>

    <!-- HERO 区 -->
    <div v-if="heroMode" class="dsh-hero-zone" aria-hidden="false">
      <div class="dsh-hero-stack">
        <div class="dsh-hero-brand">
          <div class="dsh-hero-logo-wrap">
            <img src="/icons/logo3.svg" alt="" class="dsh-hero-logo" />
            <div class="dsh-hero-logo-shimmer"></div>
          </div>
          <h2 class="dsh-hero-title">为你开启智能创作之旅</h2>
          <span class="dsh-hero-badge">测试版</span>
          <svg class="dsh-hero-crab" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 180" width="40" height="36">
            <defs>
              <filter id="dsh-crab-shadow" x="-10%" y="-10%" width="120%" height="130%">
                <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.12"/>
              </filter>
            </defs>
            <path d="M52,86 Q36,76 30,68" stroke="#D94F44" stroke-width="11" stroke-linecap="round" fill="none" filter="url(#dsh-crab-shadow)"/>
            <path d="M148,86 Q164,76 170,68" stroke="#D94F44" stroke-width="11" stroke-linecap="round" fill="none" filter="url(#dsh-crab-shadow)"/>
            <g filter="url(#dsh-crab-shadow)">
              <ellipse cx="26" cy="56" rx="18" ry="11" transform="rotate(-45 26 56)" fill="#E8655A"/>
              <ellipse cx="42" cy="80" rx="16" ry="10" transform="rotate(15 42 80)" fill="#E8655A"/>
            </g>
            <g filter="url(#dsh-crab-shadow)">
              <ellipse cx="174" cy="56" rx="18" ry="11" transform="rotate(45 174 56)" fill="#E8655A"/>
              <ellipse cx="158" cy="80" rx="16" ry="10" transform="rotate(-15 158 80)" fill="#E8655A"/>
            </g>
            <ellipse cx="100" cy="105" rx="58" ry="48" fill="#E8655A" filter="url(#dsh-crab-shadow)"/>
            <path d="M55,110 Q30,118 22,134" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#dsh-crab-shadow)"/>
            <path d="M52,125 Q28,136 18,154" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#dsh-crab-shadow)"/>
            <path d="M62,138 Q48,152 42,170" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#dsh-crab-shadow)"/>
            <path d="M145,110 Q170,118 178,134" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#dsh-crab-shadow)"/>
            <path d="M148,125 Q172,136 182,154" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#dsh-crab-shadow)"/>
            <path d="M138,138 Q152,152 158,170" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none" filter="url(#dsh-crab-shadow)"/>
            <circle cx="30" cy="68" r="8" fill="#D94F44"/>
            <circle cx="170" cy="68" r="8" fill="#D94F44"/>
            <circle cx="78" cy="62" r="16" fill="white" filter="url(#dsh-crab-shadow)"/>
            <circle cx="80" cy="62" r="8" fill="#1a1a1a"/>
            <circle cx="83" cy="59" r="3" fill="white"/>
            <circle cx="122" cy="62" r="16" fill="white" filter="url(#dsh-crab-shadow)"/>
            <circle cx="120" cy="62" r="8" fill="#1a1a1a"/>
            <circle cx="123" cy="59" r="3" fill="white"/>
          </svg>
        </div>
        <div class="dsh-hero-workspace-row">
          <button class="dsh-hero-chip" type="button">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>
            <span>选择一个工作区开始</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <button class="dsh-hero-chip" type="button">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            <span>标准模式</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 输入卡 -->
    <div class="dsh-composer-seat" :class="{ 'dsh-composer-hero': heroMode }">
      <svg v-if="heroMode" class="dsh-hero-glow" viewBox="0 0 1051 468" fill="none" aria-hidden="true">
        <defs>
          <filter id="dsh-hero-glow-blur" x="0" y="0" width="1051" height="468" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
            <feGaussianBlur stdDeviation="50" />
          </filter>
        </defs>
        <g filter="url(#dsh-hero-glow-blur)">
          <ellipse cx="525.5" cy="234" rx="425.5" ry="134" fill="currentColor" />
        </g>
      </svg>
      <div class="dsh-composer-card">
        <textarea
          ref="inputRef"
          v-model="inputText"
          class="dsh-input"
          placeholder="给 Pulse Studio 发送消息"
          rows="1"
          @keydown="onKeyDown"
          @input="onUserInput"
          @focus="onUserInput"
        ></textarea>
        <div class="dsh-composer-row">
          <div class="dsh-tools">
            <div class="dsh-plus-wrap">
              <button class="dsh-add" :class="{ 'dsh-add-active': highlightEnabled }" :disabled="isStreaming" @click="toggleHighlight" title="划重点">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              </button>
            </div>
          </div>
          <div class="dsh-trailing">
            <button class="dsh-model-pill" @click="cycleModel" :title="'当前模型: ' + currentModel">
              {{ currentModel }}
            </button>
            <button class="dsh-primary" :disabled="!inputText.trim() || isStreaming" @click="sendMessage" title="发送">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
          </div>
        </div>
      </div>
      <div class="dsh-composer-footer" v-if="!heroMode && lastStats">
        <span class="dsh-stats-line">
          {{ lastStats.turns }} 轮 · {{ lastStats.tokens }} tokens · {{ lastStats.latency }}ms
        </span>
      </div>
    </div>

    <CrabCompanion
      :show="crabVisible && pluginStore.isEnabled(CRAB_PLUGIN_ID)"
      :input-rect="crabInputRect"
    />
    <CatCompanion
      :show="crabVisible && pluginStore.isEnabled(CAT_PLUGIN_ID)"
      :input-rect="crabInputRect"
    />
    <SpongeBobCompanion
      :show="crabVisible && pluginStore.isEnabled(SPONGEBOB_PLUGIN_ID)"
      :input-rect="crabInputRect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { usePluginStore } from '@/stores/plugin'
import { renderMarkdown, renderThinkingText } from './markdown-renderer'
import type { ChatMessage, Conversation, ChatStats, AgentMeta } from './cell-types'
import { getThinkingSummary, getThinkingPreview } from './cell-types'
import { useChatHistory } from '@/composables/useChatHistory'
import CrabCompanion from './CrabCompanion.vue'
import CatCompanion from './CatCompanion.vue'
import SpongeBobCompanion from './SpongeBobCompanion.vue'
import RecoveryStatusCard from './RecoveryStatusCard.vue'
import RecoveryDecisionCard from './RecoveryDecisionCard.vue'
import AgentProgressCard from './AgentProgressCard.vue'

const authStore = useAuthStore()
const pluginStore = usePluginStore()

const CRAB_PLUGIN_ID = 'crab-companion'
const CAT_PLUGIN_ID = 'cat-companion'
const SPONGEBOB_PLUGIN_ID = 'spongebob-companion'
const darkTheme = ref(false)
const { addConversation, updateTitle } = useChatHistory()

const scrollBodyRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const inputText = ref('')
const isStreaming = ref(false)
const activeConvId = ref('')

const crabVisible = ref(false)
const crabInputRect = ref<DOMRect | null>(null)
let crabRafId: number | null = null

function updateCrabPosition() {
  const seat = document.querySelector('.dsh-composer-seat:not(.dsh-composer-hero)')
  if (seat) {
    crabInputRect.value = seat.getBoundingClientRect()
  }
  if (crabVisible.value) {
    crabRafId = requestAnimationFrame(updateCrabPosition)
  }
}

watch(crabVisible, (v) => {
  if (v) {
    crabRafId = requestAnimationFrame(updateCrabPosition)
  } else if (crabRafId) {
    cancelAnimationFrame(crabRafId)
    crabRafId = null
  }
})

onUnmounted(() => {
  if (crabRafId) cancelAnimationFrame(crabRafId)
})
const lastStats = ref<ChatStats | null>(null)

const thinkingDepth = ref<'off' | 'low' | 'medium' | 'high'>('medium')
const currentModel = ref('DeepSeek-V3')

const conversations = ref<Conversation[]>([])

const heroMode = ref(true)

const streamingHasContent = ref(false)
const streamingThinking = ref(false)
const streamingClock = ref(0)
const typewriterChars = ref(0)
let typewriterTimer: ReturnType<typeof setInterval> | null = null
let streamStartTs = 0
let clockTimer: ReturnType<typeof setInterval> | null = null
let abortController: AbortController | null = null

const isAgentMode = ref(false)
const activeWorkflowId = ref<string | null>(null)
const workflowSseController = ref<AbortController | null>(null)
const activeSessionId = ref<string | null>(null)

const showToBottom = ref(false)
const highlightEnabled = ref(false)

const expandedThinking = ref<Set<number>>(new Set())
const expandedExec = ref<Set<string>>(new Set())

const thinkingLabel = computed(() => {
  const map = { off: '思考:关', low: '思考:浅', medium: '思考:中', high: '思考:深' }
  return map[thinkingDepth.value]
})

const currentMessages = computed(() => {
  const conv = conversations.value.find(c => c.id === activeConvId.value)
  return conv ? conv.messages.filter(m => m.role !== 'system') : []
})

function getTypewriterContent(msg: ChatMessage, idx: number): string {
  if (!isLastAssistant(idx) || !isStreaming) return msg.content
  return msg.content.slice(0, typewriterChars.value)
}

function startTypewriter() {
  stopTypewriter()
  typewriterChars.value = 0
  typewriterTimer = setInterval(() => {
    typewriterChars.value += 3
  }, 16)
}

function stopTypewriter() {
  if (typewriterTimer) {
    clearInterval(typewriterTimer)
    typewriterTimer = null
  }
}

function isLastAssistant(idx: number): boolean {
  const msgs = currentMessages.value
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === 'assistant') return i === idx
  }
  return false
}

function isThinkingExpanded(idx: number): boolean {
  return expandedThinking.value.has(idx)
}

function toggleThinking(idx: number) {
  const s = new Set(expandedThinking.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedThinking.value = s
}

function isExecExpanded(msgIdx: number, tcIdx: number): boolean {
  return expandedExec.value.has(`${msgIdx}-${tcIdx}`)
}

function toggleExec(msgIdx: number, tcIdx: number) {
  const key = `${msgIdx}-${tcIdx}`
  const s = new Set(expandedExec.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expandedExec.value = s
}

function getResultLineCount(result: string): number {
  if (!result) return 0
  return result.split('\n').filter(Boolean).length
}

const expandedDiff = ref<Set<number>>(new Set())

function isDiffExpanded(idx: number): boolean {
  return expandedDiff.value.has(idx)
}

function toggleDiff(idx: number) {
  const s = new Set(expandedDiff.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedDiff.value = s
}

function onRecoveryDecide(idx: number, action: 'confirm' | 'cancel') {
  const msg = currentMessages.value[idx]
  if (msg?.agentMeta) {
    // 后端 review API 尚未接入，这里先清除决策卡；后续按 action 调用 review 接口
    msg.agentMeta.pendingDecision = undefined
  }
  console.log('[recovery] decision:', action, 'message index:', idx)
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

function newConversation() {
  const id = 'conv_' + Date.now()
  const conv: Conversation = {
    id,
    title: '新会话',
    messages: [],
    createdAt: Date.now(),
  }
  conversations.value.unshift(conv)
  activeConvId.value = id
  addConversation(id, '新会话')
  inputText.value = ''
  lastStats.value = null
  heroMode.value = true
  expandedThinking.value = new Set()
  expandedExec.value = new Set()
  expandedDiff.value = new Set()
  void scrollToBottom()
}

function toggleHighlight() {
  highlightEnabled.value = !highlightEnabled.value
}

function onSwitchConv(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  activeConvId.value = v
  void scrollToBottom()
}

function deleteConversation(convId: string) {
  const idx = conversations.value.findIndex(c => c.id === convId)
  if (idx === -1) return
  conversations.value.splice(idx, 1)
  if (activeConvId.value === convId) {
    if (conversations.value.length > 0) {
      activeConvId.value = conversations.value[0].id
    } else {
      newConversation()
    }
  }
}

function cycleThinking() {
  const order: Array<'off' | 'low' | 'medium' | 'high'> = ['off', 'low', 'medium', 'high']
  const idx = order.indexOf(thinkingDepth.value)
  thinkingDepth.value = order[(idx + 1) % order.length]
}

function cycleModel() {
  const models = ['DeepSeek-V3', 'DeepSeek-R1', 'Qwen-VL']
  const idx = models.indexOf(currentModel.value)
  currentModel.value = models[(idx + 1) % models.length]
}

function copyMessage(content: string) {
  navigator.clipboard.writeText(content)
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 336) + 'px'
}

function onUserInput() {
  autoResize()
}

function onScroll() {
  const el = scrollBodyRef.value
  if (!el) return
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  showToBottom.value = dist > 120
}

async function scrollToBottom(smooth = false) {
  await nextTick()
  if (scrollBodyRef.value) {
    scrollBodyRef.value.scrollTo({
      top: scrollBodyRef.value.scrollHeight,
      behavior: smooth ? 'smooth' : 'auto',
    })
  }
}

function startClock() {
  streamStartTs = Date.now()
  streamingClock.value = 0
  clockTimer = setInterval(() => {
    streamingClock.value = Math.floor((Date.now() - streamStartTs) / 1000)
  }, 500)
}

function stopClock() {
  if (clockTimer) {
    clearInterval(clockTimer)
    clockTimer = null
  }
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (workflowSseController.value) {
      workflowSseController.value.abort()
      workflowSseController.value = null
      return
    }
    if (isStreaming.value && abortController) {
      abortController.abort()
      return
    }
  }
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function getLastUserMessage(): string {
  const conv = conversations.value.find(c => c.id === activeConvId.value)
  if (!conv) return ''
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    if (conv.messages[i].role === 'user') return conv.messages[i].content
  }
  return ''
}

function removeLastAssistantMessage() {
  const conv = conversations.value.find(c => c.id === activeConvId.value)
  if (!conv) return
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    if (conv.messages[i].role === 'assistant') {
      conv.messages.splice(i, 1)
      break
    }
  }
}

function retryLastMessage() {
  removeLastAssistantMessage()
  const lastUser = getLastUserMessage()
  if (lastUser) {
    inputText.value = lastUser
    removeLastUserMessage()
    nextTick(() => sendMessage())
  }
}

function removeLastUserMessage() {
  const conv = conversations.value.find(c => c.id === activeConvId.value)
  if (!conv) return
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    if (conv.messages[i].role === 'user') {
      conv.messages.splice(i, 1)
      break
    }
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  let conv = conversations.value.find(c => c.id === activeConvId.value)
  if (!conv) {
    newConversation()
    conv = conversations.value[0]!
  }

  conv.messages.push({ role: 'user', content: text })
  if (conv.messages.filter(m => m.role === 'user').length === 1) {
    conv.title = text.slice(0, 20) + (text.length > 20 ? '...' : '')
    updateTitle(conv.id, conv.title)
  }

  inputText.value = ''
  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
  }

  heroMode.value = false
  crabVisible.value = true
  isStreaming.value = true
  streamingHasContent.value = false
  streamingThinking.value = false
  startClock()
  startTypewriter()
  abortController = new AbortController()
  await scrollToBottom()

  const startTime = Date.now()

  try {
    if (isAgentMode.value) {
      await sendAgentMessage(conv, text)
    } else {
      await sendMessageReal(conv, startTime)
    }
  } catch (err: any) {
    const lastMsg = conv.messages[conv.messages.length - 1]
    if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content) {
      lastMsg.content = `请求失败: ${err.message || '未知错误'}`
      lastMsg.isError = true
    } else {
      conv.messages.push({
        role: 'assistant',
        content: `请求失败: ${err.message || '未知错误'}`,
        isError: true,
      })
    }
  } finally {
    isStreaming.value = false
    streamingHasContent.value = false
    streamingThinking.value = false
    abortController = null
    stopClock()
    stopTypewriter()
    await scrollToBottom()
  }
}

const AGENT_NODE_LABELS: Record<string, string> = {
  search: '搜索爆款',
  analyze: '要素分析',
  image_plan: '图片规划',
  image_gen: '图片生成',
  image_review: '图片审核',
  copywrite: '文案撰写',
  audit: '合规审核',
  final_review: '人工终审',
  publish: '发布',
}

async function sendAgentMessage(conv: Conversation, text: string) {
  const assistantMsg: ChatMessage = {
    role: 'assistant',
    content: '',
    agentMeta: {
      workflowId: null,
      steps: [],
      totalPercent: 0,
      workflowStatus: 'running',
    },
  }
  conv.messages.push(assistantMsg)

  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  try {
    const response = await fetch('/api/v1/chat/agent', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        message: text,
        mode: 'auto',
        session_id: activeSessionId.value || undefined,
      }),
      signal: abortController?.signal,
    })

    if (!response.ok) {
      const errText = await response.text()
      throw new Error(errText || `HTTP ${response.status}`)
    }

    const data = await response.json()
    if (data.session_id) activeSessionId.value = data.session_id

    if (data.status === 'blocked') {
      assistantMsg.content = data.message || '输入未通过安全校验'
      assistantMsg.isError = true
      assistantMsg.agentMeta!.workflowStatus = 'error'
      return
    }

    if (data.status === 'chat') {
      // 纯 chat：移除占位 assistant，走 /chat/completions 流式
      conv.messages.pop()
      await sendMessageReal(conv, Date.now())
      return
    }

    if (data.workflow_id) {
      assistantMsg.agentMeta!.workflowId = data.workflow_id
      assistantMsg.agentMeta!.intent = data.intent
      activeWorkflowId.value = data.workflow_id
      await subscribeWorkflowSSE(data.workflow_id, assistantMsg)
    }

    if (data.status === 'agent_output' && data.output) {
      const output = data.output
      if (output.results && Array.isArray(output.results)) {
        const count = output.results.length
        const model = output._model_used || ''
        const duration = output._duration_ms ? ` (${Math.round(output._duration_ms / 1000)}s)` : ''
        let content = ''

        if (output._message) {
          content = output._message
        } else if (output.patterns && output.insights) {
          content = `分析完成，共 ${count} 条结果${model ? ` · ${model}` : ''}${duration}\n\n`
          if (output.patterns.title_patterns?.length) {
            content += `**标题钩子**: ${output.patterns.title_patterns.map((p: any) => p.type || p.template || '').filter(Boolean).join('、')}\n`
          }
          if (output.patterns.content_structures?.length) {
            content += `**内容结构**: ${output.patterns.content_structures.map((s: any) => s.structure || s.description || '').filter(Boolean).join('、')}\n`
          }
          if (output.insights.recommendations?.length) {
            content += `**选题方向**:\n`
            for (const rec of output.insights.recommendations) {
              content += `- ${rec.topic_direction || ''}${rec.title_template ? ` → ${rec.title_template}` : ''}\n`
            }
          }
        } else {
          content = `搜索完成，找到 ${count} 条结果${duration}`
          const top5 = output.results.slice(0, 5)
          for (const r of top5) {
            content += `\n- **${r.title || '无标题'}** ❤️${r.likes || 0} 💬${r.comments || 0}`
          }
          if (count > 5) content += `\n…共 ${count} 条`
        }
        assistantMsg.content = content
      } else if (output._error) {
        assistantMsg.content = `执行失败: ${output._error}`
        assistantMsg.isError = true
      } else {
        assistantMsg.content = JSON.stringify(output, null, 2)
      }
      assistantMsg.agentMeta!.workflowStatus = 'completed'
    }
  } catch (err: any) {
    assistantMsg.content = `Agent 执行失败: ${err.message || '未知错误'}`
    assistantMsg.isError = true
    assistantMsg.agentMeta!.workflowStatus = 'error'
  }
}

async function subscribeWorkflowSSE(workflowId: string, assistantMsg: ChatMessage) {
  const controller = new AbortController()
  workflowSseController.value = controller

  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(`/api/sse/workflow/${workflowId}`, {
    headers,
    signal: controller.signal,
  })

  if (!response.ok || !response.body) {
    assistantMsg.agentMeta!.workflowStatus = 'error'
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const jsonStr = line.slice(6)
        if (!jsonStr.trim()) continue
        try {
          handleWorkflowEvent(JSON.parse(jsonStr), assistantMsg)
        } catch {
          // 忽略心跳等非 JSON 行
        }
      }
    }
  } finally {
    workflowSseController.value = null
  }
}

function _recalcPercent(meta: AgentMeta) {
  const steps = meta.steps || []
  if (steps.length === 0) { meta.totalPercent = 0; return }
  const done = steps.filter(s => s.status === 'completed').length
  meta.totalPercent = Math.round((done / steps.length) * 100)
}

function handleWorkflowEvent(event: any, assistantMsg: ChatMessage) {
  const eventType = event.type || event.event_type
  const payload = event.payload || {}
  const meta = assistantMsg.agentMeta
  if (!meta) return

  switch (eventType) {
    case 'workflow_started': {
      meta.workflowStatus = 'running'
      meta.totalPercent = 0
      break
    }
    case 'node_status_changed': {
      const nodeKey = payload.node_id || ''
      const status = payload.status || ''
      const step = meta.steps?.find(s => s.nodeKey === nodeKey)
      if (step) step.status = status
      else if (nodeKey) {
        meta.steps?.push({
          nodeKey,
          nodeLabel: AGENT_NODE_LABELS[nodeKey] || nodeKey,
          status,
          percent: status === 'completed' ? 100 : 0,
        })
      }
      _recalcPercent(meta)
      break
    }
    case 'node_completed': {
      const nodeKey = payload.node_id || ''
      const step = meta.steps?.find(s => s.nodeKey === nodeKey)
      if (step) {
        step.status = 'completed'
        step.percent = 100
      }
      _recalcPercent(meta)
      break
    }
    case 'workflow_completed': {
      meta.workflowStatus = 'completed'
      meta.totalPercent = 100
      assistantMsg.content = '工作流完成'
      break
    }
    case 'workflow_error':
    case 'workflow_failed': {
      meta.workflowStatus = 'error'
      assistantMsg.content = payload.message || payload.error_message || '工作流出错'
      assistantMsg.isError = true
      break
    }
    case 'workflow_cancelled': {
      meta.workflowStatus = 'error'
      assistantMsg.content = '工作流已取消'
      break
    }
    case 'review_required': {
      const reviewNode = payload.review_node || payload.node_id || ''
      meta.workflowStatus = 'awaiting_review'
      const step = meta.steps?.find(s => s.nodeKey === reviewNode)
      if (step) {
        step.status = 'awaiting_review'
      } else if (reviewNode) {
        meta.steps?.push({
          nodeKey: reviewNode,
          nodeLabel: AGENT_NODE_LABELS[reviewNode] || reviewNode,
          status: 'awaiting_review',
          percent: 0,
        })
      }
      break
    }
    // Recovery 事件 → RecoveryStatusCard
    case 'recovery_attempt': {
      meta.recoveryStatus = 'retrying'
      meta.recoveryStrategy = payload.strategy
      meta.recoveryAttempt = payload.attempt
      break
    }
    case 'recovery_attempt_failed': {
      meta.recoveryStatus = 'failed'
      meta.recoveryMessage = payload.error
      break
    }
    case 'recovery_success': {
      meta.recoveryStatus = 'success'
      break
    }
    case 'recovery_exhausted': {
      meta.recoveryStatus = 'failed'
      meta.recoveryMessage = payload.last_error
      break
    }
    case 'circuit_open': {
      meta.recoveryStatus = 'circuit_open'
      break
    }
    case 'intent_parsed': {
      meta.intent = {
        action: payload.action,
        params: payload.params,
        confidence: payload.confidence,
      }
      break
    }
    case 'stream_chunk': {
      assistantMsg.content += payload.chunk || ''
      break
    }
    case 'tool_call_start': {
      if (!assistantMsg.toolCalls) assistantMsg.toolCalls = []
      assistantMsg.toolCalls.push({
        id: `tc_${Date.now()}`,
        type: 'exec',
        name: payload.tool_name,
        arguments: payload.inputs || {},
      })
      break
    }
    case 'tool_call_end': {
      const last = assistantMsg.toolCalls?.[assistantMsg.toolCalls.length - 1]
      if (last) last.result = payload.summary || JSON.stringify(payload)
      break
    }
  }
}

async function sendMessageReal(conv: Conversation, startTime: number) {
  let assistantContent = ''
  let thinkingContent = ''

  const token = localStorage.getItem('token')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const messagesPayload = conv.messages.map(m => ({ role: m.role, content: m.content }))
  const response = await fetch('/api/v1/chat/completions', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      messages: messagesPayload,
      model: currentModel.value,
      stream: true,
      thinking_depth: thinkingDepth.value,
    }),
    signal: abortController?.signal,
  })

  if (!response.ok) {
    const errText = await response.text()
    throw new Error(errText || `HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  if (reader) {
    let assistantMsgPushed = false

    const ensureAssistantMsg = () => {
      if (!assistantMsgPushed) {
        conv!.messages.push({
          role: 'assistant',
          content: '',
          thinking: '',
        })
        assistantMsgPushed = true
      }
    }

    let currentEvent = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split('\n')

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
          continue
        }
        if (!line.startsWith('data: ')) {
          continue
        }
        const data = line.slice(6).trim()
        if (data === '[DONE]') {
          currentEvent = ''
          continue
        }

        try {
          // highlight 事件：用标记版本替换原文
          if (currentEvent === 'highlight') {
            if (highlightEnabled.value) {
              const parsed = JSON.parse(data)
              if (parsed.highlighted_text) {
                const lastMsg = conv.messages[conv.messages.length - 1]
                if (lastMsg && lastMsg.role === 'assistant') {
                  lastMsg.content = parsed.highlighted_text
                }
              }
            }
            currentEvent = ''
            continue
          }
          currentEvent = ''

          const parsed = JSON.parse(data)
          const delta = parsed.choices?.[0]?.delta
          const finishReason = parsed.choices?.[0]?.finish_reason
          if (!delta) continue

          if (delta.reasoning_content) {
            thinkingContent += delta.reasoning_content
            streamingThinking.value = true
            ensureAssistantMsg()
            const lastMsg = conv!.messages[conv!.messages.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.thinking = thinkingContent
            }
            await scrollToBottom()
          }

          if (delta.content) {
            assistantContent += delta.content
            streamingHasContent.value = true
            ensureAssistantMsg()
            const lastMsg = conv!.messages[conv!.messages.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.content = assistantContent
              lastMsg.thinking = thinkingContent || undefined
            }
            await scrollToBottom()
          }

          // 后期待接入: tool_call 事件解析
          // 当后端工具系统完成后，在此处解析 delta.tool_calls
          // 并写入 msg.toolCalls / msg.planSteps / msg.diffFile 等

          if (finishReason === 'stop') {
            streamingThinking.value = false
            typewriterChars.value = Infinity

            const lastMsg = conv.messages[conv.messages.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              // Source-Backed Streaming 完成阶段：
              // 用最终完整文本替换流式草稿，触发重渲染确保格式完整
              const finalContent = lastMsg.content
              lastMsg.content = ''
              void nextTick(() => {
                lastMsg.content = finalContent
              })
            }
          }
        } catch {
          // skip unparseable lines
        }
      }
    }
  }

  if (!assistantContent && !thinkingContent) {
    conv.messages.push({
      role: 'assistant',
      content: '（无回复内容）',
    })
  } else {
    const lastMsg = conv.messages[conv.messages.length - 1]
    if (lastMsg && lastMsg.role === 'assistant') {
      if (!thinkingContent) {
        lastMsg.thinking = undefined
      }
    }
  }

  const latency = Date.now() - startTime
  const userTurns = conv.messages.filter(m => m.role === 'user').length
  lastStats.value = {
    turns: userTurns,
    tokens: assistantContent.length,
    latency,
  }
}

onMounted(async () => {
  newConversation()
  await pluginStore.loadInstalledPlugins().catch(() => {})
  crabVisible.value = true
  console.log('[ChatView] crabVisible=true, isEnabled(crab-companion)=', pluginStore.isEnabled(CRAB_PLUGIN_ID))
})

watch(activeConvId, () => {
  void scrollToBottom()
})

defineExpose({ newConversation, deleteConversation })
</script>

<style>
@import 'highlight.js/styles/github.css';

.dsh-chat.is-dark .hljs {
  background: transparent;
  color: #c9d1d9;
}
</style>

<style scoped>
.dsh-chat {
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  overflow: hidden;
  --dsh-bg: #ffffff;
  --dsh-surface: #ffffff;
  --dsh-card: #ffffff;
  --dsh-input-surface: #f7f7f8;
  --dsh-border: rgba(0, 0, 0, 0.10);
  --dsh-border-thin: rgba(0, 0, 0, 0.07);
  --dsh-border-strong: rgba(0, 0, 0, 0.16);
  --dsh-bubble: #f0f0f0;
  --dsh-text-1: #1a1a1a;
  --dsh-text-2: #555;
  --dsh-text-3: #888;
  --dsh-text-cap: #aaa;
  --dsh-hover: rgba(0, 0, 0, 0.04);
  --dsh-hover-solid: rgba(0, 0, 0, 0.06);
  --dsh-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  --dsh-scrollbar: rgba(0, 0, 0, 0.15);
  --dsh-scrollbar-hover: rgba(0, 0, 0, 0.25);
  --dsh-code-bg: #f4f4f5;
  --dsh-think-bg: #f7f7f8;
  --dsh-think-border: rgba(0, 0, 0, 0.08);
  --dsh-accent: #4a90d9;
  --dsh-green: #2da44e;
  --dsh-red: #cf222e;

  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--dsh-bg);
  color: var(--dsh-text-1);
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, 'PingFang SC', 'Microsoft YaHei', monospace;
  font-size: 14px;
  line-height: 22px;
  position: relative;
}

.dsh-chat.is-dark {
  --dsh-bg: #111;
  --dsh-surface: #0a0a0a;
  --dsh-card: #161616;
  --dsh-input-surface: #1a1a1a;
  --dsh-border: rgba(255, 255, 255, 0.08);
  --dsh-border-thin: rgba(255, 255, 255, 0.05);
  --dsh-border-strong: rgba(255, 255, 255, 0.14);
  --dsh-bubble: #222;
  --dsh-text-1: #e0e0e0;
  --dsh-text-2: #999;
  --dsh-text-3: #666;
  --dsh-text-cap: #555;
  --dsh-hover: rgba(255, 255, 255, 0.04);
  --dsh-hover-solid: rgba(255, 255, 255, 0.07);
  --dsh-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  --dsh-scrollbar: rgba(255, 255, 255, 0.1);
  --dsh-scrollbar-hover: rgba(255, 255, 255, 0.18);
  --dsh-code-bg: rgba(0, 0, 0, 0.3);
  --dsh-think-bg: rgba(255, 255, 255, 0.03);
  --dsh-think-border: rgba(255, 255, 255, 0.06);
  --dsh-accent: #6cb6ff;
  --dsh-green: #3fb950;
  --dsh-red: #f85149;
}

/* ============ 顶部 header ============ */
.dsh-header {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--dsh-border-thin);
  position: relative;
  z-index: 2;
}

/* 简化版header：与内容区融为一体 */
.dsh-header-minimal {
  padding: 8px 20px 0;
  border-bottom: none;
  background: transparent;
}

.dsh-header-cluster {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.dsh-header-trailing {
  flex: none;
}

.dsh-header-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--dsh-border);
  border-radius: 10px;
  background: var(--dsh-card);
  color: var(--dsh-text-1);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.dsh-header-btn:hover {
  background: var(--dsh-hover);
  border-color: var(--dsh-border-strong);
}

.dsh-conv-switcher {
  min-width: 0;
}

.dsh-conv-select {
  height: 32px;
  max-width: 220px;
  padding: 0 24px 0 10px;
  border: 1px solid var(--dsh-border);
  border-radius: 10px;
  background: var(--dsh-card);
  color: var(--dsh-text-1);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  appearance: none;
  outline: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 4.5L6 7.5L9 4.5' stroke='%2381858C' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 6px center;
  background-size: 12px 12px;
  transition: border-color 0.12s ease;
}

.dsh-conv-select:hover {
  border-color: var(--dsh-border-strong);
}

.dsh-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--dsh-border-thin);
  border-radius: 8px;
  background: transparent;
  color: var(--dsh-text-3);
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}

.dsh-pill:hover {
  background: var(--dsh-hover);
  color: var(--dsh-text-2);
}

.dsh-pill-active {
  background: var(--dsh-hover-solid);
  border-color: var(--dsh-border-strong);
  color: var(--dsh-text-1);
}

/* ============ 滚动主体 ============ */
.dsh-scroll-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  position: relative;
}

.dsh-scroll-body::-webkit-scrollbar {
  width: 8px;
}

.dsh-scroll-body::-webkit-scrollbar-thumb {
  background: var(--dsh-scrollbar);
  border-radius: 4px;
}

.dsh-scroll-body::-webkit-scrollbar-thumb:hover {
  background: var(--dsh-scrollbar-hover);
}

.dsh-scroll-hidden {
  display: none;
}

/* ============ Hero 阶段 ============ */
.dsh-chat.is-hero {
  justify-content: center;
}

.dsh-chat.is-hero .dsh-hero-zone {
  flex: none;
  padding-bottom: 18px;
}
.dsh-hero-zone {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.dsh-hero-glow {
  display: none;
}

.dsh-hero-stack {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  text-align: center;
  width: 100%;
  max-width: 780px;
  padding: 0 16px;
}

.dsh-hero-brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.dsh-hero-logo-wrap {
  position: relative;
  display: inline-flex;
  overflow: hidden;
  border-radius: 8px;
  flex: none;
}

.dsh-hero-logo {
  height: 64px;
  width: auto;
  object-fit: contain;
  opacity: 0.92;
  display: block;
}

.dsh-hero-logo-shimmer {
  position: absolute;
  top: -10%;
  left: -120%;
  width: 80%;
  height: 120%;
  background: linear-gradient(
    105deg,
    transparent 20%,
    rgba(255, 255, 255, 0.3) 38%,
    rgba(255, 255, 255, 0.5) 50%,
    rgba(255, 255, 255, 0.3) 62%,
    transparent 80%
  );
  animation: dsh-logo-shimmer 2s ease-in-out infinite;
  pointer-events: none;
}

@keyframes dsh-logo-shimmer {
  0% { left: -100%; }
  60% { left: 150%; }
  100% { left: 150%; }
}

.dsh-hero-badge {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 4px;
  border: 1px solid var(--dsh-border);
  background: transparent;
  color: var(--dsh-text-3);
  font-size: 11px;
  font-weight: 500;
  line-height: 20px;
  position: relative;
  z-index: 2;
}

.dsh-hero-crab {
  position: relative;
  z-index: 1;
  margin-left: -12px;
  margin-top: 2px;
  opacity: 0.85;
  animation: dsh-crab-peek 3s ease-in-out infinite;
  flex: none;
}

@keyframes dsh-crab-peek {
  0%, 100% { transform: translateX(-4px) rotate(-2deg); }
  50% { transform: translateX(2px) rotate(2deg); }
}

.dsh-hero-workspace-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.dsh-hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px 0 12px;
  border: 1px solid var(--dsh-border-thin);
  border-radius: 10px;
  background: var(--dsh-card);
  color: var(--dsh-text-2);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.dsh-hero-chip:hover {
  background: var(--dsh-hover);
  border-color: var(--dsh-border-strong);
  color: var(--dsh-text-1);
}

.dsh-hero-chip svg {
  flex: none;
  color: var(--dsh-text-3);
}

/* ============ 消息列 ============ */
.dsh-column {
  max-width: 748px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px 16px 16px;
  box-sizing: border-box;
  position: relative;
  z-index: 1;
}

.dsh-flow-item {
  min-width: 0;
}

/* 思考中 shimmer 行 */
.dsh-turn-status {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: auto;
  padding: 0;
  background: transparent;
  border: none;
}

.dsh-turn-status-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--dsh-text-3);
  animation: dsh-pulse-dot 1.1.5s ease-in-out infinite;
}

@keyframes dsh-pulse-dot {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.dsh-turn-status-text {
  font-size: 13px;
  font-weight: 400;
  color: var(--dsh-text-3);
}

.dsh-turn-status-clock {
  font-size: 12px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: var(--dsh-text-cap);
}

.dsh-turn-status-hint {
  font-size: 11px;
  color: var(--dsh-text-cap);
  opacity: 0.5;
  margin-left: 4px;
}

/* ============ UserCell ══════════════════ */
.dsh-user-row {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.dsh-user-stack {
  min-width: 0;
  max-width: min(525px, 82%);
}

.dsh-bubble {
  max-width: 100%;
  background: #f3f4f6;
  color: var(--dsh-text-1);
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 8px 12px;
  font-size: 14px;
  line-height: 22px;
  word-break: break-word;
  text-align: left;
}

.dsh-bubble :deep(p) {
  margin: 0;
}

.dsh-bubble :deep(p + p) {
  margin-top: 6px;
}

/* ============ AssistantCell ══════════════════ */
.dsh-assistant-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.dsh-assistant-content :deep(p) {
  margin: 0;
}

.dsh-assistant-content :deep(p + p) {
  margin-top: 8px;
}

.dsh-assistant-content :deep(h1),
.dsh-assistant-content :deep(h2),
.dsh-assistant-content :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  color: var(--dsh-text-1);
  margin: 12px 0 4px;
  line-height: 22px;
}

.dsh-assistant-content :deep(ul) {
  margin: 4px 0;
  padding-left: 0;
  list-style: none;
}

.dsh-assistant-content :deep(ul li) {
  margin: 2px 0;
  line-height: 20px;
  padding-left: 14px;
  position: relative;
}

.dsh-assistant-content :deep(ul li::before) {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--dsh-text-3);
}

.dsh-assistant-content :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}

.dsh-assistant-content :deep(ol li) {
  margin: 2px 0;
  line-height: 20px;
}

.dsh-assistant-content :deep(blockquote) {
  margin: 6px 0;
  padding: 0 0 0 0;
  border-left: none;
  color: var(--dsh-text-2);
  font-size: 13px;
}

.dsh-assistant-content :deep(blockquote p) {
  margin: 0;
  padding-left: 14px;
  position: relative;
}

.dsh-assistant-content :deep(blockquote p::before) {
  content: '│';
  position: absolute;
  left: 0;
  color: var(--dsh-text-cap);
  font-weight: var(--fw-light, 300);
}

.dsh-assistant-content :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 13px;
  width: 100%;
  overflow-x: auto;
  display: block;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
}

.dsh-assistant-content :deep(th),
.dsh-assistant-content :deep(td) {
  border: none;
  padding: 3px 10px;
  text-align: left;
  border-bottom: 1px solid var(--dsh-border-thin);
}

.dsh-assistant-content :deep(th) {
  border-bottom: 2px solid var(--dsh-border-strong);
  font-weight: 600;
  color: var(--dsh-text-1);
}

.dsh-assistant-content :deep(td) {
  color: var(--dsh-text-2);
}

.dsh-assistant-content :deep(tr:last-child td) {
  border-bottom: none;
}

.dsh-assistant-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--dsh-border-thin);
  margin: 10px 0;
}

.dsh-assistant-content :deep(.dsh-link-text) {
  color: var(--dsh-text-2);
}

.dsh-assistant-content :deep(a) {
  color: var(--dsh-text-2);
  text-decoration: none;
  pointer-events: none;
  cursor: default;
}

.dsh-assistant-content :deep(mark) {
  background: none;
  color: inherit;
  padding: 3px 5px 2px 3px;
  margin: 0 -2px;
  border-radius: 3px 5px 4px 3px;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
  position: relative;
}

.dsh-assistant-content :deep(mark)::after {
  content: '';
  position: absolute;
  top: -1px;
  left: -2px;
  right: -2px;
  bottom: -1px;
  background: linear-gradient(
    104deg,
    transparent 0.4%,
    rgba(250, 204, 21, 0.35) 2%,
    rgba(250, 204, 21, 0.38) 40%,
    rgba(250, 204, 21, 0.32) 60%,
    rgba(250, 204, 21, 0.36) 98%,
    transparent 99.6%
  );
  border-radius: inherit;
  filter: url(#dsh-marker-filter);
  z-index: -1;
  pointer-events: none;
}

.dsh-chat.is-dark .dsh-assistant-content :deep(mark)::after {
  background: linear-gradient(
    104deg,
    transparent 0.4%,
    rgba(250, 204, 21, 0.22) 2%,
    rgba(250, 204, 21, 0.25) 40%,
    rgba(250, 204, 21, 0.20) 60%,
    rgba(250, 204, 21, 0.23) 98%,
    transparent 99.6%
  );
}

/* ═══ Code Block: 语法高亮 + 语言标识 ═══ */
.dsh-assistant-content :deep(.dsh-code-block) {
  position: relative;
  background: var(--dsh-code-bg);
  border: 1px solid var(--dsh-border-thin);
  border-radius: 8px;
  padding: 12px 16px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
  margin: 8px 0;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
}

.dsh-assistant-content :deep(.dsh-code-lang) {
  position: absolute;
  top: 4px;
  right: 8px;
  font-size: 10px;
  font-weight: 500;
  color: var(--dsh-text-cap);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  pointer-events: none;
}

.dsh-assistant-content :deep(.dsh-code-block code) {
  font-family: inherit;
  font-size: inherit;
  background: transparent;
  padding: 0;
}



/* ═══ ThinkingCell: Codex 风格思考过程渲染 ═══
   流式阶段：spinner + 最后3行预览（dim + italic）
   完成后：折叠为一行 dim 指示器 `思考过程 (N行)`
   展开内容：dim + italic，视觉上从属于正式回复 */
.dsh-thinking {
  position: relative;
  margin-top: 8px;
  border-radius: 10px;
  overflow: hidden;
}

/* ─── 流式阶段：spinner + 预览 ─── */
.dsh-thinking-streaming {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  margin: -10px -12px;
  overflow: hidden;
}

/* 白光扫光层 - 仅流式输出时 */
.dsh-thinking-streaming::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 60%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0) 20%,
    rgba(255, 255, 255, 0.4) 45%,
    rgba(255, 255, 255, 1) 50%,        /* 纯白核心 */
    rgba(255, 255, 255, 0.4) 55%,
    rgba(255, 255, 255, 0) 80%,
    transparent 100%
  );
  pointer-events: none;
  z-index: 10;
  animation: dsh-shimmer-sweep 1s ease-in-out infinite;
}

.dsh-chat.is-dark .dsh-thinking-streaming::before {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0) 20%,
    rgba(255, 255, 255, 0.25) 45%,
    rgba(255, 255, 255, 0.8) 50%,       /* 暗色模式稍弱但仍是白光 */
    rgba(255, 255, 255, 0.25) 55%,
    rgba(255, 255, 255, 0) 80%,
    transparent 100%
  );
}

@keyframes dsh-shimmer-sweep {
  0% { left: -60%; }
  100% { left: 160%; }
}

.dsh-thinking-spinner {
  position: relative;
  z-index: 11;
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #9ca3af;
  flex-shrink: 0;
  margin-top: 7px;
  opacity: 0.8;
  box-shadow:
    0 0 6px 2px rgba(156, 163, 175, 0.3),
    0 0 12px 4px rgba(156, 163, 175, 0.15);
  animation: dsh-spinner-pulse 1.2s ease-in-out infinite;
}

.dsh-chat.is-dark .dsh-thinking-spinner {
  background: #6b7280;
  box-shadow:
    0 0 6px 2px rgba(107, 114, 128, 0.4),
    0 0 12px 4px rgba(107, 114, 128, 0.2);
}

@keyframes dsh-spinner-pulse {
  0%, 100% {
    opacity: 0.6;
    box-shadow:
      0 0 4px 1px rgba(156, 163, 175, 0.2),
      0 0 8px 2px rgba(156, 163, 175, 0.1);
  }
  50% {
    opacity: 1;
    box-shadow:
      0 0 8px 3px rgba(156, 163, 175, 0.4),
      0 0 16px 6px rgba(156, 163, 175, 0.2);
  }
}

.dsh-thinking-preview {
  position: relative;
  z-index: 11;
  font-size: 13px;
  line-height: 1.6;
  color: var(--dsh-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
  opacity: 0.75;
}



/* ─── 完成后：折叠指示器（无扫光） ─── */
.dsh-thinking-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;
  cursor: pointer;
  user-select: none;
}

.dsh-thinking-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--dsh-text-cap);
  flex-shrink: 0;
}

.dsh-thinking-label {
  font-size: 13px;
  line-height: 1.6;
  color: var(--dsh-text-3);
}

.dsh-thinking-toggle-inline {
  font-size: 11px;
  color: var(--dsh-text-cap);
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.dsh-thinking-line:hover .dsh-thinking-toggle-inline {
  opacity: 1;
}

.dsh-thinking-body {
  padding: 6px 0 0 13px;
}

.dsh-slide-enter-active,
.dsh-slide-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}

.dsh-slide-enter-from,
.dsh-slide-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.dsh-slide-enter-to,
.dsh-slide-leave-from {
  opacity: 1;
  max-height: 2000px;
}

.dsh-thinking-raw {
  font-size: 13px;
  line-height: 1.7;
  color: var(--dsh-text-3);
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ═══ PlanCell: 计划步骤 — 极简终端树形 ═══ */
.dsh-plan {
  margin: 4px 0;
}

.dsh-plan-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--dsh-text-1);
  margin-bottom: 4px;
}

.dsh-plan-explanation {
  font-size: 13px;
  color: var(--dsh-text-2);
  margin-bottom: 6px;
}

.dsh-plan-steps {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.dsh-plan-step {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 13px;
  line-height: 20px;
}

.dsh-plan-connector {
  color: var(--dsh-text-cap);
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  font-size: 12px;
  flex-shrink: 0;
  width: 14px;
  text-align: center;
}

.dsh-plan-checkbox {
  flex: none;
  width: 14px;
  text-align: center;
  font-size: 12px;
}

.dsh-plan-step-completed .dsh-plan-checkbox {
  color: #16a34a;
}

.dsh-plan-step-active .dsh-plan-checkbox {
  color: var(--dsh-accent);
  animation: dsh-plan-pulse 1.5s ease-in-out infinite;
}

@keyframes dsh-plan-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.dsh-plan-step-pending .dsh-plan-checkbox {
  color: var(--dsh-text-cap);
}

.dsh-plan-step-completed .dsh-plan-step-text {
  color: var(--dsh-text-3);
  text-decoration: line-through;
  text-decoration-color: var(--dsh-border-strong);
}

.dsh-plan-step-active .dsh-plan-step-text {
  color: var(--dsh-text-1);
  font-weight: 500;
}

.dsh-plan-step-pending .dsh-plan-step-text {
  color: var(--dsh-text-3);
}

/* ═══ ExecCell: Shell 命令 — 极简终端风格 ═══ */
.dsh-exec-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 4px 0;
}

.dsh-exec-cell {
  position: relative;
}

.dsh-exec-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 22px;
  cursor: pointer;
  user-select: none;
}

.dsh-exec-prompt {
  color: var(--dsh-text-3);
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  font-size: 12px;
  flex-shrink: 0;
}

.dsh-exec-cmd {
  color: var(--dsh-text-2);
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.dsh-exec-fold {
  color: var(--dsh-text-3);
  font-size: 11px;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  flex-shrink: 0;
}

.dsh-exec-duration {
  color: var(--dsh-text-cap);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.dsh-exec-toggle {
  font-size: 11px;
  color: var(--dsh-text-cap);
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.dsh-exec-line:hover .dsh-exec-toggle {
  opacity: 1;
}

.dsh-exec-body {
  padding: 4px 0 4px 16px;
}

.dsh-exec-output {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--dsh-text-2);
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}

/* ═══ DiffCell: 代码变更 — 极简终端风格 ═══ */
.dsh-diff {
  margin: 4px 0;
}

.dsh-diff-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;
  cursor: pointer;
  user-select: none;
}

.dsh-diff-file {
  color: var(--dsh-text-2);
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.dsh-diff-stats {
  display: flex;
  gap: 4px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  flex-shrink: 0;
}

.dsh-diff-add {
  color: #16a34a;
}

.dsh-diff-del {
  color: #dc2626;
}

.dsh-diff-toggle {
  font-size: 11px;
  color: var(--dsh-text-cap);
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.dsh-diff-line:hover .dsh-diff-toggle {
  opacity: 1;
}

.dsh-diff-body {
  padding: 4px 0 4px 16px;
}

.dsh-diff-output {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow-y: auto;
}

.dsh-diff-line-add {
  color: #16a34a;
}

.dsh-diff-line-del {
  color: #dc2626;
}

.dsh-diff-line-hunk {
  color: var(--dsh-text-3);
  font-style: italic;
}

/* ═══ 回复主体 + 流式 Bloom ═══
   text-shadow 多层扩散 + 底部暖边
   光从文字本身发出，底部有"正在书写"的暖光 */
.dsh-assistant-content {
  position: relative;
  font-size: 14px;
  line-height: 22px;
  color: var(--dsh-text-1);
  word-break: break-word;
  overflow-wrap: anywhere;
}

/* ═══ 消息操作栏 ═══ */
.dsh-msg-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.12s ease;
}

.dsh-flow-item:hover .dsh-msg-actions {
  opacity: 1;
}

.dsh-msg-action {
  padding: 4px 6px;
  border: none;
  background: none;
  color: var(--dsh-text-cap);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s ease, color 0.12s ease;
}

.dsh-msg-action:hover {
  background: var(--dsh-hover-solid);
  color: var(--dsh-text-2);
}

/* ═══ 错误重试 ═══ */
.dsh-error-row {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.dsh-retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 12px;
  border: 1px solid var(--dsh-border);
  border-radius: 8px;
  background: var(--dsh-card);
  color: var(--dsh-text-2);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
}

.dsh-retry-btn:hover {
  background: var(--dsh-hover);
  border-color: var(--dsh-border-strong);
  color: var(--dsh-text-1);
}

/* ═══ 回到底部浮动钮 ═══ */
.dsh-to-bottom-slot {
  position: sticky;
  bottom: 16px;
  z-index: 8;
  height: 0;
  display: flex;
  justify-content: flex-end;
  padding-right: max(16px, calc((100% - 748px) / 2));
  pointer-events: none;
}

.dsh-to-bottom {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-top: -34px;
  padding: 0;
  border: 1px solid var(--dsh-border);
  border-radius: 999px;
  color: var(--dsh-text-1);
  background: var(--dsh-card);
  box-shadow: var(--dsh-shadow);
  cursor: pointer;
  pointer-events: auto;
  transition: background 0.12s ease;
}

.dsh-to-bottom:hover {
  background: var(--dsh-hover);
}

/* HERO 模式下的 composer */
.dsh-composer-hero {
  position: relative;
  bottom: auto;
  z-index: 1;
  background: transparent;
  padding: 0 16px 8px;
  flex: none;
  width: 100%;
  animation: dsh-composer-hero-in 0.45s cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

.dsh-composer-hero .dsh-composer-card {
  max-width: 680px;
  margin: 0 auto;
}

/* DOCKED 模式下的 composer */
.dsh-composer-seat:not(.dsh-composer-hero) {
  position: sticky;
  bottom: 0;
  z-index: 7;
  background: linear-gradient(180deg, color-mix(in srgb, var(--dsh-bg) 0%, transparent) 0px, var(--dsh-bg) 36px);
  padding: 0 16px 8px;
  animation: dsh-composer-dock-in 0.45s cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

@keyframes dsh-composer-dock-in {
  from { transform: translateY(40vh); }
  to { transform: translateY(0); }
}

@keyframes dsh-composer-hero-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .dsh-composer-hero,
  .dsh-composer-seat:not(.dsh-composer-hero) {
    animation: none;
  }
  .dsh-turn-status-dot {
    animation: none;
    opacity: 1;
  }
  .dsh-thinking-spinner {
    animation: none;
  }
  .dsh-thinking-glow .dsh-thinking-preview {
    animation: none;
  }
  .dsh-plan-step-active .dsh-plan-checkbox {
    animation: none;
  }
}

/* ═══ 浮动输入卡 ═══ */
.dsh-composer-card {
  box-sizing: border-box;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  max-width: 780px;
  margin: 0 auto;
  padding-top: 10px;
  border: 1px solid var(--dsh-border-thin);
  border-radius: 12px;
  background: var(--dsh-input-surface);
}

.dsh-input {
  display: block;
  width: 100%;
  box-sizing: border-box;
  border: none;
  outline: none;
  background: transparent;
  color: var(--dsh-text-1);
  font-size: 14px;
  line-height: 22px;
  font-family: inherit;
  resize: none;
  max-height: 336px;
  padding: 4px 16px 0 16px;
  overflow-y: auto;
}

.dsh-input::placeholder {
  color: var(--dsh-text-cap);
  user-select: none;
}

.dsh-input::-webkit-scrollbar {
  width: 6px;
}

.dsh-input::-webkit-scrollbar-thumb {
  background: var(--dsh-scrollbar);
  border-radius: 3px;
}

.dsh-composer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 8px 6px;
}

.dsh-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dsh-plus-wrap {
  position: relative;
}

.dsh-add {
  display: grid;
  place-items: center;
  flex: none;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 999px;
  background: var(--dsh-hover-solid);
  color: var(--dsh-text-1);
  cursor: pointer;
  transition: background 0.12s ease;
}

.dsh-add:hover:not(:disabled) {
  background: var(--dsh-border-strong);
}

.dsh-add:disabled {
  opacity: 0.5;
  cursor: default;
}

.dsh-add-active {
  background: rgba(250, 204, 21, 0.2);
  color: #ca8a04;
}

.dsh-plus-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  min-width: 180px;
  background: var(--dsh-bg);
  border: 1px solid var(--dsh-border);
  border-radius: 10px;
  padding: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  z-index: 100;
}

.dsh-plus-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--dsh-text-1);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.12s;
}

.dsh-plus-item:hover {
  background: var(--dsh-hover);
}

.dsh-plus-item-active {
  background: rgba(250, 204, 21, 0.08);
  color: var(--dsh-text-1);
}

.dsh-plus-item-active:hover {
  background: rgba(250, 204, 21, 0.14);
}

.dsh-plus-check {
  margin-left: auto;
  color: #eab308;
  font-size: 12px;
}

.dsh-slide-up-enter-active,
.dsh-slide-up-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.dsh-slide-up-enter-from,
.dsh-slide-up-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

.dsh-trailing {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dsh-model-pill {
  padding: 4px 10px;
  border: 1px solid var(--dsh-border);
  border-radius: 999px;
  background: transparent;
  color: var(--dsh-text-3);
  font-size: 11px;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  white-space: nowrap;
}

.dsh-model-pill:hover {
  background: var(--dsh-hover);
  color: var(--dsh-text-2);
}

.dsh-mode-toggle {
  padding: 4px 12px;
  border: 1px solid var(--dsh-border);
  border-radius: 999px;
  background: transparent;
  color: var(--dsh-text-3);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  white-space: nowrap;
}

.dsh-mode-toggle:hover {
  background: var(--dsh-hover);
  color: var(--dsh-text-2);
}

.dsh-mode-active {
  background: var(--dsh-text-1);
  color: var(--dsh-bg);
  border-color: var(--dsh-text-1);
}

.dsh-primary {
  display: grid;
  place-items: center;
  flex: none;
  width: 32px;
  height: 32px;
  border: 1px solid var(--dsh-border);
  border-radius: 999px;
  background: var(--dsh-text-1);
  color: var(--dsh-bg);
  cursor: pointer;
  transition: opacity 0.12s ease;
}

.dsh-primary:hover:not(:disabled) {
  opacity: 0.85;
}

.dsh-primary:disabled {
  opacity: 0.4;
  cursor: default;
}

.dsh-composer-footer {
  display: flex;
  justify-content: flex-end;
  min-height: 16px;
  padding: 0 4px;
}

.dsh-stats-line {
  font-size: 11px;
  color: var(--dsh-text-cap);
  letter-spacing: 0.3px;
}

/* ═══ 响应式 ═══ */
@media (max-width: 640px) {
  .dsh-header {
    padding: 8px 12px;
  }
  .dsh-column {
    padding: 16px 12px 12px;
  }
  .dsh-header-btn span {
    display: none;
  }
  .dsh-conv-select {
    max-width: 140px;
  }
}
</style>