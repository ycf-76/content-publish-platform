import { ref, nextTick, type Ref, type ComputedRef } from 'vue'
import * as chatSessionsApi from '@/api/chatSessions'
import { useChatHistory } from '@/composables/useChatHistory'
import { useFileStore } from '@/stores/files'
import { useWorkspaceStore } from '@/stores/workspace'
import type { ChatMessage, Conversation, ChatStats } from '../cell-types'

function normalizeAgentMeta(raw: any): any {
  if (!raw || typeof raw !== 'object') return raw
  const meta: any = { ...raw }
  const map: Record<string, string> = {
    workflow_status: 'workflowStatus',
    loop_state_path: 'loopStatePath',
    confirmation_prompt: 'confirmationPrompt',
    confirmation_skill: 'confirmationSkill',
    clarification_prompt: 'clarificationPrompt',
    clarification_skill: 'clarificationSkill',
    clarification_batches: 'clarificationBatches',
    workflow_id: 'workflowId',
    current_step: 'currentStep',
    total_percent: 'totalPercent',
  }
  for (const [snake, camel] of Object.entries(map)) {
    if (meta[snake] !== undefined && meta[camel] === undefined) {
      meta[camel] = meta[snake]
    }
  }
  return meta
}

export interface ChatActionsDeps {
  conversations: Ref<Conversation[]>
  activeConvId: Ref<string>
  inputText: Ref<string>
  lastStats: Ref<ChatStats | null>
  heroMode: Ref<boolean>
  activeSessionId: Ref<string | null>
  chatSseController: Ref<AbortController | null>
  workflowSseController: Ref<AbortController | null>
  scrollBodyRef: Ref<HTMLElement | null>
  inputRef: Ref<HTMLTextAreaElement | null>
  resetExpandAll: () => void
}

export function useChatActions(deps: ChatActionsDeps) {
  const {
    conversations, activeConvId, inputText, lastStats, heroMode,
    activeSessionId, chatSseController, workflowSseController,
    scrollBodyRef, inputRef, resetExpandAll,
  } = deps

  const fileStore = useFileStore()
  const workspaceStore = useWorkspaceStore()
  const {
    addConversation, getSessionId, removeConversation,
    getConversationsForFolder,
  } = useChatHistory()

  function abortActiveSSE() {
    const oldChatCtrl = chatSseController.value
    if (oldChatCtrl) { oldChatCtrl.abort(); chatSseController.value = null }
    const oldWfCtrl = workflowSseController.value
    if (oldWfCtrl) { oldWfCtrl.abort(); workflowSseController.value = null }
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

  async function newConversation(folderId?: string, workId?: string) {
    abortActiveSSE()

    let sessionId: string | null = null
    try {
      const sess = await chatSessionsApi.createSession('新会话', workId, folderId || 'chat-files')
      sessionId = sess.id
      activeSessionId.value = sessionId
    } catch {
      // session creation failed, continue without backend persistence
    }

    const id = sessionId || 'conv_' + Date.now()
    const conv: Conversation = {
      id,
      title: '新会话',
      messages: [],
      createdAt: Date.now(),
    }
    conversations.value.unshift(conv)
    activeConvId.value = id
    const effectiveFolderId = folderId || 'chat-files'
    addConversation(id, '新会话', effectiveFolderId, sessionId || undefined, workId)
    fileStore.setActiveFolder(effectiveFolderId)
    inputText.value = ''
    lastStats.value = null
    heroMode.value = true
    resetExpandAll()
    nextTick(() => {
      inputRef.value?.focus()
    })
  }

  async function switchToFolder(folderId: string) {
    fileStore.setActiveFolder(folderId)
    if (folderId.startsWith('ws-')) {
      workspaceStore.setActive(folderId.slice(3))
    }
    const alreadyInFolder = !!activeConvId.value &&
      getConversationsForFolder(folderId).some(h => h.id === activeConvId.value)
    if (alreadyInFolder) {
      const conv = conversations.value.find(c => c.id === activeConvId.value)
      heroMode.value = !conv || conv.messages.length === 0
      return
    }
    await newConversation(folderId)
  }

  function onSwitchConv(e: Event) {
    const v = (e.target as HTMLSelectElement).value
    const conv = conversations.value.find(c => c.id === v)
    heroMode.value = !conv || conv.messages.length === 0
    activeConvId.value = v
    const sid = getSessionId(v) || v
    activeSessionId.value = sid
    void scrollToBottom()
  }

  function deleteConversation(convId: string) {
    const idx = conversations.value.findIndex(c => c.id === convId)
    if (idx === -1) return
    conversations.value.splice(idx, 1)
    removeConversation(convId)
    chatSessionsApi.deleteSession(convId).catch(() => {})
    if (activeConvId.value === convId) {
      abortActiveSSE()
      if (conversations.value.length > 0) {
        const next = conversations.value[0]
        activeConvId.value = next.id
        const sid = getSessionId(next.id) || next.id
        activeSessionId.value = sid
      } else {
        activeConvId.value = ''
        activeSessionId.value = null
        heroMode.value = true
      }
    }
  }

  async function switchToConversation(convId: string) {
    const conv = conversations.value.find(c => c.id === convId)
    heroMode.value = !conv || conv.messages.length === 0
    activeConvId.value = convId
    const sid = getSessionId(convId) || convId
    abortActiveSSE()
    activeSessionId.value = sid
    if (conv && conv.messages.length === 0) {
      try {
        const msgs = await chatSessionsApi.listMessages(sid)
        conv.messages = msgs.map(m => ({
          role: m.role as 'user' | 'assistant' | 'system',
          content: m.content,
          agentMeta: (normalizeAgentMeta(m.agent_meta) || {
            workflowId: null,
            steps: [],
            totalPercent: 0,
            workflowStatus: 'completed' as const,
            turnPhase: 'done' as const,
            statusIndicator: { header: '' },
          }) as any,
        })).filter(m => m.role !== 'system')
        if (conv.messages.length > 0) heroMode.value = false
        // 防御性降级：历史中残留的 awaiting_clarification 不应再交互
        for (const m of conv.messages) {
          if (m.role === 'assistant' && m.agentMeta?.workflowStatus === 'awaiting_clarification') {
            m.agentMeta.workflowStatus = 'completed'
          }
        }
      } catch {
        // failed to load messages
      }
    }
    await fileStore.loadFilesForSession(sid)
    void scrollToBottom()
  }

  function enterHeroMode() {
    heroMode.value = true
  }

  function resetToInitial() {
    activeConvId.value = ''
    heroMode.value = true
    inputText.value = ''
    lastStats.value = null
    resetExpandAll()
  }

  return {
    newConversation,
    switchToFolder,
    onSwitchConv,
    deleteConversation,
    switchToConversation,
    enterHeroMode,
    resetToInitial,
    scrollToBottom,
    normalizeAgentMeta,
  }
}