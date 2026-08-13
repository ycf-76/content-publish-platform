import apiClient from './client'

/** 用户在右侧工作区选择的模型/温度/风格配置（对齐后端 StartWorkflowRequest.model_settings） */
export interface ModelSettings {
  /** 文本生成模型（展示名，后端做映射），如 "DeepSeek V3" / "DeepSeek R1" */
  text_model?: string
  /** 图片生成模型（预留），如 "通义万相 wanx-v1" */
  image_model?: string
  /** 温度参数 0.0-1.0，控制文本生成随机性 */
  temperature?: number
  /** 文风，如 "活泼少女"/"知性优雅"/"专业干货"/"慵懒随性"（向后兼容，优先级低于 copywrite_skill） */
  writing_style?: string
  /** 图片风格，如 "清新自然"/"日系胶片"/"暖阳滤镜"/"复古胶片"（向后兼容，优先级低于 image_gen_skill） */
  image_style?: string
  /** copywrite 节点 Skill 名（如 "lively_girl"/"elegant"/"poetic"），优先级高于 writing_style */
  copywrite_skill?: string
  /** image_gen 节点 Skill 名（如 "fresh_natural"/"cyberpunk"），优先级高于 image_style */
  image_gen_skill?: string
  /** analyze 节点 Skill 名（如 "standard"） */
  analyze_skill?: string
  /** audit 节点 Skill 名（如 "standard"） */
  audit_skill?: string
}

/** Skill 元数据（对齐后端 Skill.metadata()） */
export interface SkillMeta {
  node_type: string
  name: string
  display_name: string
  description: string
  default_config: Record<string, any>
}

/** 启动工作流请求（对齐后端 StartWorkflowRequest） */
export interface WorkflowStartRequest {
  topic: string
  account_id: string
  /** 用户在右侧工作区选择的模型/温度/风格配置 */
  model_settings?: ModelSettings
  /** 选题池参考素材（从选题池"发起新工作流"时携带） */
  reference?: Record<string, any>
}

/** 工作流响应（对齐后端 WorkflowResponse） */
export interface WorkflowResponse {
  workflow_id: string
  user_id: string
  account_id: string
  topic: string
  status: string
  current_node: string
  created_at: string
}

/** 节点快照 */
export interface NodeSnapshot {
  node_id: string
  node_type: string
  status: 'idle' | 'pending' | 'running' | 'awaiting_review' | 'passed' | 'rejected' | 'error' | 'suspended' | 'completed' | 'terminated'
  result?: any
  output?: Record<string, any>
  error?: string
  agent_thinking?: string
}

/** 工作流详情（含节点列表） */
export interface WorkflowSnapshot {
  workflow_id: string
  status: string
  current_node: string
  progress: number
  nodes: NodeSnapshot[]
  pending_reviews: number
  created_at: string
  updated_at: string
}

/** 审核提交请求 */
export interface ReviewSubmitRequest {
  action: 'pass' | 'reject' | 'regenerate'
}

/** 工作流控制动作 */
export type WorkflowControlAction = 'pause' | 'resume' | 'rollback' | 'terminate'

