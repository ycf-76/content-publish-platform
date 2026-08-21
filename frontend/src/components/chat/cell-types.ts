/**
 * Cell 类型定义 — Codex 风格消息架构
 *
 * 每种内容类型对应独立的 Cell 组件：
 * - UserCell:      用户消息
 * - AssistantCell: AI 回复（Markdown 渲染）
 * - ThinkingCell:  思考过程（dim + italic，完成后折叠）
 * - ExecCell:      工具调用输出（后期待接入）
 * - PlanCell:      计划步骤 checkbox（后期待接入）
 * - DiffCell:      代码变更 diff（后期待接入）
 */

export type CellType = 'user' | 'assistant' | 'thinking' | 'exec' | 'plan' | 'diff'

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
}

export interface AgentStep {
  nodeKey: string
  nodeLabel: string
  status: 'pending' | 'running' | 'completed' | 'error' | 'awaiting_review'
  percent: number
}

export type RecoveryStatus = 'retrying' | 'failed' | 'success' | 'circuit_open'

export interface RecoveryDecision {
  title: string
  description?: string
}

export interface AgentMeta {
  workflowId: string | null
  intent?: { action: string; params: Record<string, unknown>; confidence: number }
  workflowStatus?: 'running' | 'awaiting_review' | 'suspended' | 'completed' | 'error'
  currentStep?: string
  steps?: AgentStep[]
  totalPercent?: number
  recoveryStatus?: RecoveryStatus
  recoveryStrategy?: string
  recoveryAttempt?: number
  recoveryMessage?: string
  pendingDecision?: RecoveryDecision
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
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

export function countLines(text: string): number {
  if (!text) return 0
  return text.split('\n').length
}

export function getThinkingSummary(text: string): string {
  if (!text) return ''
  const lines = countLines(text)
  return `思考过程 (${lines}行)`
}

export function getThinkingPreview(text: string): string {
  if (!text) return 'Thinking…'
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
  if (lines.length === 0) return 'Thinking…'
  const last = lines[lines.length - 1]
  if (last.length > 80) return last.slice(0, 77) + '…'
  return last
}
