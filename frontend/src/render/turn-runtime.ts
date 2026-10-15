/**
 * TurnRuntime — 回合沙箱（渲染层重构 L2，问题 6 根治）
 *
 * 同一会话连续多轮对话时，后端 SSE bus 以 session_id 为 key 复用，
 * 订阅时会回放该 key 下的全部历史事件。没有回合边界时，上一轮的
 * chat_turn_started / deltas / workflow_completed 会整体灌进新消息——
 * 表现为「同一个对话，第二个任务永远显示第一个任务的输出」。
 *
 * TurnRuntime 的职责：
 * - 持有本回合 ID（前端发送前生成，后端全链路回传，见 sse_bus.turn_id）
 * - 事件准入：只接收 turn_id 与本回合一致的事件；无 turn_id 的遗留事件
 *   在启用隔离后一律拒绝并计数（旧 replay 正是从没有 turn_id 的
 *   chat_turn_started 开始泄洪的）
 * - 计时：本回合开始/结束时间，供 UI 在 logo 下展示总耗时（问题 3）
 *
 * 与后端修复（sse_bus.subscribe 按 turn_id 回放）构成双保险：
 * 后端不泄、前端不接。
 */

export interface TurnEventLike {
  turn_id?: string | null
  type?: string
  event_type?: string
  payload?: Record<string, unknown> | null
}

let _seq = 0

/** 生成回合 ID：turn_<时间戳36>_<序号>_<随机>，前端可控、后端可回传 */
export function genTurnId(): string {
  _seq = (_seq + 1) % 100000
  const rand = Math.random().toString(36).slice(2, 8)
  return `turn_${Date.now().toString(36)}_${_seq.toString(36)}${rand}`
}

export class TurnRuntime {
  /** 本回合 ID（后端 chat_turn_started 回传一致的值） */
  turnId: string
  /** 是否已收到本回合的启动事件（chat_turn_started） */
  turnStarted = false
  /** 被拒绝的异回合事件数（UI 展示「已拦截 N 条旧回合事件」） */
  droppedEvents = 0
  /** 后端回传的回合总耗时（ms），来自 workflow_completed.duration_ms */
  durationMs: number | null = null

  private _startedAt: number
  private _endedAt: number | null = null

  constructor(turnId?: string) {
    this.turnId = turnId || genTurnId()
    this._startedAt = Date.now()
  }

  get elapsedMs(): number {
    return (this._endedAt ?? Date.now()) - this._startedAt
  }

  /** 本回合终态事件到达，冻结计时 */
  end(durationMs?: number | null): void {
    if (this._endedAt == null) {
      this._endedAt = Date.now()
      if (typeof durationMs === 'number' && durationMs > 0) this.durationMs = durationMs
    }
  }

  /**
   * 事件准入判定。
   * @param ev SSE 事件（含顶层 turn_id）
   * @returns true = 属于本回合，放行；false = 异回合/遗留事件，拒绝
   */
  accepts(ev: TurnEventLike): boolean {
    const et = ev?.turn_id
    if (et && et === this.turnId) {
      this.turnStarted = true
      return true
    }
    if (et && et !== this.turnId) {
      this.droppedEvents++
      return false
    }
    // 无 turn_id 的遗留事件：旧后端/旧历史。启用隔离后一律拒绝——
    // 放行它等于给旧回合的 chat_turn_started 重新开门（问题 6 原型）。
    this.droppedEvents++
    return false
  }
}