export const workflowApi = {
  /** 启动工作流 POST /api/workflows */
  start(data: WorkflowStartRequest) {
    return apiClient.post<WorkflowResponse>('/workflows', data)
  },

  /** 拉取可用 Skill 列表 GET /api/skills?node_type=xxx */
  async listSkills(nodeType?: string): Promise<Record<string, SkillMeta[]>> {
    const url = nodeType ? `/skills?node_type=${encodeURIComponent(nodeType)}` : '/skills'
    const resp: any = await apiClient.get(url)
    // 后端 StandardResponse 包装：{success, data, message}
    return (resp?.data ?? resp) as Record<string, SkillMeta[]>
  },

  /** 获取工作流详情 GET /api/workflows/{id} */
  getDetail(workflowId: string) {
    return apiClient.get<WorkflowResponse>(`/workflows/${workflowId}`)
  },

  /** 获取节点状态+输出（轮询兜底，SSE 不可靠时使用） GET /api/workflows/{id}/nodes */
  getNodes(workflowId: string) {
    return apiClient.get<{ workflow_id: string; status: string; nodes: any[] }>(`/workflows/${workflowId}/nodes`)
  },

  /** 获取节点图片 base64 列表 GET /api/workflows/{id}/nodes/{node_id}/images
   *  SSE 事件和 getNodes 都剥离了 images_base64，审核阶段需单独调本接口。
   *  设置 60s 超时（图片数据可能较大）。
   */
  getNodeImages(workflowId: string, nodeId: string) {
    return apiClient.get<{ node_id: string; images_base64: string[]; image_count: number }>(
      `/workflows/${workflowId}/nodes/${nodeId}/images`,
      { timeout: 60000 },
    )
  },

  /** 暂停 POST /api/workflows/{id}/pause */
  pause(workflowId: string, reason?: string) {
    return apiClient.post<{ success: boolean; message: string }>(`/workflows/${workflowId}/pause`, { reason: reason || '' })
  },

  /** 恢复 POST /api/workflows/{id}/resume */
  resume(workflowId: string) {
    return apiClient.post<{ success: boolean; message: string }>(`/workflows/${workflowId}/resume`)
  },

  /** 终止 POST /api/workflows/{id}/terminate */
  terminate(workflowId: string) {
    return apiClient.post<{ success: boolean; message: string }>(`/workflows/${workflowId}/terminate`)
  },

  /** 回滚 POST /api/workflows/{id}/rollback */
  rollback(workflowId: string, targetNode: string) {
    return apiClient.post<{ success: boolean; message: string }>(`/workflows/${workflowId}/rollback`, { target_node: targetNode })
  },

  /** 更新节点输出（人工编辑） PATCH /api/workflows/{id}/nodes/{node_id}/output */
  updateNodeOutput(workflowId: string, nodeId: string, output: Record<string, any>) {
    return apiClient.patch<{ success: boolean; message: string; output: any }>(`/workflows/${workflowId}/nodes/${nodeId}/output`, { output })
  },

  /** 提交审核 POST /api/workflows/{id}/reviews/{review_id} */
  submitReview(
    workflowId: string,
    reviewId: string,
    action: 'pass' | 'reject' | 'regenerate',
    selectedCandidate?: string,
  ) {
    const payload: Record<string, unknown> = { action }
    if (selectedCandidate) payload.selected_candidate = selectedCandidate
    return apiClient.post<{ success: boolean; message: string }>(
      `/workflows/${workflowId}/reviews/${reviewId}`,
      payload,
    )
  },

  /** 注入卡片图片 POST /api/workflows/{id}/inject-card-images
   *  注意：base64 图片数据量可能很大（4张 1080×1440 PNG ≈ 15-25MB），
   *  需要单独设置 120s 超时，避免默认 30s 超时导致注入失败。
   */
  injectCardImages(
    workflowId: string,
    imagesBase64: string[],
    imageDetails?: Array<Record<string, any>>,
    style?: string,
    planContext?: Record<string, any>,
  ) {
    return apiClient.post<{ success: boolean; message: string }>(
      `/workflows/${workflowId}/inject-card-images`,
      {
        images_base64: imagesBase64,
        image_details: imageDetails || [],
        style: style || '',
        plan_context: planContext || {},
      },
      { timeout: 120000 }, // 120s，大图片传输专用
    )
  },

  /** 回查半自动发布结果 POST /api/workflows/{id}/publish/check */
  checkPublishResult(workflowId: string) {
    return apiClient.post<{
      status: 'pending' | 'published' | 'failed' | 'session_invalid' | 'not_applicable'
      url: string
      message: string
    }>(`/workflows/${workflowId}/publish/check`)
  },

  /**
   * 订阅工作流 SSE 事件流 GET /api/sse/workflow/{id}
   *
   * 使用 fetch + AbortController 实现（而非 EventSource）：
   * - EventSource.close() 活跃连接时浏览器会记录 net::ERR_ABORTED，无法抑制
   * - fetch + AbortController 可主动中止且不触发浏览器错误日志
   * - 支持手动解析 SSE 格式（id/event/data 行）
   *
   * 后端 SSE 事件格式：
   *   id: evt_xxx
   *   event: workflow_started
   *   data: {"event_id":"evt_xxx","type":"workflow_started","payload":{...},"timestamp":"..."}
   *   （空行表示事件结束）
   *   : heartbeat（注释行，心跳）
   */
  subscribe(
    workflowId: string,
    onEvent: (eventType: string, payload: any, eventId: string) => void,
    onError?: (error: unknown) => void,
  ): { close: () => void } {
    // SSE 直接打后端 8000，绕过 vite 代理（vite 代理不转发 SSE 流式响应，curl 确认 0 字节）
    const SSE_BASE = import.meta.env.VITE_SSE_BASE_URL || 'http://localhost:8000'
    const url = `${SSE_BASE}/api/sse/workflow/${workflowId}`
    const controller = new AbortController()
    let closed = false // 前端是否主动关闭

    // SSE 解析缓冲区
    let buffer = ''
    let currentEvent = 'message'
    let currentId = ''

    async function consume() {
      try {
        const resp = await fetch(url, {
          method: 'GET',
          credentials: 'include', // 携带 sse_token cookie
          signal: controller.signal,
          headers: {
            'Accept': 'text/event-stream',
          },
        })

        if (!resp.ok) {
          throw new Error(`SSE HTTP ${resp.status}`)
        }

        const reader = resp.body?.getReader()
        if (!reader) {
          throw new Error('SSE stream unavailable')
        }

        const decoder = new TextDecoder('utf-8')

        while (true) {
          const { done, value } = await reader.read()
          if (done) {
            // 后端主动关闭流（如工作流终态后 return），自然退出，不触发 abort
            break
          }

          buffer += decoder.decode(value, { stream: true })

          // 按空行分割事件（SSE 协议：空行表示事件结束）
          let sepIdx: number
          while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
            const rawEvent = buffer.slice(0, sepIdx)
            buffer = buffer.slice(sepIdx + 2)

            // 解析事件行
            currentEvent = 'message'
            currentId = ''
            let dataLines: string[] = []

            for (const line of rawEvent.split('\n')) {
              if (!line || line.startsWith(':')) continue // 空行或注释（心跳）
              const colonIdx = line.indexOf(':')
              const field = colonIdx > 0 ? line.slice(0, colonIdx) : line
              // 值前可能有一个空格（SSE 规范）
              let val = colonIdx > 0 ? line.slice(colonIdx + 1) : ''
              if (val.startsWith(' ')) val = val.slice(1)

              if (field === 'event') {
                currentEvent = val
              } else if (field === 'id') {
                currentId = val
              } else if (field === 'data') {
                dataLines.push(val)
              }
            }

            // 有 data 才回调（心跳和注释不触发）
            if (dataLines.length > 0) {
              const dataStr = dataLines.join('\n')
              try {
                const parsed = JSON.parse(dataStr)
                const eventType = currentEvent !== 'message'
                  ? currentEvent
                  : (parsed.type || 'message')
                const payload = parsed.payload ?? parsed
                const eventId = parsed.event_id ?? currentId ?? ''
                onEvent(eventType, payload, eventId)
              } catch (err) {
                console.error('SSE parse error:', err, dataStr)
              }
            }
          }
        }
      } catch (err: any) {
        // AbortError 是前端主动关闭，不算错误，不回调
        if (err?.name === 'AbortError') return
        if (closed) return // 已主动关闭，忽略后续错误
        console.warn('SSE connection interrupted:', err?.message || err)
        if (onError) onError(err)
      }
    }

    consume()

    return {
      close() {
        closed = true
        if (!controller.signal.aborted) {
          controller.abort()
        }
      },
    }
  },
}