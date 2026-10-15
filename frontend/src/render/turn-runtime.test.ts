import { describe, it, expect } from 'vitest'
import { TurnRuntime, genTurnId } from './turn-runtime'
import { diceSimilarity, isHighlySimilar, bigramCounts, SIMILARITY_THRESHOLD } from './similarity'

/**
 * TurnRuntime 单测（渲染层重构 L2，问题 6 回合隔离）
 * + similarity 单测（问题 2 思考/正文去重）
 */

describe('genTurnId', () => {
  it('生成唯一且格式可控的回合 ID', () => {
    const a = genTurnId()
    const b = genTurnId()
    expect(a).toMatch(/^turn_[0-9a-z]+_[0-9a-z]+$/)
    expect(a).not.toBe(b)
  })
})

describe('TurnRuntime 事件准入', () => {
  it('同回合事件放行，并置位 turnStarted', () => {
    const rt = new TurnRuntime('turn_test_1')
    expect(rt.turnStarted).toBe(false)
    expect(rt.accepts({ turn_id: 'turn_test_1', type: 'chat_turn_started' })).toBe(true)
    expect(rt.turnStarted).toBe(true)
    expect(rt.droppedEvents).toBe(0)
  })

  it('异回合事件拒绝并计数', () => {
    const rt = new TurnRuntime('turn_test_1')
    expect(rt.accepts({ turn_id: 'turn_other', type: 'agent_message_delta' })).toBe(false)
    expect(rt.droppedEvents).toBe(1)
    expect(rt.accepts({ turn_id: 'turn_another', type: 'agent_message_delta' })).toBe(false)
    expect(rt.droppedEvents).toBe(2)
    expect(rt.turnStarted).toBe(false)
  })

  it('无 turn_id 的遗留事件一律拒绝（旧 replay 泄洪口）', () => {
    const rt = new TurnRuntime('turn_test_1')
    expect(rt.accepts({ type: 'chat_turn_started' })).toBe(false)
    expect(rt.droppedEvents).toBe(1)
  })

  it('构造时传入 turnId 即使用该值', () => {
    const rt = new TurnRuntime('turn_fixed_42')
    expect(rt.turnId).toBe('turn_fixed_42')
    expect(rt.accepts({ turn_id: 'turn_fixed_42' })).toBe(true)
  })
})

describe('TurnRuntime 计时', () => {
  it('elapsedMs 计时，end() 冻结，end(duration) 记录后端耗时', () => {
    const rt = new TurnRuntime('turn_t')
    const e1 = rt.elapsedMs
    expect(e1).toBeGreaterThanOrEqual(0)
    rt.end(1234)
    expect(rt.durationMs).toBe(1234)
    // end() 冻结计时： elapsed 不再增长
    const frozen = rt.elapsedMs
    expect(frozen).toBeGreaterThanOrEqual(0)
    expect(rt.elapsedMs).toBe(frozen)
    // 二次 end 不覆盖
    rt.end(9999)
    expect(rt.durationMs).toBe(1234)
  })

  it('end() 忽略非法 duration（None/0/负值）', () => {
    const rt = new TurnRuntime('turn_t2')
    rt.end(null)
    expect(rt.durationMs).toBeNull()
    rt.end(0)
    expect(rt.durationMs).toBeNull()
    rt.end(-5)
    expect(rt.durationMs).toBeNull()
  })
})

describe('diceSimilarity（思考/正文去重）', () => {
  it('完全相同 → 1', () => {
    expect(diceSimilarity('今天天气很好，我们出去玩吧', '今天天气很好，我们出去玩吧')).toBe(1)
  })

  it('空白排版差异不参与判定', () => {
    expect(diceSimilarity('你好 世界\n再见', '你好世界再见')).toBe(1)
  })

  it('完全不同 → 0', () => {
    expect(diceSimilarity('AAAAAAAAAA', 'BBBBBBBBBB')).toBe(0)
  })

  it('部分相似 → (0,1) 之间', () => {
    const s = diceSimilarity('春天的第一杯奶茶，唤醒沉睡的味蕾', '春天的第一杯咖啡，唤醒沉睡的清晨')
    expect(s).toBeGreaterThan(0.3)
    expect(s).toBeLessThan(0.95)
  })

  it('空串边界：双空为 1，单空为 0', () => {
    expect(diceSimilarity('', '')).toBe(1)
    expect(diceSimilarity('', 'abc')).toBe(0)
    expect(diceSimilarity('abc', '')).toBe(0)
  })

  it('单字符回退到字符集合 Dice', () => {
    expect(diceSimilarity('a', 'a')).toBe(1)
    expect(diceSimilarity('a', 'b')).toBe(0)
    // 长度 2 有合法 bigram，走 bigram 路径：'ab' vs 'ac' 无共享二元组 → 0
    expect(diceSimilarity('ab', 'ac')).toBe(0)
    // 单字符侧触发回退：'x' vs 'xy' → 集合 Dice = 2×1/(1+2) = 2/3
    expect(diceSimilarity('x', 'xy')).toBeCloseTo(2 / 3, 5)
  })

  it('isHighlySimilar 按阈值判定，阈值可配', () => {
    const a = '完全一样的文本内容啊'
    const b = '完全一样的文本内容啊'
    expect(isHighlySimilar(a, b)).toBe(true)
    expect(isHighlySimilar('AAAAAAAA', 'BBBBBBBB')).toBe(false)
    // 阈值提高到 1.01 时全不相同
    expect(isHighlySimilar(a, b, 1.01)).toBe(false)
    expect(SIMILARITY_THRESHOLD).toBe(0.85)
  })

  it('bigramCounts 统计二元组多重集', () => {
    const counts = bigramCounts('abab')
    expect(counts.get('ab')).toBe(2)
    expect(counts.get('ba')).toBe(1)
    expect(counts.size).toBe(2)
  })
})
