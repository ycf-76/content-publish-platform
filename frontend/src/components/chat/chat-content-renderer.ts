import { renderMarkdown } from './markdown-renderer'
import { sanitizeContent } from './cell-types'

// ════════════════════════════════════════════════════════════════
// Hidden tag registry — 新增标签只需往这里加一行，其余全自动
// ════════════════════════════════════════════════════════════════
const HIDDEN_TAGS = ['thinking', 'needs_clarification'] as const

// ────────────────────────────────────────────────────────────────
// 工具函数
// ────────────────────────────────────────────────────────────────

/** 正则特殊字符转义 */
function _esc(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 嵌套可选组：为标签名生成一个匹配其任意前缀的正则片段。
 *
 * "thinking" → "t(?:h(?:i(?:n(?:k(?:i(?:n(?:g)?)?)?)?)?)?)?"
 *
 * 这一个正则等价于 8 个独立正则：
 *   /<t$/i, /<th$/i, /<thi$/i, /<thin$/i, /<think$/i,
 *   /<thinki$/i, /<thinkin$/i, /<thinking$/i
 *
 * 原理：每个字符用 (?:x)? 包裹，表示"可选但必须按顺序"，
 * 所以只能匹配 tag 的前缀，不会误匹配 <the、<they 等。
 */
function _prefixRe(tag: string): string {
  if (!tag) return ''
  let p = tag[0]
  for (let i = 1; i < tag.length; i++) p += `(?:${tag[i]}`
  for (let i = 1; i < tag.length; i++) p += ')?'
  return p
}

// ────────────────────────────────────────────────────────────────
// 文本层清洗（markdown 渲染前调用）
// ────────────────────────────────────────────────────────────────

/**
 * 从原始文本中剥离所有 HIDDEN_TAGS 及其内容。
 *
 * 处理四种形态：
 *   1) 完整标签对    <tag>...</tag>
 *   2) 未闭合标签    <tag>...$        （流式截断 / max_tokens 截断）
 *   3) 带属性未闭合  <tag attr...$
 *   4) 部分前缀      <t, <th, <thi …  （逐字截断，用 _prefixRe 一条搞定）
 */
export function stripHiddenTags(text: string): string {
  if (!text) return ''

  // 保护代码块，防止误删代码中的标签
  const cbs: string[] = []
  let s = text.replace(/```[\s\S]*?```/g, (m) => {
    cbs.push(m)
    return `\x00CB${cbs.length - 1}\x00`
  })

  for (const tag of HIDDEN_TAGS) {
    const e = _esc(tag)
    const pfx = _prefixRe(tag)
    // 1) 完整标签对
    s = s.replace(new RegExp(`<${e}>[\\s\\S]*?<\\/${e}>`, 'gi'), '')
    // 2) 未闭合到末尾
    s = s.replace(new RegExp(`<${e}>[\\s\\S]*$`, 'gi'), '')
    // 3) 带属性未闭合
    s = s.replace(new RegExp(`<${e}[^>]*$`, 'gi'), '')
    // 4) 部分前缀（一条正则覆盖所有截断位置）
    s = s.replace(new RegExp(`<${pfx}$`, 'gi'), '')
  }

  // 行尾孤立的 < （不属于任何已知标签的截断残留）
  s = s.replace(/(?<![\/\w])<(?![\w\/])(?=\s*$)/gm, '')

  // 恢复代码块
  s = s.replace(/\x00CB(\d+)\x00/g, (_, i) => cbs[Number(i)])
  return s.trim()
}

// ────────────────────────────────────────────────────────────────
// HTML 层清洗（markdown 渲染后调用，安全网）
// ────────────────────────────────────────────────────────────────

/**
 * 从渲染后的 HTML 中剥离隐藏标签。
 *
 * 需要同时处理两种形式：
 *   - 原始形式：浏览器直接解析的 <tag>...</tag>
 *   - 转义形式：markdown-it 输出的 &lt;tag&gt;...&lt;/tag&gt;
 *
 * 部分前缀用 (?![\w-]) 做词界守卫，防止误杀 &lt;the、&lt;they 等正常文本。
 */
export function stripThinkingFromHtml(html: string): string {
  if (!html) return ''
  let s = html

  for (const tag of HIDDEN_TAGS) {
    const e = _esc(tag)
    const pfx = _prefixRe(tag)

    // ── 原始 HTML 形式 ──
    s = s.replace(new RegExp(`<${e}>[\\s\\S]*?<\\/${e}>`, 'gi'), '')
    s = s.replace(new RegExp(`<${e}>[\\s\\S]*$`, 'gi'), '')
    s = s.replace(new RegExp(`<${e}[^>]*$`, 'gi'), '')
    // 部分前缀：词界守卫，<thi 不会误杀 <the / <they
    s = s.replace(new RegExp(`<${pfx}(?![\\w-])`, 'gi'), '')

    // ── 转义 HTML 形式（markdown-it 输出） ──
    s = s.replace(new RegExp(`&lt;${e}&gt;[\\s\\S]*?&lt;\\/${e}&gt;`, 'gi'), '')
    s = s.replace(new RegExp(`&lt;${e}&gt;[\\s\\S]*$`, 'gi'), '')
    // 部分转义前缀：同样的词界守卫
    s = s.replace(new RegExp(`&lt;${pfx}(?![\\w-])`, 'gi'), '')
    // 孤立闭合标签残留
    s = s.replace(new RegExp(`&lt;\\/${e}&gt;`, 'gi'), '')
    s = s.replace(new RegExp(`<code>&lt;\\/${e}&gt;<\\/code>`, 'g'), '')
  }

  // 行尾孤立的 <
  s = s.replace(/(?<![\/\w])<(?![\w\/])(?=\s*$)/gm, '')
  return s.trim()
}

// ────────────────────────────────────────────────────────────────
// Markdown 渲染管线
// ────────────────────────────────────────────────────────────────

function normalizeChatMarkdown(text: string): string {
  let cleaned = typeof text === 'string' ? text : String(text || '')
  cleaned = cleaned.replace(/\r\n?/g, '\n')
  cleaned = stripHiddenTags(cleaned)
  cleaned = sanitizeContent(cleaned)
  return cleaned.trim()
}

function wrapMarkdownHtml(html: string, extraClass = ''): string {
  if (!html) return ''
  const className = ['dsh-md', extraClass].filter(Boolean).join(' ')
  return `<div class="${className}">${html}</div>`
}

export function renderAssistantHtml(text: string): string {
  const normalized = normalizeChatMarkdown(text)
  if (!normalized) return ''
  return wrapMarkdownHtml(renderMarkdown(normalized))
}

export function renderUserHtml(text: string): string {
  const normalized = normalizeChatMarkdown(text)
  if (!normalized) return ''
  return wrapMarkdownHtml(renderMarkdown(normalized), 'dsh-md-user')
}

export function renderReasoningHtml(text: string): string {
  const normalized = normalizeChatMarkdown(text)
  if (!normalized) return ''
  return wrapMarkdownHtml(renderMarkdown(normalized), 'dsh-md-reasoning')
}

export function wrapStreamHtml(html: string): string {
  return wrapMarkdownHtml(stripThinkingFromHtml(html))
}