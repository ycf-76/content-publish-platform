import { authFetch } from './client'

/** Agent 自我进化 — 进化建议（LLM 复盘产出的人审草稿） */
export type EvolutionProposalStatus = 'pending_review' | 'approved' | 'rejected'

export type TriggerSource = 'auto_error' | 'auto_dislike' | 'auto_suspended' | 'manual'

export interface EvolutionProposal {
  id: string
  user_id: string
  workflow_id: string | null
  trigger_source: TriggerSource
  trigger_reason: string
  /** 详情接口才有，列表接口为节省带宽不含此字段 */
  suggestion_md?: string | null
  status: EvolutionProposalStatus
  review_comment: string | null
  reviewed_at: string | null
  applied_at: string | null
  created_at: string
}

export interface EvolutionProposalList {
  items: EvolutionProposal[]
  total: number
  limit: number
  offset: number
}

/** 查询建议列表（按状态过滤，创建时间倒序） */
export async function listEvolutionProposals(
  opts: { status?: EvolutionProposalStatus | null; limit?: number; offset?: number } = {},
): Promise<EvolutionProposalList | null> {
  try {
    const params = new URLSearchParams()
    if (opts.status) params.set('status', opts.status)
    if (opts.limit) params.set('limit', String(opts.limit))
    if (opts.offset) params.set('offset', String(opts.offset))
    const qs = params.toString()
    const res = await authFetch(`/api/evolution/proposals${qs ? `?${qs}` : ''}`, { method: 'GET' })
    if (!res.ok) {
      console.error('[evolution] list failed:', res.status, await res.text())
      return null
    }
    const data = await res.json()
    return data.data as EvolutionProposalList
  } catch (e) {
    console.error('[evolution] list error:', e)
    return null
  }
}

/** 查看单条建议详情（含 markdown 建议草稿） */
export async function getEvolutionProposal(id: string): Promise<EvolutionProposal | null> {
  try {
    const res = await authFetch(`/api/evolution/proposals/${encodeURIComponent(id)}`, { method: 'GET' })
    if (!res.ok) return null
    const data = await res.json()
    return data.data as EvolutionProposal
  } catch (e) {
    console.error('[evolution] detail error:', e)
    return null
  }
}

/** 人审操作：approve（批准转正）/ reject（拒绝归档） */
export async function reviewEvolutionProposal(
  id: string,
  decision: 'approve' | 'reject',
  comment?: string,
): Promise<{ ok: boolean; status?: EvolutionProposalStatus; message?: string }> {
  try {
    const res = await authFetch(`/api/evolution/proposals/${encodeURIComponent(id)}/review`, {
      method: 'POST',
      body: JSON.stringify({ decision, comment: comment ?? null }),
    })
    const data = await res.json()
    if (!res.ok) {
      return { ok: false, message: data?.detail || data?.message || `审核失败 (${res.status})` }
    }
    return { ok: true, status: data.data?.status, message: data.message }
  } catch (e) {
    console.error('[evolution] review error:', e)
    return { ok: false, message: '网络错误，审核失败' }
  }
}

/** 手动触发某个工作流的 LLM 复盘 */
export async function triggerWorkflowReflection(
  workflow_id: string,
): Promise<boolean> {
  try {
    const res = await authFetch(`/api/evolution/reflect/${encodeURIComponent(workflow_id)}`, {
      method: 'POST',
    })
    return res.ok
  } catch (e) {
    console.error('[evolution] reflect error:', e)
    return false
  }
}
