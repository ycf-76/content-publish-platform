import { authFetch } from './client'

/** 点踩维度选项 */
export const DISLIKE_DIMENSIONS = ['结果不对', '太慢', '格式乱', '其他'] as const
export type DislikeDimension = typeof DISLIKE_DIMENSIONS[number]

export interface FeedbackEvent {
  id: string
  user_id: string
  workflow_id: string | null
  session_id: string | null
  event_type: 'like' | 'dislike' | 'retry'
  dimension: string | null
  created_at: string
}

export interface FeedbackStats {
  time_range_days: number
  likes: number
  dislikes: number
  retries: number
  retry_rate: number
  completed_workflows: number
  dislike_dimensions: Record<string, number>
  affected_sessions: number
}

export async function createFeedbackEvent(
  event_type: 'like' | 'dislike' | 'retry',
  opts: {
    workflow_id?: string | null
    session_id?: string | null
    dimension?: string | null
  } = {},
): Promise<FeedbackEvent | null> {
  try {
    const res = await authFetch('/api/feedback', {
      method: 'POST',
      body: JSON.stringify({
        type: event_type,
        workflow_id: opts.workflow_id ?? null,
        session_id: opts.session_id ?? null,
        dimension: opts.dimension ?? null,
      }),
    })
    if (!res.ok) {
      console.error('[feedback] create failed:', res.status, await res.text())
      return null
    }
    const data = await res.json()
    return data.data as FeedbackEvent
  } catch (e) {
    console.error('[feedback] create error:', e)
    return null
  }
}

export async function deleteFeedbackEvent(id: string): Promise<boolean> {
  try {
    const res = await authFetch(`/api/feedback/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
    return res.ok
  } catch (e) {
    console.error('[feedback] delete error:', e)
    return false
  }
}

export async function getFeedbackStats(days: number = 7): Promise<FeedbackStats | null> {
  try {
    const res = await authFetch(
      `/api/feedback/stats?days=${encodeURIComponent(days)}`,
      { method: 'GET' },
    )
    if (!res.ok) return null
    const data = await res.json()
    return data.data as FeedbackStats
  } catch (e) {
    console.error('[feedback] stats error:', e)
    return null
  }
}

export async function getWorkflowFeedback(
  workflow_id: string,
): Promise<FeedbackEvent[]> {
  try {
    const res = await authFetch(
      `/api/feedback/workflow/${encodeURIComponent(workflow_id)}`,
      { method: 'GET' },
    )
    if (!res.ok) return []
    const data = await res.json()
    return data.data as FeedbackEvent[]
  } catch (e) {
    console.error('[feedback] workflow feedback error:', e)
    return []
  }
}
