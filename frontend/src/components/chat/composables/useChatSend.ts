import type { Ref } from 'vue'
import type { Conversation, ChatMessage, ChatStats } from '../cell-types'
import { _ingestContentDelta } from './useChatSSE'
import * as chatSessionsApi from '@/api/chatSessions'
import { tryRefreshToken } from '@/api/client'
import { useChatContextStore } from '@/stores/chatContext'

export interface ChatSendDeps {
  activeWork: Ref<any>
  workStore: any
  currentModel: Ref<string>
  thinkingDepth: Ref<string>
  getAbortController: () => AbortController | null
  streamingHasContent: Ref<boolean>
  streamingThinking: Ref<boolean>
  streamingMsg: Ref<ChatMessage | null>
  isStreaming: Ref<boolean>
  notifySseComplete: () => void
  notifyImmediateComplete: () => void
  notifyAgentLoopDone: (graceMs: number) => void
  chatSseController: Ref<AbortController | null>
  scrollToBottom: () => Promise<void>
  transitionTurn: (phase: string, label?: string) => void
  highlightEnabled: Ref<boolean>
  lastStats: Ref<ChatStats | null>
}

export function useChatSend(deps: ChatSendDeps) {
  const {
    activeWork, workStore,
    currentModel, thinkingDepth,
    getAbortController, streamingHasContent, streamingThinking, streamingMsg,
    isStreaming, notifySseComplete, notifyImmediateComplete, notifyAgentLoopDone,
    chatSseController, scrollToBottom, transitionTurn, highlightEnabled, lastStats,
  } = deps

  async function sendMessageReal(
    conv: Conversation,
    startTime: number,
    sid: string | null,
    assistantMsg: ChatMessage,
  ) {
    let assistantContent = ''
    let thinkingContent = ''

    const token = localStorage.getItem('token')
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const messagesPayload = conv.messages
      .filter(m => m !== assistantMsg && m.content)
      .map(m => ({ role: m.role, content: m.content }))

    const ctxStore = useChatContextStore()
    ctxStore.bindConversation(conv.id || null)
    const contextSystemPrompt = ctxStore.buildSystemPrompt()
    if (contextSystemPrompt) {
      messagesPayload.unshift({ role: 'system', content: contextSystemPrompt })
      console.log('[sendMessageReal] contextTrack INJECTED, pinnedItems:', ctxStore.pinnedItems.length, 'promptLen:', contextSystemPrompt.length)
    } else {
      console.log('[sendMessageReal] no pinned context, skip injection')
    }
    const bodyPayload = JSON.stringify({
      messages: messagesPayload,
      model: currentModel.value,
      stream: true,
      thinking_depth: thinkingDepth.value,
    })

    let response = await fetch('/api/v1/chat/completions', {
      method: 'POST',
      headers,
      body: bodyPayload,
      signal: getAbortController()?.signal,
    })

    if (response.status === 401 && token) {
      const newToken = await tryRefreshToken()
      if (newToken) {
        headers['Authorization'] = `Bearer ${newToken}`
        response = await fetch('/api/v1/chat/completions', {
          method: 'POST',
          headers,
          body: bodyPayload,
          signal: getAbortController()?.signal,
        })
      }
    }

    if (!response.ok) {
      const errText = await response.text()
      throw new Error(errText || `HTTP ${response.status}`)
    }

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()

    if (reader) {
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
              if (!assistantMsg.reasoning) assistantMsg.reasoning = ''
              assistantMsg.reasoning += delta.reasoning_content
              assistantMsg.thinking = thinkingContent
              await scrollToBottom()
            }

            if (delta.content) {
              const clean = _ingestContentDelta(assistantMsg, delta.content)
              assistantContent += clean
              streamingHasContent.value = true
              assistantMsg.content = assistantContent
              assistantMsg.thinking = thinkingContent || assistantMsg.thinking || undefined
              streamingThinking.value = !!(assistantMsg as any)._thinkState?.inThink || !!thinkingContent
              transitionTurn('running', '生成回复中…')
            }

            if (finishReason === 'stop') {
              streamingThinking.value = false
            }
          } catch {
          }
        }
      }
    }

    const hasReasoning = !!(assistantMsg.reasoning && assistantMsg.reasoning.trim())
    if (!assistantContent && !thinkingContent && !hasReasoning) {
      assistantMsg.content = '（无回复内容）'
    } else {
      if (!thinkingContent && !hasReasoning) {
        assistantMsg.reasoning = undefined
      }
    }

    assistantMsg.agentMeta!.workflowStatus = 'completed'
    if (!assistantMsg.agentMeta!.intent) {
      assistantMsg.agentMeta!.intent = { action: 'chat', params: {}, confidence: 0.5 } as any
    }
    transitionTurn('done', '')
    if (sid) {
      chatSessionsApi.addMessage(sid, 'assistant', assistantMsg.content, assistantMsg.agentMeta).catch(() => {})
    }
    notifySseComplete()
    if (chatSseController.value) {
      chatSseController.value.abort()
    }

    const latency = Date.now() - startTime
    const userTurns = conv.messages.filter(m => m.role === 'user').length
    lastStats.value = {
      turns: userTurns,
      tokens: assistantContent.length,
      latency,
    }
  }

  return { sendMessageReal }
}