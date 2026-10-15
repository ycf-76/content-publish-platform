/**
 * StreamEngine — 流式文本播放引擎（渲染层重构 L3）
 *
 * 移植自 Codex CLI 的 AdaptiveChunkingPolicy 两档模型，与框架无关（纯 TS、可单测）：
 *
 * - raw / shown 双游标：feed() 只追加「已真实到达」的文本，step() 按帧释放到
 *   shown。显示内容永远 ≤ 真实已到达内容，绝不抢跑。
 * - Smooth 档（默认）：严格匀速 baseCps，这是「codex 匀速感」的本体——
 *   后端 burst 再猛也按这个速度吐，用户永远以固定节奏阅读。
 * - CatchUp 档（兜底）：积压超过 enterChars 时进入，追赶目标 = 积压 / catchUpSeconds，
 *   防止后端一口气吐完几千字时让用户干等；积压降到 exitChars 以下并保持
 *   exitHoldMs 后回到 Smooth（滞回，避免在阈值附近反复跳档）。
 * - 固定步长推进（1/120s）：消除 rAF/setInterval 帧率抖动导致的视觉跳跃。
 *
 * 设计约束：
 * - 不依赖 Vue / DOM / 时间源，时间由调用方通过 step(nowMs) 注入，测试可用假时钟。
 * - 状态机只通过 step() 前进，任何一个 step 都是纯函数式的一帧，可回放断言。
 */

export type StreamGear = 'smooth' | 'catchup'

export interface StreamEngineOptions {
  /** Smooth 档恒定显示速率（字符/秒） */
  baseCps: number
  /** 速率下界（CatchUp 退出后不低于此值） */
  minCps?: number
  /** 速率上界（CatchUp 封顶） */
  maxCps?: number
  /** CatchUp 追赶目标：把积压摊到这么多秒内显示完，默认 0.35 */
  catchUpSeconds?: number
  /** 退出 CatchUp 的滞回保持时长（ms），默认 250 */
  exitHoldMs?: number
  /** 进入 CatchUp 的积压阈值（字符），默认 max(80, baseCps*0.6) 运行时动态计算 */
  enterChars?: number
  /** 退出 CatchUp 的积压阈值（字符），默认 max(20, baseCps*0.15) 运行时动态计算 */
  exitChars?: number
  /**
   * CatchUp 速率相对 baseCps 的倍数上限（默认 2）。
   * 关键约束：再大的积压也不超过这个倍数——否则后端一次性吐几千字时
   * （agent 路径正文随 POST 一次性到达），追赶目标 = 积压/0.35 会算出
   * 几千 cps，表现为「飞速输出完」，违背匀速设计前提。
   */
  maxCatchUpMultiplier?: number
  /**
   * 终态后的落档速率倍数上限（默认 2.2）。
   * 输入已结束（markFinished）时剩余积压按此温和追完，对应旧版
   * pendingSettle 的 2.2× 封顶：长文不等太久，也不会「一坨涌出来」。
   */
  settleMultiplier?: number
}

const FIXED_STEP = 1 / 120 // 固定步长：120fps 细分，与 codex COMMIT_ANIMATION_TICK 对齐
const MAX_STEPS_PER_FRAME = 16 // 单帧步数上限，防止卡顿后一帧暴走

export class StreamEngine {
  /** 已真实到达的全部文本（feed 的累积） */
  raw = ''
  /** 已显示字符数（float，逐步逼近 raw.length） */
  shown = 0
  /** 输入是否已结束（终态事件到达） */
  finished = false

  private _cps = 0
  private _acc = 0
  private _gear: StreamGear = 'smooth'
  private _belowSince = 0
  private _lastExit = 0
  private _lastNow = 0

  private readonly _baseCps: number
  private readonly _minCps: number
  private readonly _maxCps: number
  private readonly _catchUpSeconds: number
  private readonly _exitHoldMs: number
  private readonly _enterChars?: number
  private readonly _exitChars?: number
  private readonly _maxCatchUpCps: number
  private readonly _settleMaxCps: number

  constructor(opts: StreamEngineOptions) {
    this._baseCps = Math.max(1, opts.baseCps)
    this._minCps = Math.max(1, opts.minCps ?? this._baseCps * 0.5)
    this._maxCps = Math.max(this._baseCps, opts.maxCps ?? 6000)
    this._catchUpSeconds = Math.max(0.05, opts.catchUpSeconds ?? 0.35)
    this._exitHoldMs = Math.max(0, opts.exitHoldMs ?? 250)
    this._enterChars = opts.enterChars
    this._exitChars = opts.exitChars
    // 追赶/收尾速率都被 baseCps 的倍数封顶——匀速是常态，追赶只是兜底
    this._maxCatchUpCps = this._baseCps * Math.max(1, opts.maxCatchUpMultiplier ?? 2)
    this._settleMaxCps = this._baseCps * Math.max(1, opts.settleMultiplier ?? 2.2)
  }

  /** 当前速率（字符/秒），向目标值指数缓动，单帧变化受限 */
  get cps(): number {
    return this._cps
  }

  get gear(): StreamGear {
    return this._gear
  }

