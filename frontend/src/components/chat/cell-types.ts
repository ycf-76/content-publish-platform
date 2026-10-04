/**
 * Cell 类型定义 — 严格对齐 Codex CLI 源码设计
 *
 * Codex 核心架构（从源码提取）：
 *
 * 1. TurnLifecycleState: 只有 agent_turn_running: bool
 *    - start() → running=true, finish() → running=false
 *    - 没有thinking/planning/executing/responding细分
 *    - 状态细节由 StatusIndicatorState.header 字符串表达，不是枚举
 *
 * 2. StatusIndicatorState: { header: String, details: Option<String> }
 *    - header 是动态字符串："Working", "Reviewing approval request", "Thinking"
 *    - 由事件自己决定显示什么，不是预设映射
 *
 * 3. EventMsg: TurnStarted/TurnComplete/AgentMessage/AgentReasoning/
 *    ItemStarted/ItemCompleted/ExecCommandBegin/End/PlanDelta/Error
 *
 * 4. TurnItem: UserMessage/AgentMessage/Plan/Reasoning/
 *    CommandExecution/McpToolCall/WebSearch/ImageGeneration/FileChange
 *
 * 5. HistoryCell trait: display_lines() + raw_lines() + transcript_lines()
 *    - 29个实现: UserHistoryCell, AgentMessageCell, ReasoningSummaryCell,
 *      ProposedPlanCell, PlanUpdateCell, ExecCell, McpToolCallCell, etc.
 *
 * 6. Streaming: Reasoning delta 不渲染到历史，只提取 **bold** 标题作状态
 *    AgentMessage delta 流式渲染，Plan delta 只在 Plan 模式渲染
 */

// ═══════════════════════════════════════════
// Turn 生命周期（对齐 Codex turn_lifecycle.rs）
// ═══════════════════════════════════════════

/**
 * Turn 状态 — 对齐 Codex: 只有 running/not-running
 * Codex 源码: TurnLifecycleState { agent_turn_running: bool }
 * 状态文本由 StatusIndicator.header 动态决定，不是枚举映射
 */
export type TurnPhase = 'idle' | 'running' | 'done' | 'error'

/**
 * StatusIndicator — 对齐 Codex status_state.rs
 * Codex 源码: StatusIndicatorState { header: String, details: Option<String> }
 * header 是事件驱动的动态字符串，不是预设枚举
 */
export interface StatusIndicator {
  header: string
  details?: string
}

// ═══════════════════════════════════════════
// Item 事件模型（对齐 Codex protocol.rs EventMsg）
// ═══════════════════════════════════════════

/**
 * Item 生命周期 — 对齐 Codex: item.started / item.updated / item.completed
 */
export type ItemLifecycle = 'started' | 'updated' | 'completed' | 'error'

/**
 * DisplayItem — 对齐 Codex TurnItem 枚举
 * Codex 源码: TurnItem { UserMessage, AgentMessage, Plan, Reasoning,
 *   CommandExecution, McpToolCall, WebSearch, ImageGeneration, FileChange }
 */
export interface DisplayItem {
  id: string
  type: DisplayItemType
  lifecycle: ItemLifecycle
  label: string
  detail?: string
  emoji?: string
  durationMs?: number
}

export type DisplayItemType =
  | 'text'
  | 'tool_call'
  | 'tool_result'
  | 'step_progress'
  | 'plan'
  | 'review'
  | 'error'

// ═══════════════════════════════════════════
// 基础 Cell 类型
// ═══════════════════════════════════════════

export type CellType = 'user' | 'assistant' | 'thinking' | 'exec' | 'plan' | 'diff' | 'artifact'

export interface PlanStep {
  step: string
  status: 'pending' | 'in_progress' | 'completed'
}

export interface ToolCall {
  id: string
  type: CellType
  name: string
  arguments: Record<string, unknown>
  result?: string
  exitCode?: number
  durationMs?: number
  displayArgs?: string
  iteration?: number
  status?: 'running' | 'done' | 'error'
  subAgentId?: string
}

export interface ArtifactCell {
  id: string
  type: 'cover_draft' | 'text_draft' | 'image_preview'
  title: string
  data: Record<string, unknown>
  actions?: { label: string; event: string }[]
}

export interface AgentStep {
  nodeKey: string
  nodeLabel: string
  status: 'pending' | 'running' | 'completed' | 'error' | 'awaiting_review'
  percent: number
}

export type RecoveryStatus = 'retrying' | 'failed' | 'success' | 'circuit_open'

export interface GovernanceEvent {
  type: string
  timestamp: number
  details: Record<string, unknown>
}

export interface GovernanceState {
  budgetWarning: boolean
  budgetRemaining: number | null
  compacted: boolean
  compactCount: number
  retrying: boolean
  retryCount: number
  contextWindowNearLimit: boolean
  recentEvents: GovernanceEvent[]
}

export interface CollabAgent {
  agentId: string
  name: string
  path: string
  parentId: string | null
  depth: number
  role: string | null
  status: 'pending' | 'running' | 'completed' | 'error' | 'interrupted'
  error?: string | null
  taskDescription?: string
  forkMode?: string
}

