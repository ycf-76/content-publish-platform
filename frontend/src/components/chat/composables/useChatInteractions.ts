                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           import { reactive, nextTick, type Ref, type ComputedRef } from 'vue'
import { authFetch } from '@/api/client'
import type { ChatMessage, Conversation } from '../cell-types'

export interface ChatInteractionsDeps {
  conversations: Ref<Conversation[]>
  activeConvId: Ref<string>
  inputText: Ref<string>
  currentMessages: ComputedRef<ChatMessage[]>
  activeSessionId: Ref<string | null>
  chatSseController: Ref<AbortController | null>
  workflowSseController: Ref<AbortController | null>
  activeWorkflowId: Ref<string | null>
  workflowSseLastEventId: Ref<string>
  isStreaming: Ref<boolean>
  streamingMsg: Ref<ChatMessage | null>
  streamingHasContent: Ref<boolean>
  streamingThinking: Ref<boolean>
  abort: () => void
  notifyImmediateComplete: () => void
  resumeFromPause: () => void
  subscribeChatSSE: (sessionId: string, assistantMsg: ChatMessage) => Promise<void>
  sendMessageRef: Ref<() => Promise<void>>
}

export function useChatInteractions(deps: ChatInteractionsDeps) {
  const {
    conversations, activeConvId, inputText, currentMessages,
    activeSessionId, chatSseController, workflowSseController,
    activeWorkflowId, workflowSseLastEventId,
    isStreaming, streamingMsg, streamingHasContent, streamingThinking,
    abort, notifyImmediateComplete, resumeFromPause, subscribeChatSSE, sendMessageRef,
  } = deps

  function onRecoveryDecide(idx: number, action: 'confirm' | 'cancel') {
    const msg = currentMessages.value[idx]
    if (msg?.agentMeta) {
      msg.agentMeta.pendingDecision = undefined
    }
    console.log('[recovery] decision:', action, 'message index:', idx)
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

  function onChatReviewed(msg: ChatMessage, action: string) {
    if (msg.agentMeta) {
      msg.agentMeta.workflowStatus = action === 'pass' ? 'running' : 'error'
    }
  }

  function onChatConfirmed(msg: ChatMessage, action: 'approve' | 'reject', data?: any) {
    if (msg.agentMeta) {
      msg.agentMeta.workflowStatus = action === 'approve' ? 'running' : 'error'
    }
    const conv = conversations.value.find((c) => c.messages.includes(msg))
    if (!conv) return

    if (action === 'reject') {
      isStreaming.value = false
      streamingMsg.value = null
      notifyImmediateComplete()
      return
    }

    // approve: 恢复流式状态，重新订阅 SSE 接收续跑输出
    resumeFromPause()
    isStreaming.value = true
    streamingMsg.value = msg
    streamingHasContent.value = false
    streamingThinking.value = false

    // 后端已改为异步续跑：立即返回 status=resumed，结果通过 SSE 推送
    // 只需保持流式状态 + 订阅 SSE 即可
    const sid = activeSessionId.value
    if (sid) {
      subscribeChatSSE(sid, msg).catch(() => {})
    }

    if (!data) return

    if (data.status === 'rejected') {
      isStreaming.value = false
      streamingMsg.value = null
      notifyImmediateComplete()
      return
    }

    if (data.status === 'awaiting_clarification') {
      const newMsg: ChatMessage = {
        role: 'assistant',
        content: data.clarification_prompt || data.message || '需要进一步确认创作偏好',
        agentMeta: {
          workflowId: null,
          workflowStatus: 'awaiting_clarification',
          loopStatePath: data.loop_state_path,
          clarificationPrompt: data.clarification_prompt,
          clarificationSkill: data.clarification_skill,
          clarificationBatches: data.clarification_batches,
        },
      }
      conv.messages.push(newMsg)
      streamingMsg.value = newMsg
      return
    }

    if (data.status === 'awaiting_confirmation') {
      if (msg.agentMeta) {
        msg.agentMeta.workflowStatus = 'awaiting_confirmation'
        msg.agentMeta.loopStatePath = data.loop_state_path
        msg.agentMeta.confirmationPrompt = data.confirmation_prompt
        msg.agentMeta.confirmationSkill = data.confirmation_skill
      }
      msg.content = data.confirmation_prompt || data.message || '需要进一步确认操作'
      streamingMsg.value = msg
      return
    }

    if (data.status === 'completed') {
      // 后端续跑完成：先尝试通过 SSE 接收流式输出
      // SSE 会推送 agent_message_delta → 播放器渲染
      // 如果 SSE 无内容到达，用 POST 响应的 message 兜底
      const completedSid = activeSessionId.value
      if (completedSid) {
        subscribeChatSSE(completedSid, msg).catch(() => {})
        // 兜底：如果 3s 后仍无 SSE 内容，用 POST 响应填充
        const fallbackMsg = data.message || '操作已完成。'
        setTimeout(() => {
          if (!msg.content || msg.content.length < 5) {
            msg.content = fallbackMsg
          }
          if (msg.agentMeta) msg.agentMeta.workflowStatus = 'completed'
        }, 3000)
      } else {
        // 无 sessionId：直接用 POST 响应
        if (data.message) {
          msg.content = data.message
        }
        if (msg.agentMeta) msg.agentMeta.workflowStatus = 'completed'
        isStreaming.value = false
        streamingMsg.value = null
        notifyImmediateComplete()
      }
      return
    }

    // 其他 status：保持流式等 SSE
    const otherSid = activeSessionId.value
    if (otherSid) {
      subscribeChatSSE(otherSid, msg).catch(() => {})
    }
  }

  function onConfirmationExpired(msg: ChatMessage) {
    if (msg.agentMeta) {
      msg.agentMeta.workflowStatus = 'confirmation_expired'
    }
  }

  async function retryWorkflow(workflowId: string) {
    try {
      const res = await authFetch(`/api/workflows/${workflowId}/retry`, {
        method: 'POST',
      })
      if (!res.ok) {
        const err = await res.text()
        console.error('[retryWorkflow] failed:', err)
        return
      }
      const data = await res.json()
      if (data.workflow_id) {
        activeWorkflowId.value = data.workflow_id
        workflowSseLastEventId.value = ''
      }
    } catch (e) {
      console.error('[retryWorkflow] error:', e)
    }
  }

  async function switchCollabMode(msg: ChatMessage, mode: string) {
    const sessionId = activeSessionId.value
    if (!sessionId) return
    try {
      const res = await authFetch(`/api/governance/collab/${sessionId}/mode`, {
        method: 'PATCH',
        body: JSON.stringify({ mode }),
      })
      if (res.ok && msg.agentMeta?.collab) {
        msg.agentMeta.collab.collabMode = mode as 'disabled' | 'explicit' | 'proactive'
      }
    } catch (e) {
      console.error('[switchCollabMode] error:', e)
    }
  }

  async function interruptAgent(agentId: string) {
    const sessionId = activeSessionId.value
    if (!sessionId) return
    try {
      await authFetch(`/api/governance/collab/${sessionId}/interrupt`, {
        method: 'POST',
        body: JSON.stringify({ agent_id: agentId }),
      })
    } catch {
      // ignore
    }
  }

  async function confirmAction(action: "approve" | "reject", meta: any) {
    const resp = await authFetch("/api/v1/chat/confirm", {
      method: "POST",
      body: JSON.stringify({
        session_id: meta.sessionId,
        loop_state_path: meta.loopStatePath,
        action: action,
        feedback: "",
      }),
    })
    return await resp.json()
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

  function stopStreaming() {
    abort()
    if (chatSseController.value) {
      chatSseController.value.abort()
      chatSseController.value = null
    }
    if (workflowSseController.value) {
      workflowSseController.value.abort()
      workflowSseController.value = null
    }
    notifyImmediateComplete()
  }

  async function retryLastMessage() {
    if (isStreaming.value) {
      stopStreaming()
      await new Promise(r => setTimeout(r, 400))
    }
    removeLastAssistantMessage()
    const lastUser = getLastUserMessage()
    if (lastUser) {
      inputText.value = lastUser
      removeLastUserMessage()
      nextTick(() => sendMessageRef.value())
    }
  }

  const dangerDialog = reactive({
    visible: false,
    title: '',
    message: '',
    resolve: null as null | ((value: boolean) => void),
  })

  function showDangerConfirm(title: string, message: string): Promise<boolean> {
    dangerDialog.title = title
    dangerDialog.message = message
    dangerDialog.visible = true
    return new Promise<boolean>((resolve) => {
      dangerDialog.resolve = resolve
    })
  }

  function onDangerConfirm() {
    dangerDialog.resolve?.(true)
    dangerDialog.resolve = null
    dangerDialog.visible = false
  }

  function onDangerCancel() {
    dangerDialog.resolve?.(false)
    dangerDialog.resolve = null
    dangerDialog.visible = false
  }

  function copyMessage(content: string) {
    navigator.clipboard.writeText(content)
  }

  function onChatClarified(msg: ChatMessage, answers: Record<string, any>, data?: any) {
    if (msg.agentMeta) {
      msg.agentMeta.workflowStatus = 'running'
    }
    const conv = conversations.value.find((c) => c.messages.includes(msg))
    if (!conv) return

    // 把同会话中所有旧的 awaiting_clarification 消息标记为 completed，
    // 防止刷新页面时旧澄清卡片重新出现
    for (const m of conv.messages) {
      if (m !== msg && m.role === 'assistant' && m.agentMeta?.workflowStatus === 'awaiting_clarification') {
        m.agentMeta.workflowStatus = 'completed'
      }
    }

    resumeFromPause()
    isStreaming.value = true
    streamingMsg.value = msg
    streamingHasContent.value = false
    streamingThinking.value = false

    // Fix Issue 1: 清除旧的工具执行文字，显示"继续创作中"状态
    msg.content = ''

    if (!data) {
      // 网络错误或解析失败，显示加载状态
      msg.content = '正在恢复创作…'
      const sid = activeSessionId.value
      if (sid) {
        subscribeChatSSE(sid, msg).catch(() => {})
      }
      return
    }

    if (data.status === 'awaiting_clarification') {
      isStreaming.value = false
      const newMsg: ChatMessage = {
        role: 'assistant',
        content: data.clarification_prompt || data.message || '需要进一步确认创作偏好',
        agentMeta: {
          workflowId: null,
          workflowStatus: 'awaiting_clarification',
          loopStatePath: data.loop_state_path,
          clarificationPrompt: data.clarification_prompt,
          clarificationSkill: data.clarification_skill,
          clarificationBatches: data.clarification_batches,
        },
      }
      conv.messages.push(newMsg)
      streamingMsg.value = newMsg
      return
    }

    if (data.status === 'awaiting_confirmation') {
      isStreaming.value = false
      const newMsg: ChatMessage = {
        role: 'assistant',
        content: data.confirmation_prompt || data.message || '需要进一步确认操作',
        agentMeta: {
          workflowId: null,
          workflowStatus: 'awaiting_confirmation',
          loopStatePath: data.loop_state_path,
          confirmationPrompt: data.confirmation_prompt,
          confirmationSkill: data.confirmation_skill,
        },
      }
      conv.messages.push(newMsg)
      streamingMsg.value = newMsg
      return
    }

    // Fix Issue 2: completed 状态直接使用后端返回的结果，不再订阅 SSE
    // （因为 /clarify 是同步 REST 调用，SSE 事件已在执行期间发出，前端订阅时已错过）
    if (data.status === 'completed') {
      msg.content = data.message || '操作已完成。'
      if (msg.agentMeta) {
        msg.agentMeta.workflowStatus = 'completed'
      }
      isStreaming.value = false
      streamingHasContent.value = true
      notifyImmediateComplete()
      return
    }

    // 其他未知状态：尝试订阅 SSE
    msg.content = '正在继续创作…'
    const sid = activeSessionId.value
    if (sid) {
      subscribeChatSSE(sid, msg).catch(() => {})
    }
  }

  return {
    onRecoveryDecide,
    getReviewType,
    onChatReviewed,
    onChatConfirmed,
    onConfirmationExpired,
    onChatClarified,
    retryWorkflow,
    switchCollabMode,
    interruptAgent,
    confirmAction,
    getLastUserMessage,
    removeLastAssistantMessage,
    removeLastUserMessage,
    stopStreaming,
    retryLastMessage,
    dangerDialog,
    showDangerConfirm,
    onDangerConfirm,
    onDangerCancel,
    copyMessage,
  }
}