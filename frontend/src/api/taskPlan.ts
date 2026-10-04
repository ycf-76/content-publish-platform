import apiClient from './client'

// ============================================================================
// 类型定义（与 backend app/api/routers/task_plan.py、app/services/task_plan.py 对齐）
// ============================================================================

/** 拆解预览单条 */
export interface DecomposeItem {
  day_index: number
  topic: string
  keyword?: string | null
}

/** POST /task-plans/decompose 返回 */
export interface DecomposeResult {
  title: string
  daily_time: string
  total_days: number
  items: DecomposeItem[]
  warnings: string[]
}

/** 清单状态 */
export type TaskPlanStatus = 'active' | 'paused' | 'completed' | 'cancelled'

/** 清单摘要（列表项） */
export interface TaskPlanSummary {
  id: string
  title: string
  intent_text: string
  status: TaskPlanStatus
  account_id: string | null
  plan_config: {
    daily_time?: string
    review_mode?: string
    publish_strategy?: string
    [key: string]: any
  }
  total_days: number
  published_days: number
  failed_days: number
  created_at: string | null
}

/** 单日执行记录 */
export interface TaskRunInfo {
  id: string
  status: 'running' | 'awaiting_confirmation' | 'succeeded' | 'failed' | 'skipped' | 'timeout'
  workflow_id: string | null
  failure_reason: string | null
  detail: Record<string, any>
  created_at: string | null
  finished_at: string | null
}

/** 逐日条目 */
export interface TaskItemInfo {
  id: string
  day_index: number
  topic: string
  keyword: string | null
  plan_time: string | null
  status: 'pending' | 'running' | 'published' | 'failed' | 'skipped' | 'cancelled'
  retry_count: number
  last_error: { reason?: string; at?: string } | null
  workflow_id: string | null
  latest_run: TaskRunInfo | null
}

/** 清单详情（摘要 + 逐日条目） */
export interface TaskPlanDetail extends TaskPlanSummary {
  items: TaskItemInfo[]
}

/** 创建清单请求 */
export interface CreatePlanPayload {
  intent_text: string
  title: string
  account_id?: string | null
  items: { day_index: number; topic: string; keyword?: string | null }[]
  plan_config?: {
    daily_time?: string
    review_mode?: 'quality_gate' | 'auto' | 'manual'
    publish_strategy?: 'manual' | 'auto'
    [key: string]: any
  }
}

// ============================================================================
// API（拦截器已解包 axios response，这里再取 StandardResponse.data）
// ============================================================================

/** 意图拆解预览（无副作用）。dry_run=true 走规则拆解，零 token 测试路径 */
export async function decomposeIntent(
  intentText: string,
  dailyTime?: string,
  dryRun = false,
): Promise<DecomposeResult> {
  const res = await apiClient.post('/task-plans/decompose', {
    intent_text: intentText,
    daily_time: dailyTime || null,
    dry_run: dryRun,
  })
  return res.data
}

/** 创建并激活清单（调度器按 plan_time 逐日自动执行） */
export async function createTaskPlan(payload: CreatePlanPayload): Promise<{ id: string; total_days: number; status: string }> {
  const res = await apiClient.post('/task-plans', payload)
  return res.data
}

/** 清单列表 */
export async function listTaskPlans(): Promise<TaskPlanSummary[]> {
  const res = await apiClient.get('/task-plans')
  return res.data || []
}

/** 清单详情（逐日条目 + 执行记录） */
export async function getTaskPlanDetail(planId: string): Promise<TaskPlanDetail | null> {
  const res = await apiClient.get(`/task-plans/${planId}`)
  return res.data
}

/** 暂停清单 */
export async function pauseTaskPlan(planId: string): Promise<{ id: string; status: string }> {
  const res = await apiClient.post(`/task-plans/${planId}/pause`)
  return res.data
}

/** 恢复暂停的清单 */
export async function resumeTaskPlan(planId: string): Promise<{ id: string; status: string }> {
  const res = await apiClient.post(`/task-plans/${planId}/resume`)
  return res.data
}

/** 取消清单（未执行条目全部取消，不可恢复） */
export async function cancelTaskPlan(planId: string): Promise<{ id: string; status: string }> {
  const res = await apiClient.post(`/task-plans/${planId}/cancel`)
  return res.data
}
