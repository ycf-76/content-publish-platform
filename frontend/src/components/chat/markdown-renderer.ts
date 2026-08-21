import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: false,
  breaks: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
        return `<pre class="dsh-code-block"><span class="dsh-code-lang">${escapeHtml(lang)}</span><code class="hljs">${highlighted}</code></pre>`
      } catch {
        // fall through
      }
    }
    const autoResult = hljs.highlightAuto(str)
    return `<pre class="dsh-code-block"><span class="dsh-code-lang">${escapeHtml(lang || 'text')}</span><code class="hljs">${autoResult.value}</code></pre>`
  },
})

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
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
  return `<code class="dsh-inline-code">\`${content}\`</code>`
}

md.renderer.rules.link_open = function () {
  return '<span class="dsh-link-text">'
}

md.renderer.rules.link_close = function () {
  return '</span>'
}

md.renderer.rules.fence = function (tokens, idx) {
  const token = tokens[idx]
  const info = token.info ? token.info.trim() : ''
  const lang = info.split(/\s+/g)[0] || ''
  const content = token.content

  if (lang && hljs.getLanguage(lang)) {
    try {
      const highlighted = hljs.highlight(content, { language: lang, ignoreIllegals: true }).value
      return `<pre class="dsh-code-block"><span class="dsh-code-lang">${escapeHtml(lang)}</span><code class="hljs">${highlighted}</code></pre>`
    } catch {
      // fall through
    }
  }

  const autoResult = hljs.highlightAuto(content)
  return `<pre class="dsh-code-block"><span class="dsh-code-lang">${escapeHtml(lang || 'text')}</span><code class="hljs">${autoResult.value}</code></pre>`
}

export function renderMarkdown(text: string): string {
  if (!text) return ''
  const stripped = stripMarkdownFence(text)
  return md.render(stripped)
}

function stripMarkdownFence(text: string): string {
  return text.replace(/^```(?:md|markdown)\s*\n([\s\S]*?)```$/m, '$1')
}

export function renderThinkingText(text: string): string {
  if (!text) return ''
  const escaped = escapeHtml(text)
  return escaped.replace(/\n/g, '<br/>')
}