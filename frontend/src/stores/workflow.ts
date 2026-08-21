import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { workflowApi, type WorkflowResponse, type WorkflowListItem, type NodeSnapshot, type ModelSettings, type WorkflowResumeRequest } from '@/api/workflow'
import { authApi } from '@/api/auth'

/** SSE 事件日志条目（供 AgentFlow 日志面板显示） */
export interface EventLog {
  event_id: string
  event_type: string
  timestamp: string
  message: string
  level: 'info' | 'success' | 'warning' | 'error'
}

/** 全局通知（欠费/配置错误/限流等，需要用户感知） */
export interface WorkflowNotification {
  id: string
  type: 'arrearage' | 'config_error' | 'rate_limited' | 'workflow_error' | 'workflow_failed' | 'search_degraded'
  message: string
  action_url?: string
  action_text?: string
  suggestion?: string
  timestamp: number
}

export const useWorkflowStore = defineStore('workflow', () => {
  const currentWorkflow = ref<WorkflowResponse | null>(null)
  const nodes = ref<NodeSnapshot[]>([])
  const eventLogs = ref<EventLog[]>([])
  const eventSource = ref<{ close: () => void } | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const isStreaming = ref(false)
  const sseSessionReady = ref(false)
  /** 通知列表（欠费/错误等，前端横幅展示） */
  const notifications = ref<WorkflowNotification[]>([])
  /** 工作流历史列表 */
  const workflowList = ref<WorkflowListItem[]>([])
  const workflowListTotal = ref(0)
  const workflowListLoading = ref(false)

  const pendingReviews = computed(() => nodes.value.filter(n => n.status === 'awaiting_review').length)
  const runningNodes = computed(() => nodes.value.filter(n => n.status === 'running').length)
  const completedNodes = computed(() => nodes.value.filter(n => n.status === 'completed' || n.status === 'passed').length)
  const progress = computed(() => {
    if (nodes.value.length === 0) return 0
    return Math.round((completedNodes.value / nodes.value.length) * 100)
  })

  /** 确保 SSE cookie session 已建立 */
  async function ensureSseSession() {
    if (sseSessionReady.value) return
    try {
      await authApi.createSseSession()
      sseSessionReady.value = true
    } catch (e) {
      console.error('Failed to create SSE session:', e)
      // 不抛错，SSE 连接失败时会有更明确的报错
    }
  }

  /** 添加通知（欠费/错误等） */
  function pushNotification(n: Omit<WorkflowNotification, 'id' | 'timestamp'>) {
    const notification: WorkflowNotification = {
      ...n,
      id: `${n.type}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      timestamp: Date.now(),
    }
    notifications.value.push(notification)
  }

  /** 移除通知 */
  function dismissNotification(id: string) {
    notifications.value = notifications.value.filter(n => n.id !== id)
  }

  /** 清空所有通知 */
  function clearNotifications() {
    notifications.value = []
  }

  /** 启动工作流并订阅 SSE */
  async function startWorkflow(
    topic: string,
    accountId: string,
    modelSettings?: ModelSettings,
    reference?: Record<string, any>,
    creativeBrief?: string,
  ) {
    if (isStreaming.value || isLoading.value) {
      if (isStreaming.value && !isLoading.value) {
        const wfId = currentWorkflow.value?.workflow_id
        if (wfId) {
          try {
            const resp: any = await workflowApi.getDetail(wfId)
            const wfData = resp?.data ?? resp
            const status = wfData?.status
            if (['completed', 'error', 'terminated', 'cancelled', 'failed'].includes(status)) {
              unsubscribeFromWorkflow()
              if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
              if (publishCheckTimer) { clearInterval(publishCheckTimer); publishCheckTimer = null }
              localStorage.removeItem('mint_active_workflow_id')
              isStreaming.value = false
            } else {
              pushNotification({
                type: 'workflow_error',
                message: '工作流正在执行中，请等待当前工作流完成后再启动新的',
              })
              return null
            }
          } catch {
            pushNotification({
              type: 'workflow_error',
              message: '工作流正在执行中，请等待当前工作流完成后再启动新的',
            })
            return null
          }
        } else {
          pushNotification({
            type: 'workflow_error',
            message: '工作流正在执行中，请等待当前工作流完成后再启动新的',
          })
          return null
        }
      } else {
        pushNotification({
          type: 'workflow_error',
          message: '工作流正在执行中，请等待当前工作流完成后再启动新的',
        })
        return null
      }
    }

    try {
      isLoading.value = true
      error.value = null
      nodes.value = []
      eventLogs.value = []
      // 启动新工作流前清空旧通知（保留 arrearage 类型的，因为欠费状态不会自动恢复）
      notifications.value = notifications.value.filter(n => n.type === 'arrearage' || n.type === 'config_error')

      // 先确保 SSE session cookie
      await ensureSseSession()

      // axios 响应拦截器已 return response.data（HTTP body），
      // 后端用 StandardResponse 包装：{success, data, message}，需提取 .data
      // modelSettings 来自右侧工作区用户选择的模型/温度/风格配置
      const resp: any = await workflowApi.start({
        topic,
        search_keyword: topic,
        creative_brief: creativeBrief || '',
        account_id: accountId,
        model_settings: modelSettings,
        reference,
      })
      const wfData = resp?.data ?? resp
      currentWorkflow.value = wfData as WorkflowResponse

      if (currentWorkflow.value?.workflow_id) {
        // 保存工作流 ID 到 localStorage，供页面刷新后恢复
        localStorage.setItem('mint_active_workflow_id', currentWorkflow.value.workflow_id)
        subscribeToWorkflow(currentWorkflow.value.workflow_id)
        // 轮询兜底：SSE 在浏览器中可能被 abort（ERR_ABORTED），
        // 启动 HTTP 轮询确保节点事件一定能被处理。
        startPollingFallback(currentWorkflow.value.workflow_id)
      }

      return wfData
    } catch (e: any) {
      error.value = e.response?.data?.message || '启动工作流失败'
      throw e
    } finally {
      isLoading.value = false
    }
  }

  /** 获取工作流详情 */
  async function fetchWorkflowDetail(workflowId: string) {
    try {
      const resp: any = await workflowApi.getDetail(workflowId)
      const wfData = resp?.data ?? resp
      currentWorkflow.value = wfData as WorkflowResponse
      return wfData
    } catch (e: any) {
      error.value = e.response?.data?.message || '获取工作流状态失败'
      throw e
    }
  }

  /** 暂停工作流 */
  async function pauseWorkflow(reason?: string) {
    if (!currentWorkflow.value) return
    try {
      await workflowApi.pause(currentWorkflow.value.workflow_id, reason)
    } catch (e: any) {
      error.value = e.response?.data?.message || '暂停失败'
      throw e
    }
  }

  /** 恢复工作流 */
  async function resumeWorkflow(payload?: WorkflowResumeRequest) {
    if (!currentWorkflow.value) return
    try {
      await workflowApi.resume(currentWorkflow.value.workflow_id, payload)
    } catch (e: any) {
      error.value = e.response?.data?.message || '恢复失败'
      throw e
    }
  }

  /** 终止工作流 */

  /** 用户主动取消工作流（刷新/重新搜索等场景，区别于 terminate） */
  async function cancelWorkflow() {
    if (!currentWorkflow.value) return
    try {
      await workflowApi.cancel(currentWorkflow.value.workflow_id)
    } catch (e: any) {
      error.value = e.response?.data?.message || '取消工作流失败'
    }
    // 无论 API 是否成功，都清理本地状态
    unsubscribeFromWorkflow()
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (publishCheckTimer) {
      clearInterval(publishCheckTimer)
      publishCheckTimer = null
    }
    localStorage.removeItem('mint_active_workflow_id')
    isStreaming.value = false
  }
  async function terminateWorkflow() {
    if (!currentWorkflow.value) return
    try {
      await workflowApi.terminate(currentWorkflow.value.workflow_id)
      unsubscribeFromWorkflow()
    } catch (e: any) {
      error.value = e.response?.data?.message || '终止失败'
      throw e
    }
  }

  /** 回滚到指定节点 */
  async function rollbackWorkflow(targetNode: string) {
    if (!currentWorkflow.value) return
    try {
      await workflowApi.rollback(currentWorkflow.value.workflow_id, targetNode)
    } catch (e: any) {
      error.value = e.response?.data?.message || '回滚失败'
      throw e
    }
  }

  /** 提交审核 */
  async function submitReview(
    reviewId: string,
    action: 'pass' | 'reject' | 'regenerate',
    selectedCandidate?: string,
  ) {
    if (!currentWorkflow.value) {
      return
    }
    try {
      const resp: any = await workflowApi.submitReview(
        currentWorkflow.value.workflow_id,
        reviewId,
        action,
        selectedCandidate,
      )
      // 检查后端返回的业务 success 字段（HTTP 200 不代表业务成功）
      // 后端响应格式：{success: true, data: {success: false, message: "..."}}
      // 后端重启后 MemorySaver 丢失，submit_review 返回 data.success=false
      const bizSuccess = resp?.data?.success
      if (bizSuccess === false) {
        const msg = resp?.data?.message || resp?.message || '审核提交失败（工作流状态可能已失效，请发起新工作流）'
        error.value = msg
        throw new Error(msg)
      }
      // 更新本地节点状态
      const node = nodes.value.find(n => n.node_id === reviewId)
      if (node) {
        node.status = action === 'pass' ? 'passed' : 'rejected'
      }
      // reject 后立即把回退目标节点设为 idle，让前端显示编辑器
      if (action === 'reject') {
        // image_review reject → image_gen 重做图片
        const rollbackTarget = reviewId === 'image_review' ? 'image_gen' : null
        if (rollbackTarget) {
          const target = nodes.value.find(n => n.node_id === rollbackTarget)
          if (target) {
            target.status = 'idle'
            target.output = { _rollback: true }
          }
        }
      }
    } catch (e: any) {
      error.value = e.response?.data?.message || '提交审核失败'
      throw e
    }
  }

  /** 更新节点输出（人工编辑，如 copywrite 的 title/content/tags） */
  async function updateNodeOutput(nodeId: string, output: Record<string, any>) {
    if (!currentWorkflow.value) return
    try {
      const resp: any = await workflowApi.updateNodeOutput(
        currentWorkflow.value.workflow_id,
        nodeId,
        output,
      )
      // 本地立即覆盖 node.output，前端展示即时刷新
      const node = nodes.value.find(n => n.node_id === nodeId)
      if (node) {
        const merged = { ...(node.output || {}), ...output, _edited: true }
        node.output = merged
      }
      return (resp?.data ?? resp)?.output
    } catch (e: any) {
      error.value = e.response?.data?.message || '更新节点输出失败'
      throw e
    }
  }
  /** 轮询兜底定时器（SSE 不可靠时确保节点事件被处理） */
  let pollTimer: ReturnType<typeof setInterval> | null = null
  /** 半自动发布结果回查轮询定时器 */
  let publishCheckTimer: ReturnType<typeof setInterval> | null = null

  /** 启动 HTTP 轮询兜底：SSE 在浏览器中可能被 abort，轮询保证结果一定能拿到 */
  function startPollingFallback(workflowId: string) {
    if (pollTimer) clearInterval(pollTimer)
    let stopped = false
    const stop = () => {
      if (stopped) return
      stopped = true
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }

    pollTimer = setInterval(async () => {
      try {
        const resp: any = await workflowApi.getNodes(workflowId)
        const data = resp?.data ?? resp
        if (!data) return

        // 用轮询结果强制刷新 store 中所有节点状态。
        // 不做 skip 优化：SSE abort 后 watch 可能没触发 completeSearch，
        // 轮询必须强制更新 nodes.value 才能让组件 watch 重新触发。
        const polledNodes: any[] = data.nodes || []
        for (const pn of polledNodes) {
          const nodeId = pn.node_id
          if (!nodeId) continue
          const idx = nodes.value.findIndex(n => n.node_id === nodeId)
          if (idx === -1) {
            nodes.value.push({ node_id: nodeId, ...pn })
          } else {
            const existing = nodes.value[idx]
            // 回退保护：只拦截 completed（第一次运行的残留状态），
            // running/idle/pending 等是合法的重新执行信号
            const isRollback = existing.output?._rollback === true
            const isStaleCompleted = isRollback && pn.status === 'completed'
            if (isStaleCompleted) {
              // 只更新非 status 字段，保留回退后的 idle 状态
              const { status: _polledStatus, ...rest } = pn
              nodes.value[idx] = { ...existing, ...rest }
            } else if (isRollback && pn.status && pn.status !== 'idle') {
              // 合法状态转换：清除 _rollback 标记，允许正常更新
              const updatedOutput = { ...(existing.output || {}) }
              delete updatedOutput._rollback
              nodes.value[idx] = { ...existing, ...pn, output: updatedOutput }
            } else {
              // 正常更新：强制替换引用，确保 Vue watch deep 能检测到变化
              nodes.value[idx] = { ...existing, ...pn }
            }
          }
        }

        // 工作流终态：停止轮询
        // getNodes 响应不含 workflow status，需要单独查询 workflow 状态
        const wfResp: any = await workflowApi.getDetail(workflowId)
        const wfData = wfResp?.data ?? wfResp
        const wfStatus = wfData?.status
        if (['completed', 'error', 'suspended', 'terminated', 'cancelled', 'failed'].includes(wfStatus)) {
          if (currentWorkflow.value) {
            currentWorkflow.value = { ...currentWorkflow.value, status: wfStatus } as WorkflowResponse
          }
          isStreaming.value = false
          stop()
        }
      } catch (e) {
        // 轮询失败静默，下一轮重试
      }
    }, 1500)
  }

  /**
   * 半自动发布结果回查轮询。
   *
   * 后端 worker 填好标题/正文/图片后不点击「发布」按钮（死壳 DOM 无法点击），
   * 由用户在弹出的浏览器窗口手动点。前端收到 awaiting_manual_publish 事件后
   * 启动此轮询，每 3s 调 /publish/check 判断是否已跳转。
   *
   * 终态（published/failed/session_invalid）时停止轮询。
   * 后端 check 接口在 published/failed 时会推 node_completed SSE，
   * 所以前端只需停轮询，节点状态由 SSE 自然更新。
   */
  function startPublishCheckPolling() {
    if (publishCheckTimer) clearInterval(publishCheckTimer)
    const workflowId = currentWorkflow.value?.workflow_id
    if (!workflowId) return

    let stopped = false
    const stop = () => {
      if (stopped) return
      stopped = true
      if (publishCheckTimer) {
        clearInterval(publishCheckTimer)
        publishCheckTimer = null
      }
    }

    publishCheckTimer = setInterval(async () => {
      try {
        const resp: any = await workflowApi.checkPublishResult(workflowId)
        const data = resp?.data ?? resp
        const status = data?.status
        // 终态：停止轮询（SSE 会推 node_completed 更新节点状态）
        if (status === 'published' || status === 'failed' || status === 'session_invalid' || status === 'not_applicable') {
          stop()
        }
      } catch (e) {
        // 轮询失败静默，下一轮重试
      }
    }, 3000)
  }

  function subscribeToWorkflow(workflowId: string) {
    if (eventSource.value) {
      eventSource.value.close()
    }
    isStreaming.value = true

    eventSource.value = workflowApi.subscribe(
      workflowId,
      (eventType, payload, eventId) => {
        handleWorkflowEvent(eventType, payload, eventId)
      },
      (err) => {
        isStreaming.value = false
      },
    )
  }

  /** 处理 SSE 事件 */
  function handleWorkflowEvent(eventType: string, payload: any, eventId: string) {
    // 记录日志
    addLog(eventType, payload, eventId)

    switch (eventType) {
      case 'workflow_started':
        if (currentWorkflow.value) {
          currentWorkflow.value = { ...currentWorkflow.value, ...payload, status: 'running' } as WorkflowResponse
        } else {
          currentWorkflow.value = payload as WorkflowResponse
        }
        break

      case 'workflow_snapshot':
        // 完整快照更新
        if (payload.nodes) {
          // 回退保护：如果本地有 _rollback 标记的节点，保留其 idle 状态
          // 避免后端快照用旧的 completed 状态覆盖回退后的编辑器状态
          const rollbackNodes = nodes.value.filter(n => n.output?._rollback === true)
          if (rollbackNodes.length > 0) {
            const newNodes = [...payload.nodes]
            for (const rn of rollbackNodes) {
              const idx = newNodes.findIndex(n => n.node_id === rn.node_id)
              if (idx !== -1) {
                // 保留回退节点的 status 和 _rollback 标记
                newNodes[idx] = { ...newNodes[idx], status: rn.status, output: rn.output }
              }
            }
            nodes.value = newNodes
          } else {
            nodes.value = payload.nodes
          }
        }
        // 处理增量 node_statuses（后端 astream chunk 发送的增量节点状态）
        // inject resume 后 image_gen/image_review 等节点状态通过此字段推送
        if (payload.node_statuses) {
          for (const [nid, status] of Object.entries(payload.node_statuses)) {
            const idx = nodes.value.findIndex(n => n.node_id === nid)
            if (idx !== -1) {
              const existing = nodes.value[idx]
              const isRollback = existing.output?._rollback === true
              const isStaleCompleted = isRollback && status === 'completed'
              if (isStaleCompleted) {
                // skip stale completed for rollback node
              } else if (isRollback && status && status !== 'idle') {
                // 合法状态转换：清除 _rollback 标记
                const updatedOutput = { ...(existing.output || {}) }
                delete updatedOutput._rollback
                nodes.value[idx] = { ...existing, status: status as NodeSnapshot['status'], output: updatedOutput }
              } else {
                nodes.value[idx] = { ...existing, status: status as NodeSnapshot['status'] }
              }
            } else {
              nodes.value.push({ node_id: nid, node_type: nid, status: status as NodeSnapshot['status'] } as NodeSnapshot)
            }
          }
        }
        if (payload.status && currentWorkflow.value) {
          currentWorkflow.value = { ...currentWorkflow.value, ...payload } as WorkflowResponse
        }
        break

      case 'workflow_completed':
        if (currentWorkflow.value) {
          currentWorkflow.value = { ...currentWorkflow.value, status: 'completed' }
        }
        isStreaming.value = false
        localStorage.removeItem('mint_active_workflow_id')
        // 后端会在发送终态事件后主动关闭 SSE 流（sse_bus.subscribe 的 return）
        // 前端 fetch 的 reader.read() 会收到 done=true 自然退出，无需主动 abort
        // 这里只清理引用，不调用 unsubscribeFromWorkflow() 的 abort 逻辑
        break

      case 'workflow_failed':
        // 关键节点失败导致工作流终止（search 空结果 / image_gen 欠费等）
        if (currentWorkflow.value) {
          currentWorkflow.value = { ...currentWorkflow.value, status: 'failed' }
        }
        isStreaming.value = false
        localStorage.removeItem('mint_active_workflow_id')
        pushNotification({
          type: 'workflow_failed',
          message: payload.message || '工作流因节点失败终止',
          suggestion: payload.suggestion,
        })
        break

      case 'workflow_error':
        if (currentWorkflow.value) {
          currentWorkflow.value = { ...currentWorkflow.value, status: 'error' }
        }
        isStreaming.value = false
        localStorage.removeItem('mint_active_workflow_id')
        pushNotification({
          type: 'workflow_error',
          message: payload.message || '工作流执行错误',
          suggestion: payload.suggestion,
        })
        break

      case 'model_arrearage':
        // 通义万相欠费：弹横幅通知用户充值
        pushNotification({
          type: 'arrearage',
          message: payload.message || '图片生成账号欠费',
          action_url: payload.action_url,
          action_text: payload.action_text,
        })
        break

      case 'model_config_error':
        // API Key 配置错误
        pushNotification({
          type: 'config_error',
          message: payload.message || '模型配置错误',
          action_url: payload.action_url,
          action_text: payload.action_text,
        })
        break

      case 'model_rate_limited':
        // 限流通知
        pushNotification({
          type: 'rate_limited',
          message: payload.message || '模型限流，请稍后重试',
        })
        break

      case 'workflow_cancelled':
        if (currentWorkflow.value) {
          currentWorkflow.value = { ...currentWorkflow.value, status: 'cancelled' }
        }
        isStreaming.value = false
        localStorage.removeItem('mint_active_workflow_id')
        break

      case 'workflow_suspended':
        if (currentWorkflow.value) {
          currentWorkflow.value = { ...currentWorkflow.value, status: 'suspended' }
        }
        break

      case 'node_started':
      case 'node_status_changed': {
        // 更新单个节点状态
        const nodeId = payload.node_id || payload.id
        const newStatus = payload.status || payload.node_status
        const idx = nodes.value.findIndex(n => n.node_id === nodeId)
        if (idx !== -1) {
          const existing = nodes.value[idx]
          // 回退保护：如果节点因 reject 被设为 idle（_rollback 标记），
          // 且新状态是 completed（来自第一次运行的残留），不覆盖。
          // running/idle/pending 等状态是合法的重新执行信号，允许通过并清除 _rollback。
          const isRollback = existing.output?._rollback === true
          const isStaleCompleted = isRollback && newStatus === 'completed'
          if (isStaleCompleted) {
            const { status: _s, node_status: _ns, ...rest } = payload
            nodes.value[idx] = { ...existing, ...rest }
          } else {
            // 合法状态转换：清除 _rollback 标记，允许正常更新
            if (isRollback && newStatus && newStatus !== 'idle') {
              const updatedOutput = { ...(existing.output || {}) }
              delete updatedOutput._rollback
              nodes.value[idx] = { ...existing, ...payload, output: updatedOutput }
            } else {
              // 节点重新 running 时清空上一轮流式文本（打字机从头开始）
              const resetStream = newStatus === 'running' && existing.agent_thinking
                ? { agent_thinking: '' }
                : {}
              nodes.value[idx] = { ...existing, ...payload, ...resetStream }
            }
          }
        } else {
          // 新节点，追加
          nodes.value.push(payload)
        }
        break
      }

      case 'node_completed': {
        const nodeId = payload.node_id || payload.id
        const idx = nodes.value.findIndex(n => n.node_id === nodeId)
        if (idx !== -1) {
          nodes.value[idx] = { ...nodes.value[idx], ...payload, status: 'completed' }
        } else {
          nodes.value.push({ node_id: nodeId, status: 'completed', ...payload })
        }
        break
      }

      case 'node_error': {
        const nodeId = payload.node_id || payload.id
        const idx = nodes.value.findIndex(n => n.node_id === nodeId)
        if (idx !== -1) {
          nodes.value[idx] = { ...nodes.value[idx], ...payload, status: 'error' }
        } else {
          nodes.value.push({ node_id: nodeId, status: 'error', ...payload })
        }
        break
      }

      case 'progress_update':
        if (currentWorkflow.value && payload.progress !== undefined) {
          currentWorkflow.value = { ...currentWorkflow.value, current_node: payload.current_node || currentWorkflow.value.current_node }
        }
        // 半自动发布：worker 填好内容等用户手动点「发布」
        // 把 output 挂到 publish 节点（保持 running），并启动 check 轮询
        if (payload.step === 'awaiting_manual_publish') {
          const idx = nodes.value.findIndex(n => n.node_id === 'publish' || n.node_type === 'publish')
          if (idx !== -1) {
            nodes.value[idx] = {
              ...nodes.value[idx],
              status: 'running',
              output: { status: 'awaiting_manual', message: payload.message || '', post_id: '' },
            }
          }
          startPublishCheckPolling()
        }
        break

      case 'stream_chunk':
        if (payload.node_id) {
          const idx = nodes.value.findIndex(n => n.node_id === payload.node_id)
          if (idx !== -1) {
            const existing = nodes.value[idx].agent_thinking || ''
            const chunk = payload.chunk
            // 优先追加式（analyze Layer2/3 的可读文本行，append-only）
            const appendText = (payload as any)._append || ''
            if (appendText) {
              nodes.value[idx].agent_thinking = existing + appendText
            } else {
              const displayText = (payload as any)._display || ''
              if (displayText) {
                nodes.value[idx].agent_thinking = displayText
              } else {
                const text = typeof chunk === 'string'
                  ? chunk
                  : chunk?.reasoning_content || chunk?.content || payload.text || ''
                if (text) nodes.value[idx].agent_thinking = existing + text
              }
            }
          }
        }
        break

      case 'review_required':
        // 创作点 interrupt：copywrite 前（方向选择）、image_gen 前（卡片编辑器）、
        // image_review 前（图片审核）、final_review 前（手机预览终审）、publish 前（安全门）
        {
          const reviewNode = payload.review_node || payload.node_id
          const reviewType = payload.review_type || ''
          if (reviewNode) {
            const idx = nodes.value.findIndex(
              n => n.node_id === reviewNode || n.node_type === reviewNode
            )
            if (idx !== -1) {
              nodes.value[idx].status = 'awaiting_review'
              if (!nodes.value[idx].output) {
                nodes.value[idx].output = {}
              }
              Object.assign(nodes.value[idx].output, payload)
              // 保存 review_type 供前端区分交互模式
              nodes.value[idx].output.review_type = reviewType
            } else {
              nodes.value.push({
                node_id: reviewNode,
                node_type: reviewNode,
                status: 'awaiting_review',
                output: { ...payload, review_type: reviewType },
              })
            }
          }
        }
        break

      case 'review_processed': {
        // 审核结果已提交
        const action = payload.action as string
        if (action === 'reject') {
          const reviewNode = nodes.value.find(n => n.status === 'awaiting_review')
          const reviewId = reviewNode?.node_id || reviewNode?.node_type
          // image_review reject → image_gen 重做图片
          const rollbackTarget = reviewId === 'image_review' ? 'image_gen' : null
          if (rollbackTarget) {
            const target = nodes.value.find(n => n.node_id === rollbackTarget)
            if (target) {
              target.status = 'idle'
              target.output = { _rollback: true }
            }
          }
          if (reviewNode) {
            reviewNode.status = 'rejected'
          }
        }
        break
      }

      case 'quality_check_result':
      case 'tool_call_start':
      case 'tool_call_end':
        break

      case 'agent_thinking':
        if (payload.node_id) {
          const idx = nodes.value.findIndex(n => n.node_id === payload.node_id)
          if (idx !== -1) {
            const existing = nodes.value[idx].agent_thinking || ''
            const chunk = payload.chunk
            const text = typeof chunk === 'string'
              ? chunk
              : chunk?.reasoning_content || chunk?.content || ''
            if (text) nodes.value[idx].agent_thinking = existing + text
          }
        }
        break

      case 'decision_made':
      case 'model_switched':
        // 这些事件主要用于日志展示，已在 addLog 处理
        break

      case 'search_degraded':
        // 搜索降级（关键词无结果，用了热门榜兜底）：弹轻量通知告知用户
        pushNotification({
          type: 'search_degraded',
          message: payload.message || '搜索降级，已使用兜底数据',
          suggestion: payload.searched_platforms
            ? `已搜索平台：${Array.isArray(payload.searched_platforms) ? payload.searched_platforms.join(', ') : payload.searched_platforms}`
            : undefined,
        })
        break

      case 'recovery_attempt':
        // Recovery 开始一次尝试，日志级别 info
        // payload: {attempt, strategy, adjusted}
        break

      case 'recovery_attempt_failed':
        // Recovery 一次尝试失败，日志级别 warning
        // payload: {attempt, strategy, error, error_type}
        break

      case 'recovery_success':
        // Recovery 最终成功（第 N 次尝试后成功）
        // payload: {attempt, strategy}
        break

      case 'recovery_exhausted':
        // Recovery 所有策略耗尽，最终失败
        // payload: {attempts, last_error}
        // 节点会走 fallback_output，不影响工作流继续
        break

      case 'circuit_open':
        // 熔断器开启，请求被拒绝
        // payload: {state}
        break
    }
  }

  /** 添加事件日志 */
  function addLog(eventType: string, payload: any, eventId: string) {
    const levelMap: Record<string, EventLog['level']> = {
      workflow_started: 'info',
      workflow_completed: 'success',
      workflow_error: 'error',
      workflow_suspended: 'warning',
      node_started: 'info',
      node_completed: 'success',
      node_error: 'error',
      node_status_changed: 'info',
      review_required: 'warning',
      search_degraded: 'warning',
      recovery_attempt: 'info',
      recovery_attempt_failed: 'warning',
      recovery_success: 'success',
      recovery_exhausted: 'error',
      circuit_open: 'error',
    }
    const level = levelMap[eventType] || 'info'

    // 生成可读消息
    let message = eventType
    if (payload.node_id) {
      message = `${eventType} · ${payload.node_id}`
    } else if (payload.message) {
      message = payload.message
    } else if (payload.topic) {
      message = `${eventType} · topic=${payload.topic}`
    }

    eventLogs.value.push({
      event_id: eventId,
      event_type: eventType,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      message,
      level,
    })

    // 限制日志数量
    if (eventLogs.value.length > 200) {
      eventLogs.value = eventLogs.value.slice(-200)
    }
  }

  /** 取消订阅 */
  function unsubscribeFromWorkflow() {
    if (eventSource.value) {
      eventSource.value.close()
      eventSource.value = null
    }
    isStreaming.value = false
  }

  function clearError() {
    error.value = null
  }

  function reset() {
    unsubscribeFromWorkflow()
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    if (publishCheckTimer) {
      clearInterval(publishCheckTimer)
      publishCheckTimer = null
    }
    currentWorkflow.value = null
    nodes.value = []
    eventLogs.value = []
    error.value = null
  }

  /** 恢复未完成的工作流（页面刷新后调用）。
   *
   * 从 localStorage 读取最近工作流 ID，调 getDetail 检查状态：
   * - 若为 running/suspended → 恢复 SSE 订阅 + 轮询，并用 getNodes 重建 nodes
   * - 若为终态（completed/error/terminated/failed）→ 不恢复
   *
   * getNodes 接口已支持从 LangGraph checkpoint 重建节点状态，
   * 即使后端重启（sse_bus 事件历史清空）也能返回正确状态。
   */
  async function restoreWorkflow(): Promise<boolean> {
    const wfId = localStorage.getItem('mint_active_workflow_id')
    if (!wfId) return false
    try {
      const resp: any = await workflowApi.getDetail(wfId)
      const wfData = resp?.data ?? resp
      if (!wfData || !wfData.workflow_id) {
        localStorage.removeItem('mint_active_workflow_id')
        return false
      }
      const status = wfData.status
      // 终态工作流不恢复
      if (['completed', 'error', 'terminated', 'cancelled', 'failed'].includes(status)) {
        localStorage.removeItem('mint_active_workflow_id')
        return false
      }
      // 恢复 running/suspended 工作流
      currentWorkflow.value = wfData as WorkflowResponse
      // 用 getNodes 重建节点状态（从 checkpoint 兜底）
      try {
        const nodesResp: any = await workflowApi.getNodes(wfId)
        const nodesData = nodesResp?.data ?? nodesResp
        if (nodesData?.nodes) {
          nodes.value = nodesData.nodes
        }
      } catch {
        // getNodes 失败不阻塞，SSE/轮询会补上
      }
      // 恢复 SSE 订阅 + 轮询
      subscribeToWorkflow(wfId)
      startPollingFallback(wfId)
      return true
    } catch {
      localStorage.removeItem('mint_active_workflow_id')
      return false
    }
  }

  /** 加载工作流历史列表 */
  async function loadWorkflowList(params?: { status?: string; limit?: number; offset?: number }) {
    workflowListLoading.value = true
    try {
      const result = await workflowApi.list(params)
      workflowList.value = result.items
      workflowListTotal.value = result.total
    } catch (e) {
      console.error('加载工作流列表失败', e)
    } finally {
      workflowListLoading.value = false
    }
  }

  /** 切换到指定工作流（从历史列表点击恢复） */
  async function switchToWorkflow(workflowId: string): Promise<boolean> {
    try {
      // 先清理旧的 SSE 和轮询
      if (eventSource.value) {
        eventSource.value.close()
        eventSource.value = null
      }
      isStreaming.value = false
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
      if (publishCheckTimer) { clearInterval(publishCheckTimer); publishCheckTimer = null }

      const resp: any = await workflowApi.getDetail(workflowId)
      const wfData = resp?.data ?? resp
      const wfStatus = wfData?.status || wfData?.workflow_status

      currentWorkflow.value = wfData as WorkflowResponse
      localStorage.setItem('mint_active_workflow_id', workflowId)

      // 加载节点数据
      try {
        const nodesResp: any = await workflowApi.getNodes(workflowId)
        const nodesData = nodesResp?.data ?? nodesResp
        const nodeList = nodesData?.nodes || []
        nodes.value = nodeList
      } catch (e) {
        console.error('[switchToWorkflow] getNodes failed:', e)
        nodes.value = []
      }

      // 活跃工作流：恢复 SSE + 轮询
      if (!['completed', 'error', 'terminated', 'failed', 'cancelled'].includes(wfStatus)) {
        subscribeToWorkflow(workflowId)
        startPollingFallback(workflowId)
      }

      return true
    } catch (e) {
      console.error('切换工作流失败', e)
      return false
    }
  }

  return {
    currentWorkflow,
    nodes,
    eventLogs,
    isLoading,
    error,
    isStreaming,
    sseSessionReady,
    notifications,
    pendingReviews,
    runningNodes,
    completedNodes,
    progress,
    startWorkflow,
    fetchWorkflowDetail,
    pauseWorkflow,
    resumeWorkflow,
    terminateWorkflow,
    cancelWorkflow,
    rollbackWorkflow,
    submitReview,
    updateNodeOutput,
    subscribeToWorkflow,
    unsubscribeFromWorkflow,
    startPollingFallback,
    ensureSseSession,
    clearError,
    reset,
    restoreWorkflow,
    loadWorkflowList,
    switchToWorkflow,
    workflowList,
    workflowListTotal,
    workflowListLoading,
    pushNotification,
    dismissNotification,
    clearNotifications,
  }
})