  /** 积压字符数（已到达但尚未显示） */
  get backlog(): number {
    return Math.max(0, this.raw.length - this.shown)
  }

  /** 已显示的文本 */
  get shownText(): string {
    return this.raw.slice(0, Math.floor(this.shown))
  }

  /** 输入结束且全部显示完毕 */
  get done(): boolean {
    return this.finished && this.shown >= this.raw.length
  }

  /** 追加真实到达的文本 */
  feed(text: string): void {
    if (!text) return
    this.raw += text
  }

  /** 标记输入结束（终态事件到达）。剩余积压按 CatchUp 追完。 */
  markFinished(): void {
    this.finished = true
  }

  /** 立即显示完全部（取消播放：用户中断/错误路径） */
  settle(): void {
    this.shown = this.raw.length
    this._cps = 0
    this._acc = 0
  }

  /** 重置到初始状态（同一实例复用） */
  reset(): void {
    this.raw = ''
    this.shown = 0
    this.finished = false
    this._cps = 0
    this._acc = 0
    this._gear = 'smooth'
    this._belowSince = 0
    this._lastExit = 0
  }

  /**
   * 推进一帧。
   * @param nowMs 当前时间戳（ms，与上次 step 同一时间源）
   * @returns shown 是否有推进（调用方可据此跳过 DOM 更新）
   */
  step(nowMs: number): boolean {
    if (this._lastNow === 0) this._lastNow = nowMs
    // dt 夹紧到 0.5s：后台标签页恢复 / 预览 iframe 被节流时，
    // 避免单帧 dt 巨大导致「涌一大段」；同时保证低帧率环境下仍可见地推进。
    const dt = Math.min(Math.max((nowMs - this._lastNow) / 1000, 0), 0.5)
    this._lastNow = nowMs

    const backlog = this.backlog
    if (backlog <= 0) {
      // 无积压：重置动态速率。持续平静超过 exitHoldMs 后回归 Smooth，
      // 否则下一段输入会直接以 CatchUp 起步（违背「默认匀速」的设计前提）。
      if (this._gear === 'catchup') {
        if (!this._belowSince) this._belowSince = nowMs
        else if (nowMs - this._belowSince >= this._exitHoldMs) {
          this._gear = 'smooth'
          this._lastExit = nowMs
          this._belowSince = 0
        }
      }
      this._cps = 0
      this._acc = 0
      return false
    }
    this._belowSince = 0

    this._updateGear(nowMs, backlog)

    // 目标速率：
    // - 终态（输入已结束）：2.2×base 封顶温和追完。这是 agent 路径的主场景
    //   （正文随 POST 一次性到达，几千字一次喂入）——绝不能按 backlog/0.35
    //   算出几千 cps「飞速倾泻」，也不必严格匀速让用户干等长文。
    // - 实时流：Smooth 严格匀速 baseCps；CatchUp 追赶目标 = 积压/catchUpSeconds，
    //   但同样封顶 2×base——后端 burst 再猛，显示速率最多翻倍，体感始终接近匀速。
    let target: number
    if (this.finished) {
      target = Math.min(this._settleMaxCps, Math.max(this._baseCps, backlog / 0.6))
    } else if (this._gear === 'catchup') {
      target = Math.min(this._maxCatchUpCps, Math.max(this._minCps, backlog / this._catchUpSeconds))
    } else {
      target = this._baseCps
    }
    target = Math.min(target, this._maxCps)

    // 速率缓动（惯性）：单帧变化受限，绝不从 50 一帧跳到 3000
    const tau = this._gear === 'catchup' ? 0.18 : 0.32
    const k = 1 - Math.exp(-dt / tau)
    this._cps += (target - this._cps) * k

    // 固定步长推进：把 dt 拆成 1/120s 小步，消除帧率抖动导致的视觉跳跃
    this._acc += dt
    let steps = 0
    while (this._acc >= FIXED_STEP && this.shown < this.raw.length && steps < MAX_STEPS_PER_FRAME) {
      this._acc -= FIXED_STEP
      steps++
      this.shown = Math.min(this.raw.length, this.shown + FIXED_STEP * this._cps)
    }
    if (steps === MAX_STEPS_PER_FRAME) this._acc = 0 // 丢弃残余，防暴走
    return steps > 0
  }

  private _updateGear(nowMs: number, backlog: number): void {
    const enter = this._enterChars ?? Math.max(80, this._baseCps * 0.6)
    const exit = this._exitChars ?? Math.max(20, this._baseCps * 0.15)

    if (this._gear === 'smooth') {
      // 刚退出追赶的 250ms 内不轻易再进入（滞回上半环）
      if (backlog >= enter && !(nowMs - this._lastExit < this._exitHoldMs && backlog < enter * 3)) {
        this._gear = 'catchup'
        this._belowSince = 0
      }
    } else {
      if (backlog <= exit) {
        if (!this._belowSince) this._belowSince = nowMs
        else if (nowMs - this._belowSince >= this._exitHoldMs) {
          this._gear = 'smooth'
          this._lastExit = nowMs
          this._belowSince = 0
        }
      } else {
        this._belowSince = 0
      }
    }
  }
}
