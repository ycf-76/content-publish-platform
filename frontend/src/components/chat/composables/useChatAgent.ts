import type { Ref } from 'vue'
import type { Conversation, ChatMessage } from '../cell-types'
import { sanitizeContent } from '../cell-types'
import { AGENT_NODE_LABELS, formatAgentOutput } from '../agent-output-formatter'
import { normalizeCardDraft, pickCoverUrl, pickImages } from '@/composables/cardDraft'
import * as chatSessionsApi from '@/api/chatSessions'
import { authFetch } from '@/api/client'

export interface ChatAgentDeps {
  activeWork: Ref<any>
  activeFile: Ref<any>
  workStore: any
  fileStore: any
  workspaceStore: any
  pickers: any
  sse: any
  stream: any
  showWorkDetail: Ref<boolean>
  creativePhase: Ref<string>
  modelSettings: any
  autoApproveEnabled: Ref<boolean>
  sendMessageReal: (conv: Conversation, startTime: number, sid: string | null, assistantMsg: ChatMessage) => Promise<void>
  transitionTurn: (phase: string, label?: string) => void
}

export function useChatAgent(deps: ChatAgentDeps) {
  const {
    activeWork, activeFile, workStore, fileStore, workspaceStore,
    pickers, sse, stream,
    showWorkDetail, creativePhase, modelSettings, autoApproveEnabled,
    sendMessageReal, transitionTurn,
  } = deps

  async function sendAgentMessage(conv: Conversation, text: string, startTime: number) {
    let assistantMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      reasoning: '',
      decisions: [],
      progress: [],
      errors: [],
      _streamHtml: '',
      agentMeta: {
        workflowId: null,
        steps: [],
        totalPercent: 0,
        workflowStatus: 'running',
        turnPhase: 'running',
        statusIndicator: { header: '思考中…' },
      },
    }
    conv.messages.push(assistantMsg)
    assistantMsg = conv.messages[conv.messages.length - 1]
    stream.streamingMsg.value = assistantMsg
    transitionTurn('running', '思考中…')

    let sid = sse.activeSessionId.value
    if (!sid) {
      try {
        const sessRes = await authFetch("/api/chat/sessions", {
          method: "POST",
          body: JSON.stringify({ title: text.slice(0, 30), work_id: activeWork.value?.id || null }),
        })
        if (sessRes.ok) {
          const sessData = await sessRes.json()
          sid = sessData.data?.id || sessData.id || sessData.session_id
          if (sid) sse.activeSessionId.value = sid
        }
      } catch {
      }
    }

    if (sse.chatSseController.value) {
      sse.chatSseController.value.abort()
      sse.chatSseController.value = null
    }
    if (sse.workflowSseController.value) {
      sse.workflowSseController.value.abort()
      sse.workflowSseController.value = null
    }
    // 递增消息代，防止旧 SSE replay 事件污染新消息
    if (sse.advanceMsgEpoch) sse.advanceMsgEpoch()

    if (sid) {
      const chatSseReady = sse.waitForChatSseReady ? sse.waitForChatSseReady() : Promise.resolve()
      sse.subscribeChatSSE(sid, assistantMsg).catch(() => {})
      try {
        await Promise.race([
          chatSseReady,
          new Promise<void>((resolve) => setTimeout(resolve, 3000)),
        ])
      } catch {
      }
    }

    const shouldInjectWorkContext = !!activeWork.value
    const _forceWorkCtx = workStore.buildWorkContext()
    const workCtx = shouldInjectWorkContext ? (_forceWorkCtx || undefined) : undefined

    try {
      const response = await authFetch("/api/v1/chat/agent", {
        method: 'POST',
        body: JSON.stringify({
          message: text,
          mode: 'auto',
          session_id: sid || undefined,
          agent_id: pickers.selectedAgentId.value || undefined,
          workspace_id: workspaceStore.activeWorkspaceId || undefined,
          work_context: workCtx,
          analysis_context: shouldInjectWorkContext ? (workStore.buildAnalysisPrompt() || undefined) : undefined,
          file_context: activeFile.value ? { name: activeFile.value.name, type: activeFile.value.type, size: activeFile.value.size } : undefined,
          folder_context: fileStore.activeFolderId ? {
            folderId: fileStore.activeFolderId,
            files: fileStore.getFilesForFolder(fileStore.activeFolderId).map((f: any) => ({ name: f.name, type: f.type, size: f.size })),
          } : undefined,
          model_settings: modelSettings || undefined,
          creation_type: workStore.activeCreationType || undefined,
          auto_approve: autoApproveEnabled.value,
        }),
        signal: stream.getAbortController()?.signal,
      })

      if (!response.ok) {
        if (response.status === 429) {
          assistantMsg.content = '当前并发工作流数量已达上限，请稍后再试'
          assistantMsg.isError = true
          assistantMsg.agentMeta!.workflowStatus = 'error'
          if (sid) {
            chatSessionsApi.addMessage(sid, 'assistant', assistantMsg.content, assistantMsg.agentMeta).catch(() => {})
          }
          stream.notifyImmediateComplete()
          return
        }
        const errText = await response.text()
        throw new Error(errText || `HTTP ${response.status}`)
      }

      const data = await response.json()
      if (data.session_id) sse.activeSessionId.value = data.session_id

      console.log(`[ChatAgent] API response: status=${data.status}, intent=${JSON.stringify(data.intent)}`)

      if (data.status === 'blocked') {
        assistantMsg.content = '输入未通过安全校验'
        assistantMsg.isError = true
        assistantMsg.agentMeta!.workflowStatus = 'error'
        transitionTurn('error')
        stream.notifyImmediateComplete()
        return
      }

      if (data.status === 'error') {
        assistantMsg.content = sanitizeContent(data.message || '处理出错，请稍后重试')
        assistantMsg.isError = true
        assistantMsg.agentMeta!.workflowStatus = 'error'
        transitionTurn('error')
        stream.notifyImmediateComplete()
        return
      }

      if (data.status === 'awaiting_clarification') {
        if (!assistantMsg.agentMeta) {
          assistantMsg.agentMeta = {
            workflowId: null, steps: [], totalPercent: 0,
            workflowStatus: 'awaiting_clarification', turnPhase: 'running',
            statusIndicator: { header: '等待偏好确认…' },
          } as any
        }
        assistantMsg.content = sanitizeContent(data.message || data.clarification_prompt || '需要确认创作偏好')
        assistantMsg.agentMeta!.workflowStatus = 'awaiting_clarification'
        if (data.loop_state_path) {
          assistantMsg.agentMeta!.loopStatePath = data.loop_state_path
        }
        if (data.clarification_prompt) {
          assistantMsg.agentMeta!.clarificationPrompt = data.clarification_prompt
        }
        if (data.clarification_skill) {
          assistantMsg.agentMeta!.clarificationSkill = data.clarification_skill
        }
        if (data.clarification_batches) {
          assistantMsg.agentMeta!.clarificationBatches = data.clarification_batches
        }
        console.log(
          '[ChatAgent] awaiting clarification:',
          { skill: data.clarification_skill, hasPath: !!data.loop_state_path }
        )
        transitionTurn('running', '等待偏好确认…')
        stream.notifyPaused()
        return
      }

      if (data.status === 'awaiting_confirmation') {
        if (!assistantMsg.agentMeta) {
          assistantMsg.agentMeta = {
            workflowId: null, steps: [], totalPercent: 0,
            workflowStatus: 'awaiting_confirmation', turnPhase: 'running',
            statusIndicator: { header: '等待确认…' },
          } as any
        }
        assistantMsg.content = sanitizeContent(data.message || data.confirmation_prompt || '需要确认操作')
        assistantMsg.agentMeta!.workflowStatus = 'awaiting_confirmation'
        assistantMsg.agentMeta!.intent = data.intent
        if (data.loop_state_path) {
          assistantMsg.agentMeta!.loopStatePath = data.loop_state_path
        }
        if (data.confirmation_prompt) {
          assistantMsg.agentMeta!.confirmationPrompt = data.confirmation_prompt
        }
        if (data.confirmation_skill) {
          assistantMsg.agentMeta!.confirmationSkill = data.confirmation_skill
        }
        console.log(
          '[ChatAgent] awaiting confirmation:',
          { skill: data.confirmation_skill, hasPath: !!data.loop_state_path }
        )
        transitionTurn('running', '等待确认…')
        stream.notifyPaused()
        return
      }

      if (data.status === 'chat') {
        if (data.intent) {
          assistantMsg.agentMeta!.intent = data.intent
        }
        if (data.message && data.message.trim()) {
          const finalText = sanitizeContent(data.message)
          const _sseAlreadyProvided = (assistantMsg as any)._contentFromSSE === true
          const _hasStreamContent = (assistantMsg.content || '').length > 10
          if (_sseAlreadyProvided || _hasStreamContent) {
            console.log('[ChatAgent] chat status: SSE already provided content, skipping POST response overwrite. SSE content length=', assistantMsg.content?.length, ', POST response length=', finalText.length)
          } else if (finalText.length > 0) {
            console.log('[ChatAgent] chat status: no SSE content, using POST response. length=', finalText.length)
            assistantMsg.content = finalText
          }
          assistantMsg.agentMeta!.workflowStatus = 'completed'
          transitionTurn('done', '')
          if (sid) {
            chatSessionsApi.addMessage(sid, 'assistant', assistantMsg.content, assistantMsg.agentMeta).catch(() => {})
          }
          stream.notifyAgentLoopDone(10_000)
          return
        }
        const _sseAlreadyProvided = (assistantMsg as any)._contentFromSSE === true
        const _hasStreamContent = !!(assistantMsg as any)._streamHtml || (assistantMsg.content && assistantMsg.content.length > 10)
        console.log('[ChatAgent] chat status check:', {
          _sseAlreadyProvided,
          _hasStreamContent,
          contentLength: assistantMsg.content?.length,
          hasStreamHtml: !!(assistantMsg as any)._streamHtml,
        })
        if ((_sseAlreadyProvided || _hasStreamContent) && assistantMsg.content && assistantMsg.content.length > 5) {
          console.log('[ChatAgent] SSE/stream already provided content for chat status, skipping sendMessageReal')
          assistantMsg.agentMeta!.workflowStatus = 'completed'
          transitionTurn('done', '')
          stream.notifyAgentLoopDone(10_000)
          return
        }
        console.log('[ChatAgent] no SSE content yet, calling sendMessageReal')
        await sendMessageReal(conv, startTime, sid, assistantMsg)
        return
      }

      if (data.status === "workflow_started" || data.workflow_id) {
        const wfId = data.workflow_id || ""
        assistantMsg.agentMeta!.workflowId = wfId
        assistantMsg.agentMeta!.intent = data.intent
        if (data.plan_steps && data.plan_steps.length > 0) {
          assistantMsg.agentMeta!.steps = (data.plan_steps as string[]).map((s: string) => ({
            nodeKey: s,
            nodeLabel: AGENT_NODE_LABELS[s] || s,
            status: 'pending' as const,
            percent: 0,
          }))
          assistantMsg.agentMeta!.planSteps = data.plan_steps
        }
        if (wfId) {
          sse.activeWorkflowId.value = wfId
          sse.subscribeWorkflowSSE(wfId, assistantMsg).catch(() => {})
          setTimeout(() => {
            const chatCtrl = sse.chatSseController.value as AbortController | null
            if (chatCtrl) {
              chatCtrl.abort()
              sse.chatSseController.value = null
            }
          }, 500)
        }
        assistantMsg.content = sanitizeContent(data.message || "已启动处理，正在为您准备内容…")
        assistantMsg.agentMeta!.workflowStatus = "running"
        transitionTurn('running', '处理中…')
        return
      }

      if (data.status === "shortcut_completed") {
        let content = data.message || '已完成'
        if (data.wechat_push) {
          if (data.wechat_push === 'sent') {
            content += '\n\n[done] 已推送到微信'
          } else if (data.wechat_push.startsWith('skipped:')) {
            content += `\n\n[warn] 微信推送跳过：${data.wechat_push.slice(8)}`
          } else if (data.wechat_push.startsWith('error:')) {
            content += `\n\n[error] 微信推送失败：${data.wechat_push.slice(6)}`
          }
        }
        assistantMsg.content = sanitizeContent(content)
        assistantMsg.agentMeta!.workflowStatus = "completed"
        transitionTurn('done', '')
        assistantMsg.agentMeta!.intent = data.intent
        if (data.plan_steps && data.plan_steps.length > 0) {
          assistantMsg.agentMeta!.steps = (data.plan_steps as string[]).map((s: string) => ({
            nodeKey: s,
            nodeLabel: AGENT_NODE_LABELS[s] || s,
            status: 'completed' as const,
            percent: 100,
          }))
          assistantMsg.agentMeta!.planSteps = data.plan_steps
        }
        if (data.card_draft && data.card_draft.pages && data.card_draft.pages.length > 0) {
          try {
            const normalized = normalizeCardDraft(data.card_draft)
            const pngUrls: string[] = data.png_urls || normalized.pngUrls
            const htmlUrls: string[] = data.html_urls || normalized.htmlUrls
            normalized.pngUrls = pngUrls
            normalized.htmlUrls = htmlUrls
            const coverUrl = pickCoverUrl(normalized.pages, pngUrls)
            const images = pickImages(normalized.pages, pngUrls)
            let aw = workStore.activeWork
            if (aw && aw.isDraft) {
              workStore.updateDraft(aw.id, {
                cardDraft: normalized,
                coverUrl: coverUrl || aw.coverUrl,
                images,
              })
            } else {
              workStore.saveCardAsDraft(normalized, normalized.title, coverUrl, images)
            }
            if (assistantMsg.agentMeta) {
              assistantMsg.agentMeta.cardDraft = normalized
            }
          } catch (e) {
            console.error('[ChatAgent] draft panel update failed:', e)
          }
        }
        if (data.creative_state) {
          creativePhase.value = data.creative_state.phase || 'idle'
          if (data.creative_state._card_draft && data.creative_state._card_draft.pages && data.creative_state._card_draft.pages.length > 0) {
            try {
              const normalized = normalizeCardDraft(data.creative_state._card_draft)
              const coverUrl = pickCoverUrl(normalized.pages, normalized.pngUrls)
              const images = pickImages(normalized.pages, normalized.pngUrls)
              let aw = workStore.activeWork
              if (aw && aw.isDraft) {
                workStore.updateDraft(aw.id, {
                  cardDraft: normalized,
                  coverUrl: coverUrl || aw.coverUrl,
                  images,
                })
              } else {
                workStore.saveCardAsDraft(normalized, normalized.title, coverUrl, images)
              }
              if (assistantMsg.agentMeta) {
                assistantMsg.agentMeta.cardDraft = normalized
              }
            } catch (e) {
              console.error('[ChatAgent] SSE creative_state._card_draft panel update failed:', e)
            }
          }
        }
        if (data.created_files && Array.isArray(data.created_files)) {
          for (const cf of data.created_files) {
            fileStore.addBackendFile(cf)
          }
          await fileStore.loadFilesForSession(sid || '')
        }
        stream.notifyImmediateComplete()
        return
      }

      if (data.status === "agent_output" && data.output) {
        const output = data.output
        const _sseAlreadyUpdated = (assistantMsg as any)._contentFromSSE === true

        if (output.card_draft && output.card_draft.pages && output.card_draft.pages.length > 0) {
          try {
            const normalized = normalizeCardDraft(output.card_draft)
            const pngUrls: string[] = output.png_urls || normalized.pngUrls
            const htmlUrls: string[] = output.html_urls || normalized.htmlUrls
            normalized.pngUrls = pngUrls
            normalized.htmlUrls = htmlUrls
            const coverUrl = pickCoverUrl(normalized.pages, pngUrls)
            const images = pickImages(normalized.pages, pngUrls)
            let aw = workStore.activeWork
            if (aw && aw.isDraft) {
              workStore.updateDraft(aw.id, {
                cardDraft: normalized,
                coverUrl: coverUrl || aw.coverUrl,
                images,
              })
            } else {
              workStore.saveCardAsDraft(normalized, normalized.title, coverUrl, images)
            }
            if (assistantMsg.agentMeta) {
              assistantMsg.agentMeta.cardDraft = normalized
            }
          } catch (e) {
            console.error('[ChatAgent] draft panel update failed:', e)
          }
        }

        if (data.creative_state) {
          creativePhase.value = data.creative_state.phase || 'idle'
          if (data.creative_state._card_draft && data.creative_state._card_draft.pages && data.creative_state._card_draft.pages.length > 0) {
            try {
              const normalized = normalizeCardDraft(data.creative_state._card_draft)
              const coverUrl = pickCoverUrl(normalized.pages, normalized.pngUrls)
              const images = pickImages(normalized.pages, normalized.pngUrls)
              let aw = workStore.activeWork
              if (aw && aw.isDraft) {
                workStore.updateDraft(aw.id, {
                  cardDraft: normalized,
                  coverUrl: coverUrl || aw.coverUrl,
                  images,
                })
              } else {
                workStore.saveCardAsDraft(normalized, normalized.title, coverUrl, images)
              }
              if (assistantMsg.agentMeta) {
                assistantMsg.agentMeta.cardDraft = normalized
              }
            } catch (e) {
              console.error('[ChatAgent] creative_state._card_draft panel update failed:', e)
            }
          }
        }

        if (!_sseAlreadyUpdated) {
          const _existingContent = assistantMsg.content || ''
          if (_existingContent.length > 10) {
            console.log('[ChatAgent] agent_output: existing content from stream, skip overwrite. existing length=', _existingContent.length)
          } else if (output.results && Array.isArray(output.results)) {
            const count = output.results.length
            let content = ''
            if (output.summary && output.summary.length > 10) {
              content = output.summary
            } else if (output.patterns && output.insights) {
              content = `分析完成，共 ${count} 条结果\n\n`
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
              content = `搜索完成，找到 ${count} 条结果`
              const top5 = output.results.slice(0, 5)
              for (const r of top5) {
                content += `\n- **${r.title || '无标题'}** likes:${r.likes || 0} comments:${r.comments || 0}`
              }
              if (count > 5) content += `\n…共 ${count} 条`
            }
            assistantMsg.content = sanitizeContent(content)
          } else if (output._error) {
            assistantMsg.content = '[warn] 处理过程中遇到问题，请稍后重试'
            assistantMsg.isError = true
          } else if (output.summary && output.summary.length > 0) {
            assistantMsg.content = sanitizeContent(output.summary)
          } else {
            assistantMsg.content = sanitizeContent(formatAgentOutput(output))
          }
        } else {
          console.log('[ChatAgent] Skipping content update - SSE already provided content')
        }

        if (data.intent) {
          assistantMsg.agentMeta!.intent = data.intent
        }
        if (data.thinking) {
          if (!assistantMsg.reasoning) assistantMsg.reasoning = data.thinking
        }
        assistantMsg.agentMeta!.workflowStatus = 'completed'
        transitionTurn('done', '')

        if (data.output?.created_files && Array.isArray(data.output.created_files)) {
          for (const cf of data.output.created_files) {
            fileStore.addBackendFile(cf)
          }
          await fileStore.loadFilesForSession(sid || '')
        }

        stream.notifyAgentLoopDone(10_000)
      } else if (!assistantMsg.content) {
        assistantMsg.content = sanitizeContent(data.message || '处理完成')
        assistantMsg.agentMeta!.workflowStatus = 'completed'
        transitionTurn('done', '')
        stream.notifyAgentLoopDone(10_000)
      } else {
        stream.notifyAgentLoopDone(10_000)
      }
    } catch (err: any) {
      assistantMsg.content = "Agent 执行失败: " + (err.message || "未知错误")
      assistantMsg.isError = true
      assistantMsg.agentMeta!.workflowStatus = 'error'
      if (sid) {
        chatSessionsApi.addMessage(sid, 'assistant', assistantMsg.content, assistantMsg.agentMeta).catch(() => {})
      }
      stream.notifyImmediateComplete()
    }
  }

  return { sendAgentMessage }
}