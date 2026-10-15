/**
 * similarity — 字符二元组 Dice 相似度（渲染层重构 L3 配套，问题 2 去重）
 *
 * 用途：思考（reasoning）与正文（content）落地后比对，相似度 ≥ 阈值时
 * 由 AssistantMessageCell 自动折叠思考区并展示徽标——模型「先把 answer
 * 写进 reasoning 再原样吐 content」时消除重复展示。
 *
 * 算法：Sørensen–Dice on character bigrams
 *   dice = 2·|A ∩ B| / (|A| + |B|)   （多重集交集，词频计权）
 *
 * 设计约束：
 * - 忽略全部空白（\s+ 去除）：markdown 排版差异（换行/缩进）不参与判定，
 *   避免「内容相同只是排版不同」被误判为不相似。
 * - 单字符/空串回退：bigram 为空时退化为字符集合 Dice；双空视为相同。
 * - 纯函数、无依赖，可单测。
 */

/** 思考/正文去重判定阈值（与 render-layer 原型一致） */
export const SIMILARITY_THRESHOLD = 0.85

function _normalize(text: string): string {
  return (text || '').replace(/\s+/g, '')
}

/** 字符二元组多重集（Map<bigram, count>） */
export function bigramCounts(text: string): Map<string, number> {
  const norm = _normalize(text)
  const counts = new Map<string, number>()
  for (let i = 0; i + 1 < norm.length; i++) {
    const bg = norm.slice(i, i + 2)
    counts.set(bg, (counts.get(bg) || 0) + 1)
  }
  return counts
}

/**
 * 二元组 Dice 相似度，返回 [0, 1]。
 * - 双空串 → 1（调用方自行判空；这里保持全等关系自洽）
 * - 一方为空 → 0
 * - 完全相同的非空文本 → 1
 */
export function diceSimilarity(a: string, b: string): number {
  const na = _normalize(a)
  const nb = _normalize(b)
  if (!na && !nb) return 1
  if (!na || !nb) return 0
  if (na === nb) return 1

  // 单字符回退：字符集合 Dice（bigram 无法构成）
  if (na.length < 2 || nb.length < 2) {
    const sa = new Set(na)
    const sb = new Set(nb)
    let inter = 0
    for (const ch of sa) if (sb.has(ch)) inter++
    return (2 * inter) / (sa.size + sb.size)
  }

  const ca = bigramCounts(na)
  const cb = bigramCounts(nb)

  let inter = 0
  let total = 0
  for (const [bg, n] of ca) {
    const m = cb.get(bg)
    if (m) inter += Math.min(n, m)
    total += n
  }
  for (const n of cb.values()) total += n

  return total === 0 ? 0 : (2 * inter) / total
}

/** 便捷判定：思考与正文是否高度相似（默认阈值 SIMILARITY_THRESHOLD） */
export function isHighlySimilar(a: string, b: string, threshold: number = SIMILARITY_THRESHOLD): boolean {
  return diceSimilarity(a, b) >= threshold
}
