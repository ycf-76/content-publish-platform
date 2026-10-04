import { ref, onUnmounted } from 'vue'
import type { ChatMessage, AgentMeta, TurnPhase, StatusIndicator } from '../cell-types'
import { getToolDisplayLabel, getNodeDisplayLabel, getThinkingPreview, sanitizeContent } from '../cell-types'
import { stripThinkingFromHtml, stripHiddenTags } from '../chat-content-renderer'
import { getToolIcon, getNodeIcon } from '../icon-map'
import { AGENT_NODE_LABELS } from '../agent-output-formatter'
import { renderMarkdown } from '../markdown-renderer'
import { normalizeCardDraft, pickCoverUrl, pickImages } from '@/composables/cardDraft'
import { streamTargetLag, streamMinCps, streamMaxCps, streamFrameMs } from './useStreamSpeed'

function _stripThinkBlocks(text: string): string {
  if (!text) return ''
  // 先清理 RichMediaReference（SSE 专用标签，不在通用 HIDDEN_TAGS 中）
  const cleaned = text.replace(/<RichMediaReference>[\s\S]*?superscript:/g, '')
  // 复用通用隐藏标签剥离逻辑（thinking / needs_clarification 等）
  return stripHiddenTags(cleaned)
}

export function _ingestContentDelta(msg: ChatMessage, delta: string): string {
  if (!delta) return ''
  const st = (msg as any)._thinkState || { inThink: false, base: '', buf: '', carry: '' }
  // 只识别 <thinking> 标签。
  // unicode think 标签(❨/❩)已移除——后端通过 reasoning_summary_text_delta 事件路由，
  // 前端不再需要从 agent_message_delta 的正文中用正则提取。
  const OPENS = ['<thinking>']
  const CLOSES = ['</thinking>']

  // 拼接上一块暂存的"部分标签"前缀，再统一扫描
  const text = (st.carry || '') + delta
  st.carry = ''
  let out = ''
  let i = 0
  while (i < text.length) {
    if (!st.inThink) {
      let oi = -1
      let openLen = 0
      for (const tag of OPENS) {
        const idx = text.indexOf(tag, i)
        if (idx !== -1 && (oi === -1 || idx < oi || (idx === oi && tag.length > openLen))) {
          oi = idx
          openLen = tag.length
        }
      }
      if (oi === -1) {
        // 本块无完整 OPEN： OPEN 前缀的字节暂存，等下一块
        const k = Math.max(...OPENS.map((t) => _trailingPartial(text, t)))
        out += text.slice(i, text.length - k)
        st.carry = text.slice(text.length - k)
        break
      }
      out += text.slice(i, oi)
      // 进入思考块：把此前已定稿的思考文本作为基底
      // 路由到 msg.reasoning（统一走 ReasoningSummaryCell 渲染）
      st.base = msg.reasoning || ''
      if (st.base && !st.base.endsWith('\n')) st.base += '\n'
      st.inThink = true
      st.buf = ''
      i = oi + openLen
    } else {
      let ci = -1
      let closeLen = 0
      for (const tag of CLOSES) {
        const idx = text.indexOf(tag, i)
        if (idx !== -1 && (ci === -1 || idx < ci || (idx === ci && tag.length > closeLen))) {
          ci = idx
          closeLen = tag.length
        }
      }
      if (ci === -1) {
        // 本块无完整 CLOSE： CLOSE 前缀的字节暂存，等下一块
        const k = Math.max(...CLOSES.map((t) => _trailingPartial(text.slice(i), t)))
        st.buf += text.slice(i, text.length - k)
        msg.reasoning = st.base + st.buf
        st.carry = text.slice(text.length - k)
        break
      }
      st.buf += text.slice(i, ci)
      msg.reasoning = st.base + st.buf + '\n'
      st.inThink = false
      st.buf = ''
      i = ci + closeLen
    }
  }
  ;(msg as any)._thinkState = st
  return out
}

// 返回 s 末尾与 tag 前缀匹配的最长长度（且 < tag.length，即"部分匹配"而非完整匹配）。
// 完整匹配由 indexOf 负责，这里只处理跨 chunk 截断的尾巴。
function _trailingPartial(s: string, tag: string): number {
  const maxk = Math.min(tag.length - 1, s.length)
  let best = 0
  for (let k = 1; k <= maxk; k++) {
    if (s.slice(s.length - k) === tag.slice(0, k)) best = k
  }
  return best
}

// 同一轮里首个 stream_chunk 用于替换启动占位文案，后续块才追加
const streamedPlaceholderReplaced = new WeakSet<ChatMessage>()

export interface ChatSSECallbacks {
  transitionTurn: (phase: TurnPhase, statusHeader?: string) => void
  emit: (event: 'open-image-workspace' | 'draft-panel-update', draft?: any) => void
  isCodexMode: () => boolean
  isChatMode: () => boolean
  streamingThinking: { value: boolean }
  streamingHasContent: { value: boolean }
  persistAssistantMessage?: (content: string, agentMeta: AgentMeta) => void
  onSseComplete?: () => void
  onContentReady?: () => void
  onStreamDelta?: () => void
}