export interface CollabState {
  agents: CollabAgent[]
  activeCount: number
  maxConcurrent: number
  maxDepth: number
  poolAvailable: number
  poolActive: number
  collabMode: 'explicit' | 'proactive' | 'disabled'
}

export interface RecoveryDecision {
  title: string
  description?: string
}

export interface AgentMeta {
  workflowId: string | null
  intent?: { action: string; tools?: string[]; topic?: string; params: Record<string, unknown>; confidence: number }
  workflowStatus?: 'running' | 'awaiting_review' | 'awaiting_confirmation' | 'awaiting_clarification' | 'suspended' | 'completed' | 'error'
  currentStep?: string
  steps?: AgentStep[]
  totalPercent?: number
  recoveryStatus?: RecoveryStatus
  recoveryStrategy?: string
  recoveryAttempt?: number
  recoveryMessage?: string
  pendingDecision?: RecoveryDecision
  governance?: GovernanceState
  collab?: CollabState
  reviewImages?: string[]
  reviewContent?: { title: string; body: string; tags: string[] }
  videoResult?: { media_url: string; publish_status: string; post_id: string; message: string }
  cardDraft?: { title?: string; template?: string; pages: any[]; pngUrls: string[]; htmlUrls: string[] }
  displayItems?: DisplayItem[]
  /** Turn 阶段 — 对齐 Codex: idle/running/done/error */
  turnPhase?: TurnPhase
  /** StatusIndicator — 对齐 Codex: 事件驱动的动态状态文本 */
  statusIndicator?: StatusIndicator
  planSteps?: string[]
  strategy?: string
  optionalTools?: string[]
  rollback?: Record<string, string>
  contextUsed?: string
  loopStatePath?: string
  confirmationPrompt?: string
  confirmationSkill?: string
  clarificationPrompt?: string
  clarificationSkill?: string
  clarificationBatches?: any[]
  currentBatch?: number
  totalBatches?: number
  clarificationExpired?: boolean
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  reasoning?: string
  decisions?: string[]
  progress?: string[]
  errors?: string[]
  thinking?: string
  isError?: boolean
  cellType?: CellType
  toolCalls?: ToolCall[]
  planSteps?: PlanStep[]
  planExplanation?: string
  diffFile?: string
  diffContent?: string
  diffAddCount?: number
  diffDelCount?: number
  agentMeta?: AgentMeta
  _persisted?: boolean
  _streamHtml?: string
}

export interface Conversation {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: number
}

export interface ChatStats {
  turns: number
  tokens: number
  latency: number
}

// ═══════════════════════════════════════════
// Presentation Adapter（对齐 Codex HistoryCell 渲染-逻辑分离）
// ═══════════════════════════════════════════

import { getToolIcon, getNodeIcon } from './icon-map'

export function getToolDisplayLabel(toolName: string): { label: string } {
  return { label: getToolIcon(toolName).label }
}

export function getNodeDisplayLabel(nodeKey: string): { label: string } {
  return { label: getNodeIcon(nodeKey).label }
}

/**
 * 获取 Chat 模式下的状态指示器文本
 *
 * 对齐 Codex StatusIndicatorState:
 * - header 是事件驱动的动态字符串
 * - 优先使用 statusIndicator.header（事件设置的）
 * - 降级到从 workflow 状态推断
 *
 * Codex 源码: StatusIndicatorState { header: String, details: Option<String> }
 * 事件自己决定显示什么，不是预设枚举映射
 */
export function getChatStatusText(meta: AgentMeta | undefined): string {
  if (!meta) return ''

  if (meta.workflowStatus === 'completed') return ''
  if (meta.workflowStatus === 'error') return ''

  if (meta.statusIndicator?.header) {
    return meta.statusIndicator.header
  }

  if (meta.workflowStatus === 'running') {
    const activeStep = meta.steps?.find(s => s.status === 'running')
    if (activeStep) {
      const { label } = getNodeDisplayLabel(activeStep.nodeKey)
      return `${label}中…`
    }
    return '处理中…'
  }

  return ''
}

/**
 * 从 agentMeta 生成规划步骤的轻量预览文本
 * 对齐 Codex: Plan delta 只在 Plan 模式渲染
 * Chat 模式下不显示规划步骤（Codex: on_plan_delta checks active_mode_kind）
 */
export function getPlanPreviewText(meta: AgentMeta | undefined): string {
  if (!meta) return ''
  const steps = meta.planSteps
  if (!steps || steps.length === 0) return ''
  const intentAction = meta.intent?.action || ''
  const { label } = getNodeDisplayLabel(intentAction)
  const prefix = intentAction ? `${label} → ` : ''
  return prefix + steps.join(' → ')
}

// ═══════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════

export function countLines(text: string): number {
  if (!text) return 0
  return text.split('\n').length
}

const THINKING_NOISE_PATTERNS = [
  /^\s*\[progress\]\s*\[\d+\/\d+\]\s*loop\s*iter/i,
  /^\s*\[progress\]\s*\[\d+\/\d+\]/,
  /^\s*\[\d+\/\d+\]\s*loop/i,
]

