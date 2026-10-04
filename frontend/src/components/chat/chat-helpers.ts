import type { ChatMessage } from './cell-types'

export function toTagList(tags: any): string[] {
  if (Array.isArray(tags)) return tags.filter((t): t is string => typeof t === 'string')
  if (tags && typeof tags === 'object' && Array.isArray(tags.items)) return toTagList(tags.items)
  return []
}

export function isLastAssistant(idx: number, messages: ChatMessage[]): boolean {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') return i === idx
  }
  return false
}

export function getResultLineCount(result: string): number {
  if (!result) return 0
  return result.split('\n').filter(Boolean).length
}

export function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export function renderDiff(content: string): string {
  if (!content) return ''
  return content.split('\n').map(line => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return `<span class="dsh-diff-line-add">${escapeHtml(line)}</span>`
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      return `<span class="dsh-diff-line-del">${escapeHtml(line)}</span>`
    } else if (line.startsWith('@@')) {
      return `<span class="dsh-diff-line-hunk">${escapeHtml(line)}</span>`
    }
    return escapeHtml(line)
  }).join('\n')
}