export function useChatSSE(callbacks: ChatSSECallbacks) {
    const workflowSseController = ref<AbortController | null>(null)
    const workflowSseLastEventId = ref<string>('')
    const chatSseController = ref<AbortController | null>(null)
    const chatSseLastEventId = ref<string>('')
    const activeWorkflowId = ref<string | null>(null)
    const activeSessionId = ref<string | null>(null)
    // 消息代（epoch）：每次 sendAgentMessage 递增，防止旧 SSE replay 事件污染新消息
    let _chatMsgEpoch = 0
    let _chatSseReadyResolvers: Array<() => void> = []

    function _markChatSseReady() {
        const resolvers = _chatSseReadyResolvers
        _chatSseReadyResolvers = []
        for (const resolve of resolvers) resolve()
    }

    function waitForChatSseReady(): Promise<void> {
        return new Promise((resolve) => {
            _chatSseReadyResolvers.push(resolve)
        })
    }

    onUnmounted(() => {
        if (workflowSseController.value) {
            workflowSseController.value.abort()
            workflowSseController.value = null
        }
        if (chatSseController.value) {
            chatSseController.value.abort()
            chatSseController.value = null
        }
    })

    // ── 流式文本播放器：借鉴 Codex CLI v0.145 渲染管线 ──
    // 1) 事件处理只把 delta 追加到真实累积缓冲 raw，由独立 rAF 循环按帧释放到
    //    响应式 content。渲染节奏与事件到达频率解耦，杜绝 Vue 批量合并导致的「整段打印」。
    //    显示内容永远 ≤ 真实已到达内容（绝不抢跑）。
    // 2) 目标延迟模型（替代旧版 MAX_LAG=200 硬跳）：追赶速度 = 积压 / 目标延迟，
    //    显示内容恒定落后真实内容约 TARGET_LAG 秒，平滑收敛、绝不跳变。
    // 3) 增量 markdown 渲染（脏段缓存，对应 Codex segment cache + dirty-region）：
    //    稳定段（最后一个空行边界之前、且不在未闭合代码围栏内）只解析一次并缓存，
    //    每帧只重解析末尾活跃段——长回复的每帧渲染成本恒定，不再随内容变长线性恶化
    //    （旧版每帧对整段内容跑 markdown-it + v-html 全量替换，越长越卡，帧率退化后
    //    dt 变大、单帧吐更多字符，形成「卡几秒突然刷一大段」的正反馈）。
    interface StreamPlayer {
        raw: string
        shown: number
        raf: number | null
        last: number
        lastPaint: number
        // 双游标（对齐 Codex emitted_stable_len / enqueued_stable_len）
        // enqueued: 已识别为稳定但尚未渲染到 DOM 的边界
        // emitted: 已渲染到 DOM 的稳定段边界，一旦推进永不回退
        enqueuedStableLen: number
        emittedStableLen: number
        emittedStableHtml: string
        phase: 'preview' | 'settling' | 'settled'
        settledHtml: string
        // 流式输入已结束（agent_message_completed / workflow_completed 到达），
        // 播放器追完后自动落地（settled），不再需要外部 cancelStreamDelta 跳帧
        pendingSettle: boolean
        // 落地内容：若 completed 事件携带的文本比 delta 累积更长，用此值覆盖
        settleContent: string | null
    }

    const streamPlayers = new WeakMap<ChatMessage, StreamPlayer>()

    // UI 更新节流：DOM 重渲染约 60fps（SSE 事件需要低延迟透传到用户）
    // 四个参数从 useStreamSpeed 读取，用户可在设置面板实时调节
    // STREAM_FRAME_MS: 渲染节流间隔（ms）
    // STREAM_TARGET_LAG: 目标显示延迟（秒），越小越跟手
    // STREAM_MIN_CPS / STREAM_MAX_CPS: 每秒字符数上下界

    function _ensureStreamPlayer(msg: ChatMessage) {
        let p = streamPlayers.get(msg)
        if (!p) {
            p = {raw: '', shown: 0, raf: null, last: 0, lastPaint: 0, enqueuedStableLen: 0, emittedStableLen: 0, emittedStableHtml: '', phase: 'preview', settledHtml: '', pendingSettle: false, settleContent: null}
            streamPlayers.set(msg, p)
        }
        return p
    }

    function _sanitizeForStream(text: string): string {
        return callbacks.isChatMode() ? sanitizeContent(text) : text
    }

    // 入队稳定边界（对齐 Codex enqueued_stable_len）
    // 换行提交策略：遇到换行符就标记为稳定行（Codex 默认策略）
    // 但代码围栏内不提交——等围栏闭合后再整体提交
    // 这避免了长段落中内容迟迟不被提交的问题（双换行太保守）
    function _enqueueStableBoundary(p: StreamPlayer, shownText: string) {
        if (shownText.length - p.enqueuedStableLen < 20) return
        // 从当前 enqueued 位置向后扫描，找到最后一个可提交的换行
        let lastCommitableNewline = -1
        let inCodeFence = false
        const start = p.enqueuedStableLen
        for (let i = start; i < shownText.length; i++) {
            if (shownText[i] === '`' && shownText[i+1] === '`' && shownText[i+2] === '`') {
                inCodeFence = !inCodeFence
                i += 2
                continue
            }
            if (!inCodeFence && shownText[i] === '\n') {
                lastCommitableNewline = i + 1
            }
        }
        if (lastCommitableNewline > p.enqueuedStableLen) {
            p.enqueuedStableLen = lastCommitableNewline
        }
    }

    // 提交稳定段（对齐 Codex emitted_stable_len）
    // 把 enqueued 边界推进到 emitted，渲染并缓存 HTML
    // 一旦 emitted，永不回退——对应 Codex "committed to scrollback, never modified"
    function _emitStableBoundary(p: StreamPlayer, shownText: string) {
        if (p.enqueuedStableLen <= p.emittedStableLen) return
        p.emittedStableLen = p.enqueuedStableLen
        p.emittedStableHtml = renderMarkdown(_sanitizeForStream(shownText.slice(0, p.emittedStableLen)))
    }

    // 渲染当前帧：emitted 稳定段 HTML + 可变尾部增量渲染
    function _paintStreamFrame(msg: ChatMessage, p: StreamPlayer) {
        const shownText = p.raw.slice(0, Math.floor(p.shown))
        msg.content = shownText
        _enqueueStableBoundary(p, shownText)
        _emitStableBoundary(p, shownText)
        const tail = shownText.slice(p.emittedStableLen)
        const rawHtml = p.emittedStableHtml + (tail ? renderMarkdown(_sanitizeForStream(tail)) : '')
        msg._streamHtml = stripThinkingFromHtml(rawHtml)
    }

    function pushStreamDelta(msg: ChatMessage, delta: string) {
        if (!delta) return
        if (!streamedPlaceholderReplaced.has(msg)) {
            // 首个真实内容块：抛弃启动占位文案
            msg.content = ''
            streamedPlaceholderReplaced.add(msg)
        }
        const cleaned = _ingestContentDelta(msg, delta)
        const inThink = !!(msg as any)._thinkState?.inThink
        if (inThink) {
            callbacks.streamingThinking.value = true
        }
        if (!cleaned) return
        const p = _ensureStreamPlayer(msg)
        p.raw += cleaned
        ;(msg as any)._contentFromSSE = true
        callbacks.streamingHasContent.value = true
        callbacks.transitionTurn('running', '生成回复中…')
        callbacks.onStreamDelta?.()
        if (p.raf == null) {
            p.last = performance.now()
            p.lastPaint = 0
            const tick = () => {
                const cur = streamPlayers.get(msg)
                if (!cur) return
                const now = performance.now()
                const dt = Math.min((now - cur.last) / 1000, 0.25)
                cur.last = now
                const backlog = cur.raw.length - cur.shown
                if (backlog > 0) {
                    const _lag = cur.pendingSettle ? 0.05 : Math.max(0.02, streamTargetLag.value || 0.15)
                    const _minCps = Math.max(20, streamMinCps.value || 120)
                    const _maxCps = Math.max(_minCps, streamMaxCps.value || 4800)
                    const cps = Math.min(_maxCps, Math.max(_minCps, backlog / _lag))
                    cur.shown = Math.min(cur.raw.length, cur.shown + dt * cps)
                }
                const _frameMs = Math.max(8, streamFrameMs.value || 16)
                if (now - cur.lastPaint >= _frameMs || cur.shown >= cur.raw.length) {
                    cur.lastPaint = now
                    _paintStreamFrame(msg, cur)
                }
                if (cur.shown >= cur.raw.length) {
                    // 播放器追完：若 pendingSettle，自动落地
                    if (cur.pendingSettle && cur.phase !== 'settled') {
                        _doSettle(msg, cur)
                    }
                    cur.raf = null
                } else {
                    cur.raf = requestAnimationFrame(tick)
                }
            }
            p.raf = requestAnimationFrame(tick)
        }
    }

    function _doSettle(msg: ChatMessage, p: StreamPlayer) {
        if (p.phase === 'settled') return
        const finalContent = p.settleContent ?? p.raw
        msg.content = finalContent
        p.phase = 'settling'
        p.settledHtml = stripThinkingFromHtml(renderMarkdown(_sanitizeForStream(finalContent)))
        msg._streamHtml = p.settledHtml
        p.phase = 'settled'
        p.pendingSettle = false
        p.settleContent = null
    }

    function _stopPlayer(msg: ChatMessage) {
        const p = streamPlayers.get(msg)
        if (!p) return
        if (p.raf != null) {
            cancelAnimationFrame(p.raf)
            p.raf = null
        }
        p.shown = p.raw.length
        _doSettle(msg, p)
    }

    // 标记流式输入结束，让播放器加速追完后自动落地（不跳帧）
    function _markPendingSettle(msg: ChatMessage, settleContent: string | null = null) {
        const st = (msg as any)._thinkState
        if (st) {
            if (st.carry) {
                if (st.inThink) {
                    st.buf += st.carry
                    msg.reasoning = (st.base || '') + st.buf + '\n'
                } else if (st.carry.startsWith('<') && !st.carry.includes('>')) {
                    // 不完整的标签前缀（如 '<', '<t', '<thin'），直接丢弃
                } else {
                    // carry 是普通文本（如被截断的非标签内容），追加到 raw
                    const p = streamPlayers.get(msg)
                    if (p) p.raw += st.carry
                }
                st.carry = ''
            }
            if (st.inThink) {
                st.inThink = false
                st.buf = ''
            }
        }
        const p = streamPlayers.get(msg)
        if (!p) {
            // 没有 player 说明没有 delta 到达，直接设内容
            if (settleContent) {
                msg.content = settleContent
                msg._streamHtml = stripThinkingFromHtml(renderMarkdown(_sanitizeForStream(settleContent)))
            }
            return
        }
        p.pendingSettle = true
        if (settleContent && settleContent.length > p.raw.length) {
            p.settleContent = settleContent
        }
        // 如果播放器已经追完（raf == null），立即落地
        if (p.shown >= p.raw.length && p.raf == null) {
            _doSettle(msg, p)
        }
        // 否则 tick 循环会在追完后自动调用 _doSettle
    }

    function cancelStreamDelta(msg: ChatMessage) {
        _stopPlayer(msg)
    }

    function flushStreamDelta(msg: ChatMessage) {
        _stopPlayer(msg)
    }

    function _recalcPercent(meta: AgentMeta) {
        const steps = meta.steps || []
        if (steps.length === 0) {
            meta.totalPercent = 0;
            return
        }
        const done = steps.filter(s => s.status === 'completed').length
        meta.totalPercent = Math.round((done / steps.length) * 100)
    }

    async function subscribeChatSSE(
        sessionId: string,
        assistantMsg: ChatMessage,
        retryCount = 0
    ) {
        const {tryRefreshToken} = await import('@/api/client')
        if (chatSseController.value) {
            chatSseController.value.abort()
            chatSseController.value = null
        }
        const controller = new AbortController()
        chatSseController.value = controller
        // 捕获当前消息代，用于过滤旧 replay 事件
        const epoch = _chatMsgEpoch
        // 是否已收到新消息的 workflow_started 事件
        // 在此之前的所有事件都是旧消息的 replay，必须忽略
        let newWorkflowStarted = false

        const token = localStorage.getItem("token")
        const headers: Record<string, string> = {Accept: "text/event-stream"}
        if (token) headers["Authorization"] = "Bearer " + token
        if (chatSseLastEventId.value) {
            headers["Last-Event-ID"] = chatSseLastEventId.value
        }

        try {
            let response = await fetch("/api/sse/chat/" + sessionId, {
                headers,
                signal: controller.signal,
            })

            if (response.status === 401 && token) {
                const newToken = await tryRefreshToken()
                if (newToken) {
                    headers["Authorization"] = "Bearer " + newToken
                    response = await fetch("/api/sse/chat/" + sessionId, {
                        headers,
                        signal: controller.signal,
                    })
                }
            }

            if (!response.ok || !response.body) {
                console.warn(`[ChatSSE] connection failed: status=${response.status}, ok=${response.ok}`)
                _markChatSseReady()
                return
            }

            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            _markChatSseReady()
            let buffer = ""

            while (true) {
                const {done, value} = await reader.read()
                if (done) break
                buffer += decoder.decode(value, {stream: true})
                const lines = buffer.split("\n")
                buffer = lines.pop() || ""
                for (const line of lines) {
                    if (line.startsWith("id: ")) {
                        chatSseLastEventId.value = line.slice(4).trim()
                        continue
                    }
                    if (!line.startsWith("data: ")) continue
                    const jsonStr = line.slice(6)
                    if (!jsonStr.trim()) continue
                    try {
                        const parsed = JSON.parse(jsonStr)
                        const _et = parsed.type || parsed.event_type
                        // 消息代检查：如果 epoch 不匹配，说明这是旧消息的 replay 事件，忽略
                        if (epoch !== _chatMsgEpoch) {
                            continue
                        }
                        // 在收到 chat_turn_started / workflow_started 之前，忽略所有事件（防止旧消息 replay 污染新消息）
                        if (!newWorkflowStarted) {
                            if (_et === 'chat_turn_started' || _et === 'workflow_started') {
                                newWorkflowStarted = true
                            } else {
                                continue
                            }
                        }
                        handleWorkflowEvent(parsed, assistantMsg)
                    } catch {
                        // ignore
                    }
                }
            }
        } catch (err: any) {
            _markChatSseReady()
            if (err?.name === 'AbortError') return
            if (retryCount < 2) {
                const delay = 2000 * (retryCount + 1)
                console.warn(`[ChatSSE] connection lost, retrying in ${delay}ms (attempt ${retryCount + 1})`)
                await new Promise(r => setTimeout(r, delay))
                return subscribeChatSSE(sessionId, assistantMsg, retryCount + 1)
            }
        } finally {
            if (chatSseController.value === controller) {
                chatSseController.value = null
            }
            const epochStillCurrent = epoch === _chatMsgEpoch
            flushStreamDelta(assistantMsg)
            if (epochStillCurrent && callbacks.onSseComplete && !workflowSseController.value) {
                callbacks.onSseComplete()
            }
        }
    }

    async function subscribeWorkflowSSE(
        workflowId: string,
        assistantMsg: ChatMessage,
        retryCount = 0
    ) {
        const {tryRefreshToken} = await import('@/api/client')
        const controller = new AbortController()
        workflowSseController.value = controller

        const token = localStorage.getItem('token')
        const headers: Record<string, string> = {Accept: 'text/event-stream'}
        if (token) headers['Authorization'] = `Bearer ${token}`
        if (workflowSseLastEventId.value) {
            headers['Last-Event-ID'] = workflowSseLastEventId.value
        }

        try {
            let response = await fetch(`/api/sse/workflow/${workflowId}`, {
                headers,
                signal: controller.signal,
            })

            if (response.status === 401 && token) {
                const newToken = await tryRefreshToken()
                if (newToken) {
                    headers['Authorization'] = `Bearer ${newToken}`
                    response = await fetch(`/api/sse/workflow/${workflowId}`, {
                        headers,
                        signal: controller.signal,
                    })
                }
            }

            if (!response.ok || !response.body) {
                console.warn(`[WorkflowSSE] connection failed: status=${response.status}, ok=${response.ok}`)
                if (response?.status !== 403 && retryCount < 2) {
                    const delay = 2000 * (retryCount + 1)
                    console.warn(`[WorkflowSSE] HTTP ${response?.status}, retrying in ${delay}ms`)
                    await new Promise(r => setTimeout(r, delay))
                    return subscribeWorkflowSSE(workflowId, assistantMsg, retryCount + 1)
                }
                assistantMsg.agentMeta!.workflowStatus = 'error'
                _pollShortcutResult(workflowId, assistantMsg)
                return
            }

            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            let buffer = ''
            let currentEventId = ''

            while (true) {
                const {done, value} = await reader.read()
                if (done) {
                    break
                }
                buffer += decoder.decode(value, {stream: true})
                const lines = buffer.split('\n')
                buffer = lines.pop() || ''
                for (const line of lines) {
                    if (line.startsWith('id: ')) {
                        currentEventId = line.slice(4).trim()
                        workflowSseLastEventId.value = currentEventId
                        continue
                    }
                    if (!line.startsWith('data: ')) continue
                    const jsonStr = line.slice(6)
                    if (!jsonStr.trim()) continue
                    try {
                        const parsed = JSON.parse(jsonStr)
                        handleWorkflowEvent(parsed, assistantMsg)
                    } catch {
                        // 忽略心跳等非 JSON 行
                    }
                }
            }
        } catch (err: any) {
            if (err?.name === 'AbortError') return
            if (retryCount < 2) {
                const delay = 2000 * (retryCount + 1)
                console.warn(`[WorkflowSSE] connection lost, retrying in ${delay}ms (attempt ${retryCount + 1})`)
                await new Promise(r => setTimeout(r, delay))
                return subscribeWorkflowSSE(workflowId, assistantMsg, retryCount + 1)
            }
            _pollShortcutResult(workflowId, assistantMsg)
        } finally {
            if (workflowSseController.value === controller) {
                workflowSseController.value = null
            }
            flushStreamDelta(assistantMsg)
            if (callbacks.onSseComplete && !chatSseController.value) {
                callbacks.onSseComplete()
            }
        }
    }

    async function _pollShortcutResult(sessionId: string, assistantMsg: ChatMessage) {
        const {authFetch} = await import('@/api/client')
        console.warn(`[PollFallback] SSE failed, polling session ${sessionId} for result`)
        for (let attempt = 0; attempt < 30; attempt++) {
            await new Promise(r => setTimeout(r, 3000))
            try {
                const res = await authFetch(`/api/chat/sessions/${sessionId}/messages?limit=1&role=assistant`)
                if (!res.ok) continue
                const data = await res.json()
                // 后端 StandardResponse: data 直接是消息数组；消息元数据字段为 agent_meta（下划线）
                const messages = Array.isArray(data?.data) ? data.data : (data?.data?.messages || data?.messages || [])
                const last = [...messages].reverse().find((m: any) => m.role === 'assistant')
                const meta = last?.agent_meta || last?.metadata || {}
                if (last && meta.workflow_status === 'completed') {
                    assistantMsg.content = sanitizeContent(last.content || '处理完成')
                    assistantMsg.agentMeta!.workflowStatus = 'completed'
                    assistantMsg.agentMeta!.totalPercent = 100
                    if (assistantMsg.agentMeta!.steps) {
                        for (const s of assistantMsg.agentMeta!.steps) {
                            s.status = 'completed'
                            s.percent = 100
                        }
                    }
                    callbacks.transitionTurn('done', '')
                    return
                }
                if (last && meta.workflow_status === 'awaiting_clarification') {
                    assistantMsg.content = sanitizeContent(last.content || '需要确认创作偏好')
                    assistantMsg.agentMeta!.workflowStatus = 'awaiting_clarification'
                    if (meta.loop_state_path) {
                        assistantMsg.agentMeta!.loopStatePath = meta.loop_state_path
                    }
                    if (meta.clarification_prompt) {
                        assistantMsg.agentMeta!.clarificationPrompt = meta.clarification_prompt
                    }
                    if (meta.clarification_skill) {
                        assistantMsg.agentMeta!.clarificationSkill = meta.clarification_skill
                    }
                    if (meta.clarification_batches) {
                        assistantMsg.agentMeta!.clarificationBatches = meta.clarification_batches
                    }
                    callbacks.transitionTurn('running', '等待偏好确认…')
                    return
                }
                if (last && meta.workflow_status === 'awaiting_confirmation') {
                    assistantMsg.content = sanitizeContent(last.content || '需要确认操作')
                    assistantMsg.agentMeta!.workflowStatus = 'awaiting_confirmation'
                    if (meta.loop_state_path) {
                        assistantMsg.agentMeta!.loopStatePath = meta.loop_state_path
                    }
                    if (meta.confirmation_prompt) {
                        assistantMsg.agentMeta!.confirmationPrompt = meta.confirmation_prompt
                    }
                    if (meta.confirmation_skill) {
                        assistantMsg.agentMeta!.confirmationSkill = meta.confirmation_skill
                    }
                    callbacks.transitionTurn('running', '等待确认…')
                    return
                }
                if (last && meta.workflow_status === 'error') {
                    assistantMsg.content = sanitizeContent(last.content || '处理出错')
                    assistantMsg.agentMeta!.workflowStatus = 'error'
                    assistantMsg.isError = true
                    callbacks.transitionTurn('error')
                    return
                }
            } catch {
            }
        }
        assistantMsg.content = '处理超时，请刷新页面查看结果'
        assistantMsg.agentMeta!.workflowStatus = 'error'
    }

    async function handleWorkflowEvent(event: any, assistantMsg: ChatMessage) {
        const eventType = event.type || event.event_type
        const payload = event.payload || {}
        const meta = assistantMsg.agentMeta
        if (!meta) return

        switch (eventType) {
            case 'chat_turn_started': {
                // 新一轮对话开始，标记 running 状态
                meta.workflowStatus = 'running'
                meta.totalPercent = 0
                callbacks.transitionTurn('running', '思考中…')
                break
            }
            case 'workflow_started': {
                meta.workflowStatus = 'running'
                meta.totalPercent = 0
                callbacks.transitionTurn('running', '处理中…')
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
                if (status === 'running' && nodeKey) {
                    const {label} = getNodeDisplayLabel(nodeKey)
                    callbacks.transitionTurn('running', `${label}中…`)
                }
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
                const nextRunning = meta.steps?.find(s => s.status === 'running')
                if (nextRunning) {
                    const {label} = getNodeDisplayLabel(nextRunning.nodeKey)
                    callbacks.transitionTurn('running', `${label}中…`)
                } else {
                    callbacks.transitionTurn('running', '处理中…')
                }
                break
            }
            case 'workflow_completed': {
                _markPendingSettle(assistantMsg)
                meta.workflowStatus = 'completed'
                meta.totalPercent = 100
                callbacks.streamingThinking.value = false
                callbacks.transitionTurn('done', '')
                if (callbacks.onContentReady) {
                    callbacks.onContentReady()
                }
                if (callbacks.persistAssistantMessage && assistantMsg.content && !assistantMsg._persisted) {
                    assistantMsg._persisted = true
                    callbacks.persistAssistantMessage(assistantMsg.content, meta)
                }
                break
            }
            case 'workflow_error':
            case 'workflow_failed': {
                cancelStreamDelta(assistantMsg)
                meta.workflowStatus = 'error'
                assistantMsg.isError = true
                callbacks.streamingThinking.value = false
                const failMsg = payload.message || payload.error || '处理失败'
                if (!assistantMsg.content || assistantMsg.content.length < 5) {
                    assistantMsg.content = sanitizeContent(`[error] ${failMsg}`)
                }
                callbacks.transitionTurn('error')
                if (callbacks.onContentReady) {
                    callbacks.onContentReady()
                }
                if (callbacks.persistAssistantMessage && !assistantMsg._persisted) {
                    assistantMsg._persisted = true
                    callbacks.persistAssistantMessage(assistantMsg.content, meta)
                }
                break
            }
            case 'workflow_cancelled': {
                meta.workflowStatus = 'error'
                callbacks.transitionTurn('error')
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
                if (payload.images) {
                    meta.reviewImages = payload.images
                }
                if (payload.has_images && !payload.images) {
                    meta.reviewImages = []
                }
                if (payload.title || payload.content) {
                    meta.reviewContent = {
                        title: payload.title || '',
                        body: payload.content || '',
                        tags: payload.tags || [],
                    }
                }
                break
            }
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
                    tools: payload.tools,
                    topic: payload.topic,
                    params: payload.params,
                    confidence: payload.confidence,
                }
                break
            }
            case 'draft_patch': {
                const {draft_id: patchDraftId, updates} = payload
                if (updates._card_draft) {
                    try {
                        const {useWorkStore} = await import('@/stores/work')
                        const workStore = useWorkStore()
                        const cardDraft = updates._card_draft
                        const normalized = normalizeCardDraft(cardDraft)
                        const {pages: draftPages, pngUrls, htmlUrls} = normalized
                        const coverUrl = pickCoverUrl(draftPages, pngUrls)
                        const images = pickImages(draftPages, pngUrls)
                        const firstPageHtml = workStore.extractFirstPageHtml(normalized)

                        let activeWork = workStore.activeWork
                        if (activeWork && activeWork.isDraft) {
                            workStore.updateDraft(activeWork.id, {
                                cardDraft: normalized,
                                coverUrl: coverUrl || activeWork.coverUrl,
                                images,
                                firstPageHtml,
                            })
                        } else {
                            workStore.saveCardAsDraft(normalized, normalized.title, coverUrl, images)
                        }
                        if (meta) {
                            meta.cardDraft = normalized
                        }
                        callbacks.emit('draft-panel-update', {cardDraft: normalized, pngUrls, htmlUrls})
                    } catch {
                    }
                    delete updates._card_draft
                }
                if (patchDraftId && Object.keys(updates).length > 0) {
                    try {
                        const {useWorkStore} = await import('@/stores/work')
                        const workStore = useWorkStore()
                        workStore.updateDraft(patchDraftId, updates)
                    } catch {
                    }
                }
                break
            }
            case 'card_draft_ready': {
                try {
                    const {useWorkStore} = await import('@/stores/work')
                    const workStore = useWorkStore()
                    const cardDraft = payload.card_draft
                    const normalized = normalizeCardDraft(cardDraft)
                    const pngUrls: string[] = payload.png_urls?.length
                        ? payload.png_urls
                        : normalized.pngUrls
                    const htmlUrls: string[] = payload.html_urls?.length
                        ? payload.html_urls
                        : normalized.htmlUrls
                    normalized.pngUrls = pngUrls
                    normalized.htmlUrls = htmlUrls

                    const coverUrl = pickCoverUrl(normalized.pages, pngUrls)
                    const images = pickImages(normalized.pages, pngUrls)
                    const firstPageHtml = workStore.extractFirstPageHtml(normalized)

                    let activeWork = workStore.activeWork
                    if (activeWork && activeWork.isDraft) {
                        workStore.updateDraft(activeWork.id, {
                            cardDraft: normalized,
                            coverUrl: coverUrl || activeWork.coverUrl,
                            images,
                            firstPageHtml,
                        })
                    } else {
                        workStore.saveCardAsDraft(normalized, normalized.title, coverUrl, images)
                    }

                    if (meta) {
                        meta.cardDraft = normalized
                    }
                    callbacks.emit('draft-panel-update' as any, {cardDraft: normalized, pngUrls, htmlUrls})
                } catch (e) {
                    console.error('[ChatSSE] card_draft_ready handling failed:', e)
                }
                break
            }
            case 'plan_ready': {
                meta.intent = {
                    action: payload.intent,
                    params: {topic: payload.topic},
                    confidence: payload.confidence,
                }
                if (payload.tool_params && Object.keys(payload.tool_params).length > 0) {
                    meta.intent.params = {
                        ...meta.intent.params,
                        tools: payload.tool_params,
                    }
                }
                if (payload.steps && payload.steps.length > 0) {
                    meta.planSteps = payload.steps
                }
                if (payload.strategy) {
                    meta.strategy = payload.strategy
                }
                if (payload.optional_tools && payload.optional_tools.length > 0) {
                    meta.optionalTools = payload.optional_tools
                }
                if (payload.rollback && Object.keys(payload.rollback).length > 0) {
                    meta.rollback = payload.rollback
                }
                if (payload.context_used) {
                    meta.contextUsed = payload.context_used
                }
                callbacks.transitionTurn('running', '规划中…')
                break
            }
            case 'stream_chunk': {
                const rawChunk = payload.chunk || ''
                const chunkContent =
                    typeof rawChunk === 'object'
                        ? (rawChunk.content || '')
                        : rawChunk
                const appendText =
                    (typeof payload._append === 'string' && payload._append) ||
                    chunkContent
                if (!appendText) break
                pushStreamDelta(assistantMsg, appendText)
                break
            }
            case 'tool_call_start': {
                if (!assistantMsg.toolCalls) assistantMsg.toolCalls = []
                const args = payload.inputs || {}
                const toolName = payload.tool_name || ''
                console.log('[ChatSSE] tool_call_start:', toolName, 'sub_agent_id:', payload.sub_agent_id, 'node:', payload.item_id)
                let argsStr = ''
                if (Object.keys(args).length > 0) {
                    if (toolName === 'spawn_agent') {
                        const tn = args.task_name || args.name || ''
                        const td = args.task_description || ''
                        const role = args.role || ''
                        const parts: string[] = []
                        if (tn) parts.push(`任务=${tn}`)
                        if (role) parts.push(`角色=${role}`)
                        if (td) parts.push(`描述=${td.length > 120 ? td.slice(0, 120) + '…' : td}`)
                        argsStr = parts.join(', ')
                    } else if (toolName === 'wait_agent') {
                        const aid = args.agent_id || ''
                        argsStr = aid ? `等待=${aid}` : ''
                    } else {
                        argsStr = Object.entries(args).map(([k, v]) => {
                            const val = typeof v === 'string' ? (v.length > 60 ? v.slice(0, 60) + '…' : v) : JSON.stringify(v)
                            return `${k}=${val}`
                        }).join(', ')
                    }
                }
                assistantMsg.toolCalls.push({
                    id: `tc_${Date.now()}`,
                    type: 'exec',
                    name: toolName,
                    arguments: args,
                    displayArgs: argsStr,
                    iteration: payload.iteration,
                    status: 'running',
                    subAgentId: payload.sub_agent_id || '',
                })
                // 工具开始调用 → 规划阶段结束，后续 delta 直接进 msg.content
                ;(assistantMsg as any)._planningMode = false
                const {label} = getToolDisplayLabel(payload.tool_name || '')
                callbacks.transitionTurn('running', `${label}中…`)
                break
            }
            case 'tool_call_end': {
                const endToolName = payload.tool_name || ''
                const endSubId = payload.sub_agent_id || ''
                let target = assistantMsg.toolCalls?.[assistantMsg.toolCalls.length - 1]
                if (target && target.name !== endToolName) {
                  target = assistantMsg.toolCalls?.findLast(
                    tc => tc.name === endToolName && (tc.subAgentId || '') === endSubId && tc.status === 'running'
                  )
                }
                if (target) {
                    if (payload.result_data !== undefined && payload.result_data !== null) {
                        try {
                            target.result = JSON.stringify(payload.result_data, null, 2)
                        } catch {
                            target.result = payload.summary || (payload.success ? '成功' : '失败')
                        }
                    } else {
                        target.result = payload.summary || (payload.success ? '成功' : '失败')
                    }
                    target.status = payload.success ? 'done' : 'error'
                    if (payload.duration_ms) target.durationMs = payload.duration_ms
                }
                break
            }
            case 'agent_confirm_required': {
                // 高危操作确认请求（SSE 双通道兜底）：POST 响应链路曾出现挂起，
                // 确认卡片改为从 SSE 事件直接渲染——与 tool_call_start 同一条可靠通道
                const cMeta: any = assistantMsg.agentMeta || {
                    workflowId: null, steps: [], totalPercent: 0,
                    turnPhase: 'running', statusIndicator: {header: ''},
                }
                cMeta.workflowStatus = 'awaiting_confirmation'
                if (payload.loop_state_path) cMeta.loopStatePath = payload.loop_state_path
                if (payload.confirmation_prompt) cMeta.confirmationPrompt = payload.confirmation_prompt
                if (payload.confirmation_skill) cMeta.confirmationSkill = payload.confirmation_skill
                assistantMsg.agentMeta = cMeta
                if (payload.confirmation_prompt && !assistantMsg.content) {
                    assistantMsg.content = sanitizeContent(payload.confirmation_prompt)
                }
                callbacks.streamingThinking.value = false
                callbacks.transitionTurn('running', '等待确认…')
                break
            }
            case 'agent_clarification_required': {
                const clMeta: any = assistantMsg.agentMeta || {
                    workflowId: null, steps: [], totalPercent: 0,
                    turnPhase: 'running', statusIndicator: {header: ''},
                }
                clMeta.workflowStatus = 'awaiting_clarification'
                if (payload.loop_state_path) clMeta.loopStatePath = payload.loop_state_path
                if (payload.clarification_prompt) clMeta.clarificationPrompt = payload.clarification_prompt
                if (payload.clarification_skill) clMeta.clarificationSkill = payload.clarification_skill
                if (payload.clarification_batches) clMeta.clarificationBatches = payload.clarification_batches
                assistantMsg.agentMeta = clMeta
                if (payload.clarification_prompt && !assistantMsg.content) {
                    assistantMsg.content = sanitizeContent(payload.clarification_prompt)
                }
                callbacks.streamingThinking.value = false
                callbacks.transitionTurn('running', '等待偏好确认…')
                break
            }
            case 'agent_clarification_expired': {
                const expMeta: any = assistantMsg.agentMeta || {
                    workflowId: null, steps: [], totalPercent: 0,
                    turnPhase: 'running', statusIndicator: {header: ''},
                }
                expMeta.workflowStatus = 'running'
                expMeta.clarificationExpired = true
                assistantMsg.agentMeta = expMeta
                if (!assistantMsg.content) {
                    assistantMsg.content = '澄清已超时，按默认设置继续'
                }
                callbacks.streamingThinking.value = false
                callbacks.transitionTurn('running', '继续创作…')
                break
            }
            case 'agent_clarification_ack': {
                const ackMeta: any = assistantMsg.agentMeta || {
                    workflowId: null, steps: [], totalPercent: 0,
                    turnPhase: 'running', statusIndicator: {header: ''},
                }
                ackMeta.clarificationAcked = true
                if (ackMeta.workflowStatus === 'awaiting_clarification') {
                    ackMeta.workflowStatus = 'running'
                }
                assistantMsg.agentMeta = ackMeta
                break
            }
            case 'agent_clarification_hint': {
                const hintMeta: any = assistantMsg.agentMeta || {
                    workflowId: null, steps: [], totalPercent: 0,
                    turnPhase: 'running', statusIndicator: {header: ''},
                }
                hintMeta.clarificationHint = {
                    prompt: payload.clarification_prompt || '',
                    skill: payload.clarification_skill || '',
                    batches: payload.clarification_batches || [],
                    autoDefaultedFields: payload.auto_defaulted_fields || {},
                    message: payload.message || '已使用默认偏好继续创作',
                }
                assistantMsg.agentMeta = hintMeta
                if (payload.message && !assistantMsg.content) {
                    assistantMsg.content = sanitizeContent(payload.message)
                }
                break
            }
            case 'governance_budget_warning': {
                if (!meta.governance) meta.governance = {
                    budgetWarning: false,
                    budgetRemaining: null,
                    compacted: false,
                    compactCount: 0,
                    retrying: false,
                    retryCount: 0,
                    contextWindowNearLimit: false,
                    recentEvents: []
                }
                meta.governance.budgetWarning = true
                meta.governance.budgetRemaining = payload.remaining ?? null
                meta.governance.recentEvents.push({type: 'budget_warning', timestamp: Date.now(), details: payload})
                break
            }
            case 'governance_compaction': {
                if (!meta.governance) meta.governance = {
                    budgetWarning: false,
                    budgetRemaining: null,
                    compacted: false,
                    compactCount: 0,
                    retrying: false,
                    retryCount: 0,
                    contextWindowNearLimit: false,
                    recentEvents: []
                }
                meta.governance.compacted = true
                meta.governance.compactCount += 1
                meta.governance.recentEvents.push({type: 'compaction', timestamp: Date.now(), details: payload})
                break
            }
            case 'governance_retry': {
                if (!meta.governance) meta.governance = {
                    budgetWarning: false,
                    budgetRemaining: null,
                    compacted: false,
                    compactCount: 0,
                    retrying: false,
                    retryCount: 0,
                    contextWindowNearLimit: false,
                    recentEvents: []
                }
                meta.governance.retrying = payload.action === 'retry'
                meta.governance.retryCount = payload.retries ?? 0
                meta.governance.recentEvents.push({type: 'retry', timestamp: Date.now(), details: payload})
                break
            }
            case 'governance_context_window': {
                if (!meta.governance) meta.governance = {
                    budgetWarning: false,
                    budgetRemaining: null,
                    compacted: false,
                    compactCount: 0,
                    retrying: false,
                    retryCount: 0,
                    contextWindowNearLimit: false,
                    recentEvents: []
                }
                meta.governance.contextWindowNearLimit = payload.reason === 'limit_reached'
                meta.governance.recentEvents.push({type: 'context_window', timestamp: Date.now(), details: payload})
                break
            }
            case 'governance_guardian_decision': {
                if (!meta.governance) meta.governance = {
                    budgetWarning: false,
                    budgetRemaining: null,
                    compacted: false,
                    compactCount: 0,
                    retrying: false,
                    retryCount: 0,
                    contextWindowNearLimit: false,
                    recentEvents: []
                }
                meta.governance.recentEvents.push({type: 'guardian_decision', timestamp: Date.now(), details: payload})
                break
            }
            case 'collab_agent_spawned': {
                if (!meta.collab) meta.collab = {
                    agents: [],
                    activeCount: 0,
                    maxConcurrent: 3,
                    maxDepth: 3,
                    poolAvailable: 3,
                    poolActive: 0,
                    collabMode: 'explicit'
                }
                meta.collab.agents.push({
                    agentId: payload.agent_id,
                    name: payload.name || 'unnamed',
                    path: payload.path || '',
                    parentId: payload.parent_id || null,
                    depth: payload.depth ?? 1,
                    role: payload.role || null,
                    status: 'running',
                    taskDescription: payload.task_description || '',
                    forkMode: payload.fork_mode || 'clean',
                })
                meta.collab.activeCount = meta.collab.agents.filter(a => a.status === 'running' || a.status === 'pending').length
                meta.collab.poolActive = meta.collab.activeCount
                meta.collab.poolAvailable = meta.collab.maxConcurrent - meta.collab.poolActive
                break
            }
            case 'collab_agent_completed': {
                if (!meta.collab) break
                const agent = meta.collab.agents.find(a => a.agentId === payload.agent_id)
                if (agent) {
                    agent.status = payload.status || 'completed'
                    agent.error = payload.error || null
                    if (payload.task_description && !agent.taskDescription) {
                        agent.taskDescription = payload.task_description
                    }
                }
                meta.collab.activeCount = meta.collab.agents.filter(a => a.status === 'running' || a.status === 'pending').length
                meta.collab.poolActive = meta.collab.activeCount
                meta.collab.poolAvailable = meta.collab.maxConcurrent - meta.collab.poolActive
                const resultPreview = payload.result_preview || ''
                if (resultPreview) {
                    assistantMsg.content += `\n\n---\n**子智能体 ${payload.agent_id?.slice(0, 8) || ''} 完成**\n${resultPreview}`
                }
                break
            }
            case 'collab_agent_interrupted': {
                if (!meta.collab) break
                const intAgent = meta.collab.agents.find(a => a.agentId === payload.agent_id)
                if (intAgent) intAgent.status = 'interrupted'
                meta.collab.activeCount = meta.collab.agents.filter(a => a.status === 'running' || a.status === 'pending').length
                meta.collab.poolActive = meta.collab.activeCount
                meta.collab.poolAvailable = meta.collab.maxConcurrent - meta.collab.poolActive
                break
            }
            case 'collab_state_update': {
                if (!meta.collab) meta.collab = {
                    agents: [],
                    activeCount: 0,
                    maxConcurrent: 3,
                    maxDepth: 3,
                    poolAvailable: 3,
                    poolActive: 0,
                    collabMode: 'explicit'
                }
                if (payload.agents) {
                    meta.collab.agents = payload.agents
                }
                if (payload.max_concurrent) meta.collab.maxConcurrent = payload.max_concurrent
                if (payload.max_depth) meta.collab.maxDepth = payload.max_depth
                if (payload.pool_active !== undefined) meta.collab.poolActive = payload.pool_active
                if (payload.pool_available !== undefined) meta.collab.poolAvailable = payload.pool_available
                if (payload.collab_mode) meta.collab.collabMode = payload.collab_mode
                meta.collab.activeCount = meta.collab.agents.filter(a => a.status === 'running' || a.status === 'pending').length
                break
            }
            case 'agent_thinking': {
                const reasoning = payload.reasoning || ''
                if (reasoning) {
                    if (!assistantMsg.reasoning) assistantMsg.reasoning = ''
                    assistantMsg.reasoning += '\n' + reasoning
                    callbacks.streamingThinking.value = true
                    const header = reasoning.length > 40 ? reasoning.slice(0, 37) + '…' : reasoning
                    callbacks.transitionTurn('running', header)
                }
                break
            }
            case 'reasoning_summary_text_delta': {
                const delta = payload.delta || ''
                if (delta) {
                    if (!assistantMsg.reasoning) assistantMsg.reasoning = ''
                    assistantMsg.reasoning += delta
                    callbacks.streamingThinking.value = true
                    const boldMatch = assistantMsg.reasoning.match(/\*\*(.+?)\*\*/)
                    if (boldMatch) {
                        callbacks.transitionTurn('running', boldMatch[1])
                    } else {
                        callbacks.transitionTurn('running', getThinkingPreview(assistantMsg.reasoning))
                    }
                }
                break
            }
            case 'reasoning_completed': {
                callbacks.streamingThinking.value = false
                if (!assistantMsg.reasoning || assistantMsg.reasoning.trim().length === 0) {
                    assistantMsg.reasoning = '思考完成'
                }
                break
            }
            case 'agent_message_delta': {
                const delta = payload.delta || ''
                if (!delta) break
                pushStreamDelta(assistantMsg, delta)
                break
            }
            case 'agent_message_clear': {
                cancelStreamDelta(assistantMsg)
                streamPlayers.delete(assistantMsg)
                assistantMsg.content = ''
                callbacks.streamingHasContent.value = false
                break
            }
            case 'agent_message_completed': {
                const rawText = payload.text || ''
                const text = _stripThinkBlocks(rawText)
                // Codex 原则：终态事件是唯一结束信号，但内容以更完整的一方为准。
                // 使用 _markPendingSettle 让播放器加速追完后自动落地，而不是 cancelStreamDelta 跳帧
                const p = streamPlayers.get(assistantMsg)
                const accumulatedLen = p ? p.raw.length : 0
                if (text && text.length >= accumulatedLen) {
                    // completed 文本更长或相等：用它作为落地内容
                    _markPendingSettle(assistantMsg, text)
                } else if (accumulatedLen > 0) {
                    // delta 流更完整：只标记待落地，不覆盖
                    _markPendingSettle(assistantMsg)
                } else if (text) {
                    // 没有 delta，只有 completed 文本
                    _markPendingSettle(assistantMsg, text)
                }
                ;(assistantMsg as any)._contentFromSSE = true
                callbacks.streamingThinking.value = false
                callbacks.streamingHasContent.value = true
                break
            }
            case 'decision_made': {
                const decision = payload.decision || ''
                if (decision) {
                    if (!assistantMsg.decisions) assistantMsg.decisions = []
                    assistantMsg.decisions.push(decision)
                    const boldMatch = decision.match(/\*\*(.+?)\*\*/)
                    if (boldMatch) {
                        callbacks.transitionTurn('running', boldMatch[1])
                    } else {
                        const header = decision.length > 40 ? decision.slice(0, 37) + '…' : decision
                        callbacks.transitionTurn('running', header)
                    }
                }
                break
            }
            case 'progress_update': {
                const label = payload.label || ''
                if (label) {
                    if (!assistantMsg.progress) assistantMsg.progress = []
                    assistantMsg.progress.push(label)
                }
                break
            }
            case 'workflow_progress': {
                const step = payload.step || ''
                const message = payload.message || ''
                const tools = payload.tools || []
                const draftPatch = payload.draft_patch

                if (step === 'agent_error') {
                    const errMsg = payload.message || payload.error || '执行出错'
                    const hint = payload.hint || ''
                    if (!assistantMsg.errors) assistantMsg.errors = []
                    assistantMsg.errors.push(hint ? `${errMsg} (${hint})` : errMsg)
                    meta.workflowStatus = 'error'
                    assistantMsg.isError = true
                    callbacks.transitionTurn('error')
                } else if (step === 'skill_chain_start' && tools.length > 0) {
                    meta.steps = tools.map((t: string, i: number) => ({
                        nodeKey: t,
                        nodeLabel: AGENT_NODE_LABELS[t] || t,
                        status: 'pending' as const,
                        percent: 0,
                    }))
                    meta.planSteps = tools
                    if (!assistantMsg.progress) assistantMsg.progress = []
                    assistantMsg.progress.push(message || '开始处理')
                    callbacks.streamingThinking.value = true
                    callbacks.transitionTurn('running', message || '处理中…')
                } else if (step === 'skill_chain_done') {
                    meta.workflowStatus = 'completed'
                    meta.totalPercent = 100
                    if (meta.steps) {
                        for (const s of meta.steps) {
                            s.status = 'completed'
                            s.percent = 100
                        }
                    }
                    if (!assistantMsg.progress) assistantMsg.progress = []
                    assistantMsg.progress.push(message || '全部完成')
                    callbacks.streamingThinking.value = true
                    callbacks.transitionTurn('done', '')
                } else if (step && meta.steps) {
                    const stepItem = meta.steps.find((s: any) => s.nodeKey === step || s.nodeKey === step.replace('_done', ''))
                    if (stepItem) {
                        if (step.endsWith('_done')) {
                            stepItem.status = 'completed'
                            stepItem.percent = 100
                        } else {
                            stepItem.status = 'running'
                            stepItem.percent = 50
                        }
                    }
                    _recalcPercent(meta)
                    if (step.endsWith('_error')) {
                        if (!assistantMsg.errors) assistantMsg.errors = []
                        assistantMsg.errors.push(message)
                    } else {
                        if (!assistantMsg.progress) assistantMsg.progress = []
                        assistantMsg.progress.push(message)
                    }
                    callbacks.streamingThinking.value = true
                    const {label} = getNodeDisplayLabel(step.replace('_done', ''))
                    callbacks.transitionTurn('running', message || `${label}中…`)
                } else if (step && !step.startsWith('video_') && step !== 'agent_error') {
                    if (step.endsWith('_error')) {
                        if (!assistantMsg.errors) assistantMsg.errors = []
                        assistantMsg.errors.push(message)
                    } else {
                        if (!assistantMsg.progress) assistantMsg.progress = []
                        assistantMsg.progress.push(message)
                    }
                    callbacks.streamingThinking.value = true
                    callbacks.transitionTurn('running', message || '处理中…')
                }

                if (draftPatch) {
                    try {
                        const {useWorkStore} = await import('@/stores/work')
                        const workStore = useWorkStore()
                        const currentWorkId = workStore.activeWorkId
                        if (currentWorkId) {
                            const idx = workStore.works.findIndex(w => w.id === currentWorkId)
                            if (idx !== -1) {
                                Object.assign(workStore.works[idx], draftPatch)
                            }
                        }
                    } catch {
                    }
                }
                break
            }
            case 'agent_error': {
                const errMsg = payload.error || payload.message || '执行出错'
                const hint = payload.hint || ''
                const isUnrecoverable = payload.unrecoverable === true
                if (!assistantMsg.errors) assistantMsg.errors = []
                assistantMsg.errors.push(hint ? `${errMsg} (${hint})` : errMsg)
                if (isUnrecoverable) {
                    assistantMsg.errors.push('LLM 熔断器已开启，后续调用已自动拦截。充值后请点击"重试"或刷新页面。')
                }
                meta.workflowStatus = 'error'
                assistantMsg.isError = true
                callbacks.transitionTurn('error')
                break
            }
            case 'shortcut_completed': {
                cancelStreamDelta(assistantMsg)
                let content = payload.message || '已完成'
                if (payload.wechat_push) {
                    if (payload.wechat_push === 'sent') {
                        content += '\n\n[done] 已推送到微信'
                    } else if (payload.wechat_push.startsWith('skipped:')) {
                        content += `\n\n[warn] 微信推送跳过：${payload.wechat_push.slice(8)}`
                    } else if (payload.wechat_push.startsWith('error:')) {
                        content += `\n\n[error] 微信推送失败：${payload.wechat_push.slice(6)}`
                    }
                }
                meta.workflowStatus = 'completed'
                meta.totalPercent = 100
                if (meta.steps) {
                    for (const s of meta.steps) {
                        s.status = 'completed'
                        s.percent = 100
                    }
                }
                callbacks.transitionTurn('done', '')
                // 同 agent_message_completed：终态文本比 delta 累积更短时，保留更完整的 delta 累积结果
                const _p = streamPlayers.get(assistantMsg)
                const _accumulated = _p ? _p.raw : ''
                const _finalText = sanitizeContent(_stripThinkBlocks(content))
                if (_finalText.length >= _accumulated.length || !_accumulated) {
                    assistantMsg.content = _finalText
                }
                ;(assistantMsg as any)._contentFromSSE = true
                if (callbacks.onContentReady) {
                    callbacks.onContentReady()
                }
                if (payload.card_draft && payload.card_draft.pages && payload.card_draft.pages.length > 0) {
                    try {
                        const {useWorkStore} = await import('@/stores/work')
                        const workStore = useWorkStore()
                        const cardDraft = payload.card_draft
                        const pngUrls: string[] = payload.png_urls || cardDraft?.pngUrls || []
                        const htmlUrls: string[] = payload.html_urls || cardDraft?.htmlUrls || []
                        const normalized = normalizeCardDraft(cardDraft)
                        normalized.pngUrls = pngUrls
                        normalized.htmlUrls = htmlUrls
                        const coverUrl = pickCoverUrl(normalized.pages, pngUrls)
                        const images = pickImages(normalized.pages, pngUrls)
                        const firstPageHtml = workStore.extractFirstPageHtml(normalized)

                        let activeWork = workStore.activeWork
                        if (activeWork && activeWork.isDraft) {
                            workStore.updateDraft(activeWork.id, {
                                cardDraft: normalized,
                                coverUrl: coverUrl || activeWork.coverUrl,
                                images,
                                firstPageHtml,
                            })
                        } else {
                            workStore.saveCardAsDraft(normalized, normalized.title, coverUrl, images)
                        }
                        if (meta) {
                            meta.cardDraft = normalized
                        }
                        callbacks.emit('draft-panel-update' as any, {cardDraft: normalized, pngUrls, htmlUrls})
                    } catch (e) {
                        console.error('[ChatSSE] shortcut_completed card_draft handling failed:', e)
                    }
                }
                break
            }
        }
    }

    return {
        workflowSseController,
        workflowSseLastEventId,
        chatSseController,
        activeWorkflowId,
        activeSessionId,
        subscribeChatSSE,
        subscribeWorkflowSSE,
        handleWorkflowEvent,
        waitForChatSseReady,
        flushStreamDelta,
        // 递增消息代，在新消息发送前调用，防止旧 SSE replay 事件污染新消息
        advanceMsgEpoch: () => { _chatMsgEpoch++ },
    }
}