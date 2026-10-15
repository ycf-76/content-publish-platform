import { describe, it, expect } from 'vitest'
import { StreamEngine } from './stream-engine'

/**
 * StreamEngine 单测（渲染层重构 L3）
 *
 * 覆盖：匀速 / 追赶 / 滞回 / dt 夹紧 / 抢跑防护 / 终态封顶 / 惯性缓动。
 * 时钟为调用方注入的假时间（ms），无 rAF/Date 依赖。
 */

const FRAME_MS = 1000 / 60

function makeEngine(overrides: Partial<{ baseCps: number; minCps: number; maxCps: number; catchUpSeconds: number; exitHoldMs: number; enterChars: number; exitChars: number; maxCatchUpMultiplier: number; settleMultiplier: number }> = {}) {
  return new StreamEngine({ baseCps: 160, ...overrides })
}

/** 推进 n 帧，返回推进到的假时间戳 */
function runFrames(engine: StreamEngine, startMs: number, frames: number, dtMs: number = FRAME_MS): number {
  let now = startMs
  for (let i = 0; i < frames; i++) {
    now += dtMs
    engine.step(now)
  }
  return now
}

describe('StreamEngine', () => {
  it('Smooth 档严格匀速：持续小流量喂入时按 baseCps 释放', () => {
    // enterChars 显式调高：喂入速率(3/帧)略大于显示速率(2.67/帧)，
    // 积压会缓慢累积，防止它意外越过追赶阈值抢档
    const engine = makeEngine({ baseCps: 160, enterChars: 500 })
    let now = 0
    // 每帧喂入 3 字符（略快于 baseCps/60≈2.67，积压保持 >0），
    // 模拟真实 SSE 小 delta 流。先预热 2s 越过惯性爬坡
    // （cps 从 0 指数收敛到 baseCps），再测稳态窗口的释放速率。
    // 注意：积压恰好为 0 的帧会把 cps 归零（防下一段输入以追赶速率起步），
    // 所以喂入速率必须略大于显示速率才能测到稳态。
    for (let i = 0; i < 120; i++) {
      now += FRAME_MS
      engine.feed('xxx')
      engine.step(now)
    }
    expect(engine.gear).toBe('smooth')
    const warm = engine.shown
    for (let i = 0; i < 60; i++) {
      now += FRAME_MS
      engine.feed('xxx')
      engine.step(now)
    }
    // 稳态 1 秒释放 ≈160 字符（±10%），且档位保持 smooth
    const released = engine.shown - warm
    expect(released).toBeGreaterThan(160 * 0.9)
    expect(released).toBeLessThan(160 * 1.1)
    expect(engine.gear).toBe('smooth')
  })

  it('绝不抢跑：一次性喂入大段积压，首帧只释放一帧的量', () => {
    const engine = makeEngine({ baseCps: 160 })
    engine.feed('x'.repeat(5000))
    engine.step(FRAME_MS) // 首帧 dt=16.7ms
    expect(engine.shown).toBeLessThan(50)
    expect(engine.shown).toBeLessThan(engine.raw.length)
    expect(engine.raw.length).toBe(5000)
  })

  it('CatchUp 档：积压超阈值后进入追赶，速率封顶 2×baseCps', () => {
    const engine = makeEngine({ baseCps: 160 })
    engine.feed('x'.repeat(2000))
    const end = runFrames(engine, 0, 30) // 0.5s
    expect(engine.gear).toBe('catchup')
    expect(engine.cps).toBeLessThanOrEqual(320 + 1)
    // 0.5s 最多释放 ~320×0.5=160 字符（而非 2000 一次性倾泻）
    expect(engine.shown).toBeLessThanOrEqual(165)
    expect(engine.shown).toBeLessThan(engine.raw.length)
    expect(end).toBeGreaterThan(0)
  })

  it('CatchUp 退出滞回：排空后保持 exitHoldMs 才回 Smooth', () => {
    const engine = makeEngine({ baseCps: 160 })
    engine.feed('x'.repeat(150)) // > enter(96) → 应最终进入 catchup
    // fresh 实例 _lastExit=0，前 250ms 滞回保护期内 1.5×enter 的积压不进档，
    // 多跑几帧越过保护窗口
    let now = runFrames(engine, 0, 20)
    expect(engine.gear).toBe('catchup')

    // 停止喂入，等播放器自然排空到积压精确为 0
    // （引擎语义：backlog>0 的帧会重置保持计时，退出判定以积压归零起算）
    let zeroAt = -1
    for (let i = 0; i < 600 && zeroAt < 0; i++) {
      now += FRAME_MS
      engine.step(now)
      if (engine.backlog === 0) zeroAt = now
    }
    expect(zeroAt).toBeGreaterThan(0)

    // 归零后 240ms（< exitHoldMs=250）：仍是 catchup
    now = runFrames(engine, zeroAt, Math.round(240 / FRAME_MS))
    expect(engine.gear).toBe('catchup')

    // 归零后累计 > 250ms：回 smooth
    now = runFrames(engine, now, Math.round(40 / FRAME_MS) + 2)
    expect(engine.gear).toBe('smooth')
  })

  it('dt 夹紧：单帧 dt=5s 被夹到 0.5s，不会一帧涌完', () => {
    const engine = makeEngine({ baseCps: 160 })
    engine.feed('x'.repeat(100))
    engine.step(1) // 非零起点（_lastNow===0 是未初始化哨兵，step(0) 会吞帧）
    engine.step(1 + 5000) // dt 被夹紧到 0.5s
    // 0.5s × 追赶目标(≤320cps) ≈ 160 的上界；远小于 100 字符倾泻
    expect(engine.shown).toBeLessThan(60)
    expect(engine.shown).toBeLessThan(engine.raw.length)
  })

  it('终态封顶：markFinished 后按 settleMultiplier 温和追完（不半秒倾泻）', () => {
    const engine = makeEngine({ baseCps: 160, settleMultiplier: 2.2 })
    engine.feed('x'.repeat(5000))
    engine.markFinished()
    // 1 秒内释放量 ≤ 352cps × 1s（速率从 0 缓动上升，实际更少）
    runFrames(engine, 0, 60)
    expect(engine.shown).toBeLessThanOrEqual(355)
    expect(engine.done).toBe(false)
    // 继续推进直至播完
    const end = runFrames(engine, 1000, 1500) // 再 25s
    expect(engine.done).toBe(true)
    expect(engine.shown).toBe(engine.raw.length)
    expect(end).toBeGreaterThan(1000)
  })

  it('自定义 settleMultiplier=1 时终态速率不超过 baseCps', () => {
    const engine = makeEngine({ baseCps: 160, settleMultiplier: 1 })
    engine.feed('x'.repeat(3000))
    engine.markFinished()
    runFrames(engine, 0, 60)
    expect(engine.shown).toBeLessThanOrEqual(165)
    expect(engine.done).toBe(false)
  })

  it('CatchUp 倍数闸优先于 maxCps：即使 maxCps=10000 也不超过 2×base', () => {
    const engine = makeEngine({ baseCps: 100, maxCps: 10000, maxCatchUpMultiplier: 2 })
    engine.feed('x'.repeat(4000))
    runFrames(engine, 0, 120) // 2s
    // 无倍数闸时目标 = 4000/0.35 ≈ 11428cps（仅 maxCps 封顶），0.4s 就播完；
    // 有倍数闸后 2s 最多释放 ~200cps×2s=400
    expect(engine.shown).toBeLessThanOrEqual(420)
    expect(engine.done).toBe(false)
  })

  it('settle() 立即显示全部并停机', () => {
    const engine = makeEngine()
    engine.feed('x'.repeat(500))
    engine.step(FRAME_MS)
    engine.settle()
    expect(engine.shown).toBe(500)
    expect(engine.cps).toBe(0)
    expect(engine.step(FRAME_MS * 2)).toBe(false)
  })

  it('done 语义：必须输入结束且全部显示完毕', () => {
    const engine = makeEngine({ baseCps: 400 })
    engine.feed('x'.repeat(10))
    // 未 markFinished：即使 shown 追平 raw，done 仍为 false
    let now = 0
    for (let i = 0; i < 120 && engine.shown < engine.raw.length; i++) {
      now += FRAME_MS
      engine.step(now)
    }
    expect(engine.shown).toBe(10)
    expect(engine.done).toBe(false)
    engine.markFinished()
    expect(engine.done).toBe(true)
  })

  it('reset() 回到初始状态（同实例复用）', () => {
    const engine = makeEngine({ baseCps: 160 })
    engine.feed('x'.repeat(100))
    engine.markFinished()
    runFrames(engine, 0, 10)
    engine.reset()
    expect(engine.raw).toBe('')
    expect(engine.shown).toBe(0)
    expect(engine.finished).toBe(false)
    expect(engine.gear).toBe('smooth')
    expect(engine.backlog).toBe(0)
    expect(engine.done).toBe(false)
  })

  it('速率缓动（惯性）：首帧不会从 0 跳到目标速率', () => {
    // enterChars 调高 + 喂足积压：保证整个收敛过程档位保持 smooth、
    // 积压不排空（排空帧会把 cps 归零）
    const engine = makeEngine({ baseCps: 400, enterChars: 3000 })
    engine.feed('x'.repeat(2000))
    engine.step(1) // 非零起点（_lastNow===0 是未初始化哨兵）
    engine.step(1 + FRAME_MS) // 第二个 16.7ms 帧
    // k = 1-exp(-dt/tau) ≈ 0.05 → cps ≈ 400×0.05 ≈ 20，远小于 400
    expect(engine.cps).toBeGreaterThan(0)
    expect(engine.cps).toBeLessThan(100)
    // 持续推进后收敛到 baseCps 附近（1s 时 ≈382）
    runFrames(engine, 1 + FRAME_MS, 60)
    expect(engine.cps).toBeGreaterThan(350)
    expect(engine.cps).toBeLessThanOrEqual(400)
  })
})
