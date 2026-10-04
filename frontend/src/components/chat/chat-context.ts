import { inject, provide, type Ref, type ComputedRef } from 'vue'
import type { ChatMessage, StatusIndicator, TurnPhase } from './cell-types'

export interface ChatRenderContext {
  isChatMode: ComputedRef<boolean>
  isCodexMode: ComputedRef<boolean>
  isStreaming: Ref<boolean>
  streamingMsg: Ref<ChatMessage | null>
  streamingThinking: Ref<boolean>
  streamingHasContent: Ref<boolean>
  streamingClock: Ref<number>
  currentStatusIndicator: Ref<StatusIndicator>
  isExecExpanded: (msgIdx: number, tcIdx: number) => boolean
  toggleExec: (msgIdx: number, tcIdx: number) => void
  isDiffExpanded: (idx: number) => boolean
  toggleDiff: (idx: number) => void
  isThinkingExpanded: (idx: number) => boolean
  toggleThinking: (idx: number) => void
  expandedAgentId: Ref<string | null>
  toggleAgentExpand: (agentId: string) => void
  copyMessage: (content: string) => void
  retryLastMessage: () => void
  retryWorkflow: (workflowId: string) => Promise<void>
  interruptAgent: (agentId: string) => Promise<void>
  onRecoveryDecide: (idx: number, action: 'confirm' | 'cancel') => void
  onChatReviewed: (msg: ChatMessage, action: string) => void
  onChatConfirmed: (msg: ChatMessage, action: 'approve' | 'reject', data?: any) => void
  onConfirmationExpired: (msg: ChatMessage) => void
  onChatClarified?: (msg: ChatMessage, answers: Record<string, any>, data?: any) => void
  switchCollabMode: (msg: ChatMessage, mode: string) => Promise<void>
  sendMessage: () => Promise<void>
  openInBrowser: (url: string) => void
}

const CHAT_RENDER_KEY = Symbol('chat-render-context')

export function provideChatRenderContext(ctx: ChatRenderContext) {
  provide(CHAT_RENDER_KEY, ctx)
}

export function useChatRenderContext(): ChatRenderContext {
  const ctx = inject<ChatRenderContext>(CHAT_RENDER_KEY)
  if (!ctx) throw new Error('useChatRenderContext must be used inside ChatView')
  return ctx
}