function filterThinkingNoise(text: string): string {
  if (!text) return ''
  const lines = text.split('\n')
  const filtered = lines.filter(line => {
    const trimmed = line.trim()
    if (!trimmed) return false
    for (const pat of THINKING_NOISE_PATTERNS) {
      if (pat.test(trimmed)) return false
    }
    return true
  })
  return filtered.join('\n')
}

function countThinkingSteps(text: string): number {
  if (!text) return 0
  return text.split('\n').filter(l => l.trim().startsWith('[decision]')).length
}

export function getThinkingSummary(msg: ChatMessage): string {
  const parts: string[] = []
  if (msg.reasoning) {
    const lines = countLines(filterThinkingNoise(msg.reasoning))
    parts.push(`推理 (${lines}行)`)
  }
  if (msg.decisions?.length) parts.push(`${msg.decisions.length}步决策`)
  if (msg.progress?.length) parts.push(`${msg.progress.length}条进度`)
  if (msg.thinking) {
    const clean = filterThinkingNoise(msg.thinking)
    if (clean) {
      const steps = countThinkingSteps(clean)
      if (steps > 0) parts.push(`${steps}步思考`)
      else parts.push(`思考 (${countLines(clean)}行)`)
    }
  }
  if (parts.length === 0) return ''
  return parts.join(' · ')
}

export function getThinkingPreview(text: string): string {
  if (!text) return '思考中…'
  const clean = filterThinkingNoise(text)
  if (!clean) return '思考中…'
  const lines = clean.split('\n').map(l => l.trim()).filter(Boolean)
  if (lines.length === 0) return '思考中…'
  const last = lines[lines.length - 1]
  if (last.length > 80) return last.slice(0, 77) + '…'
  return last
}

export function getThinkingLiveLines(text: string, maxLines = 2): string {
  if (!text) return ''
  const clean = filterThinkingNoise(text)
  if (!clean) return ''
  const lines = clean.split('\n')
  const tail = lines.slice(-maxLines)
  return tail.join('\n')
}

/**
 * 内容净化：移除所有内部技术标记
 * 对齐 Codex: Event Channel 不穿透内部事件到 UI
 */
export function sanitizeContent(raw: string): string {
  if (!raw) return ''
  if (typeof raw !== 'string') return String(raw)
  let cleaned = raw
  const patterns = [
    /_model_used["\s:]+["\']?\w[\w-]*["\']?/g,
    /_duration_ms["\s:]+\d+/g,
    /_message["\s:]+["\'][^"\']*["\']/g,
    /未收到前端注入[^，。]*/g,
    /Data truncated for column[^，。\n]*/g,
    /SQL:\s*[^。\n]*/g,
    /\(pymysql\.err\.[A-Za-z]+\)[^。\n]*/g,
    /File\s+"[^"]+",\s*line\s+\d+/g,
    /pymysql\.err\.\w+/g,
    /image_gen\s*未收到[^\n]*/gi,
    /工作流启动失败[^\n]*/g,
    /工作流启动异常[^\n]*/g,
    /\[object Object\]/g,
  ]
  patterns.forEach(p => {
    cleaned = cleaned.replace(p, '')
  })
  // 清理内部标签及其内容（思考过程和澄清通过独立组件展示）
  const codeBlocks: string[] = []
  cleaned = cleaned.replace(/```[\s\S]*?```/g, (m) => {
    codeBlocks.push(m)
    return `\x00CB${codeBlocks.length - 1}\x00`
  })
  // <thinking> 标签（原始形式）
  cleaned = cleaned.replace(/<thinking>[\s\S]*?<\/thinking>/gi, '')
  cleaned = cleaned.replace(/<thinking>[\s\S]*$/gi, '')
  // <thinking> 标签（HTML 转义形式，防止已转义文本漏网）
  cleaned = cleaned.replace(/&lt;thinking&gt;[\s\S]*?&lt;\/thinking&gt;/gi, '')
  cleaned = cleaned.replace(/&lt;thinking&gt;[\s\S]*$/gi, '')
  cleaned = cleaned.replace(/&lt;\/thinking&gt;/gi, '')
  // <needs_clarification> 标签（原始形式）
  cleaned = cleaned.replace(/<needs_clarification>[\s\S]*?<\/needs_clarification>/gi, '')
  cleaned = cleaned.replace(/<needs_clarification>[\s\S]*$/gi, '')
  // <needs_clarification> 标签（HTML 转义形式）
  cleaned = cleaned.replace(/&lt;needs_clarification&gt;[\s\S]*?&lt;\/needs_clarification&gt;/gi, '')
  cleaned = cleaned.replace(/&lt;needs_clarification&gt;[\s\S]*$/gi, '')
  cleaned = cleaned.replace(/&lt;\/needs_clarification&gt;/gi, '')
  // 恢复代码块
  cleaned = cleaned.replace(/\x00CB(\d+)\x00/g, (_, i) => codeBlocks[Number(i)])
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n')
  return cleaned.trim()
}