import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import yaml from 'highlight.js/lib/languages/yaml'
import bash from 'highlight.js/lib/languages/bash'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import sql from 'highlight.js/lib/languages/sql'
import markdown from 'highlight.js/lib/languages/markdown'

hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('json', json)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('svg', xml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)

const COPY_BTN_SVG = '<button class="dsh-code-copy-btn" title="复制代码"><svg class="dsh-copy-icon-default" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><svg class="dsh-copy-icon-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></button>'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: false,
  breaks: true,
})

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function renderCodeBlock(lang: string, content: string): string {
  const safeLang = escapeHtml(lang || 'text')
  const source = content.replace(/\n$/, '')
  const lineCount = source ? source.split('\n').length : 1
  const gutter = Array.from({ length: lineCount }, (_, i) => i + 1).join('\n')

  let highlighted = ''
  if (lang && hljs.getLanguage(lang)) {
    try {
      highlighted = hljs.highlight(content, { language: lang, ignoreIllegals: true }).value
    } catch {
      highlighted = escapeHtml(content)
    }
  } else {
    highlighted = hljs.highlightAuto(content).value
  }

  return `<div class="dsh-code-block">
  <div class="dsh-code-header">
    <span class="dsh-code-lang">${safeLang}</span>
    <span class="dsh-code-actions">${COPY_BTN_SVG}</span>
  </div>
  <div class="dsh-code-body">
    <span class="dsh-code-gutter" aria-hidden="true">${gutter}</span>
    <code class="hljs">${highlighted}</code>
  </div>
</div>`
}

md.inline.ruler.push('highlight_mark', (state, silent) => {
  const max = state.posMax
  const start = state.pos
  if (start + 3 > max) return false
  if (state.src.charCodeAt(start) !== 0x3D /* = */) return false
  if (state.src.charCodeAt(start + 1) !== 0x3D /* = */) return false
  if (silent) return false
  let pos = start + 2
  let found = -1
  while (pos < max - 1) {
    if (state.src.charCodeAt(pos) === 0x3D && state.src.charCodeAt(pos + 1) === 0x3D) {
      found = pos
      break
    }
    pos++
  }
  if (found === -1) return false
  const content = state.src.slice(start + 2, found)
  if (!content.trim()) return false
  const tokenOpen = state.push('highlight_mark_open', 'mark', 1)
  tokenOpen.markup = '=='
  const tokenText = state.push('text', '', 0)
  tokenText.content = content
  const tokenClose = state.push('highlight_mark_close', 'mark', -1)
  tokenClose.markup = '=='
  state.pos = found + 2
  return true
})

md.renderer.rules.code_inline = function (tokens, idx) {
  const content = escapeHtml(tokens[idx].content)
  return `<code class="dsh-inline-code" title="点击复制">${content}</code>`
}

function normalizePath(href: string): string {
  return href.replace(/\\/g, '/')
}

md.renderer.rules.link_open = function (tokens, idx) {
  let href = String(tokens[idx].attrGet('href') || '')
  if (/^[A-Za-z]:\\|^\\\\|^~\/|^\.\.?\//.test(href)) {
    href = normalizePath(href)
    if (!href.startsWith('file://') && /^[A-Za-z]:\//.test(href)) {
      href = 'file:///' + href
    }
  }
  const safeHref = href.replace(/"/g, '&quot;')
  return `<span class="dsh-link-wrap"><a class="dsh-link-text" href="${safeHref}" target="_blank" rel="noopener noreferrer">`
}

md.renderer.rules.link_close = function () {
  return `</a></span>`
}

md.renderer.rules.fence = function (tokens, idx) {
  const token = tokens[idx]
  const info = token.info ? token.info.trim() : ''
  const lang = info.split(/\s+/g)[0] || ''
  return renderCodeBlock(lang, token.content)
}

md.renderer.rules.code_block = function (tokens, idx) {
  return renderCodeBlock('', tokens[idx].content)
}

const _mdCache = new Map<string, string>()

const CARD_HTML_OPEN = '<!--card-html-->'
const CARD_HTML_CLOSE = '<!--/card-html-->'

export function renderMarkdown(text: string): string {
  if (!text) return ''
  const cached = _mdCache.get(text)
  if (cached !== undefined) return cached

  let preprocessed = text
  const cardHtmlBlocks: string[] = []
  preprocessed = preprocessed.replace(
    new RegExp(escapeRegex(CARD_HTML_OPEN) + '([\\s\\S]*?)' + escapeRegex(CARD_HTML_CLOSE), 'g'),
    (_, html) => {
      const idx = cardHtmlBlocks.length
      cardHtmlBlocks.push(html)
      return `\x00CARD_HTML_${idx}\x00`
    }
  )

  const stripped = stripMarkdownFence(preprocessed)
  let result = md.render(stripped)

  if (cardHtmlBlocks.length > 0) {
    for (let i = 0; i < cardHtmlBlocks.length; i++) {
      const placeholder = `\x00CARD_HTML_${i}\x00`
      const escapedPlaceholder = placeholder.replace(/\x00/g, '&#x00;')
      const sandboxedHtml = `<div class="dsh-card-html-wrap"><iframe sandbox="allow-same-origin" srcdoc="${escapeAttr(cardHtmlBlocks[i])}" class="dsh-card-iframe" loading="lazy"></iframe></div>`
      result = result.replace(escapedPlaceholder, sandboxedHtml)
      result = result.replace(placeholder, sandboxedHtml)
    }
  }

  result = degradeWideTables(result)
  if (_mdCache.size > 64) {
    const firstKey = _mdCache.keys().next().value as string
    if (firstKey !== undefined) _mdCache.delete(firstKey)
  }
  _mdCache.set(text, result)
  return result
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function degradeWideTables(html: string): string {
  return html.replace(/<table>([\s\S]*?)<\/table>/g, (match) => {
    const rows = match.match(/<tr[\s\S]*?<\/tr>/g)
    if (!rows || rows.length < 2) return match
    const headerRow = rows[0]
    const headers = (headerRow.match(/<th[\s\S]*?>([\s\S]*?)<\/th>/g) || []).map(
      (h) => h.replace(/<th[^>]*>/, '').replace(/<\/th>/, '').trim()
    )
    if (headers.length !== 2) return match
    const bodyRows = rows.slice(1)
    let hasLongContent = false
    for (const row of bodyRows) {
      const cells = (row.match(/<td[\s\S]*?>([\s\S]*?)<\/td>/g) || []).map(
        (c) => c.replace(/<td[^>]*>/, '').replace(/<\/td>/, '').trim()
      )
      for (const cell of cells) {
        if (cell.length > 60 || /\/|\\|https?:\/\//.test(cell)) {
          hasLongContent = true
          break
        }
      }
      if (hasLongContent) break
    }
    if (!hasLongContent) return match
    let kvHtml = '<dl class="dsh-kv-list">'
    for (const row of bodyRows) {
      const cells = (row.match(/<td[\s\S]*?>([\s\S]*?)<\/td>/g) || []).map(
        (c) => c.replace(/<td[^>]*>/, '').replace(/<\/td>/, '').trim()
      )
      if (cells.length >= 2) {
        kvHtml += `<dt>${cells[0]}</dt><dd>${cells[1]}</dd>`
      }
    }
    kvHtml += '</dl>'
    return kvHtml
  })
}

function stripMarkdownFence(text: string): string {
  return text.replace(/^```(?:md|markdown)\s*\n([\s\S]*?)```$/m, '$1')
}

export function renderThinkingText(text: string): string {
  if (!text) return ''
  const escaped = escapeHtml(text)
  return escaped.replace(/\n/g, '<br/>')
}